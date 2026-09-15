// main/demo_balance.c —— GLM 积分余额监控页。
// 连接 NET_WIFI_SSID,轮询局域网聚合服务(NET_SERVER_URL,见 tools/balance_server.py),
// 显示滚动 5 小时窗与 7 天窗的估算积分消耗。数据为本地记账口径(hermes 流量)。
#include "demo.h"
#include "demo_radio.h"
#include "bsp_display.h"
#include "ui_pixel.h"
#if __has_include("net_config.h")
#include "net_config.h"
#else
#include "net_config.defaults.h"
#endif

#include "cJSON.h"
#include "esp_event.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_netif_ip_addr.h"
#include "esp_wifi.h"
#include "lvgl.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include <stdio.h>
#include <string.h>

static const char *TAG = "demo_balance";

#define POLL_PERIOD_MS (5u * 60u * 1000u)
#define HTTP_BUF_SIZE  2048
#define FETCH_STACK    8192

typedef enum {
    BAL_WIFI_CONNECTING = 0,
    BAL_FETCHING,
    BAL_ONLINE,
    BAL_ERROR,
} bal_state_t;

// 页面 UI(LVGL 上下文持有)
static lv_obj_t *s_scr;
static lv_obj_t *s_status;
static lv_obj_t *s_5h;
static lv_obj_t *s_week;
static lv_obj_t *s_note;
static lv_timer_t *s_timer;

// 网络与工作任务(start/stop 生命周期持有)
static esp_netif_t *s_sta_netif;
static esp_event_handler_instance_t s_got_ip_handler;
static esp_event_handler_instance_t s_discon_handler;
static SemaphoreHandle_t s_wakeup;
static TaskHandle_t s_task;
static volatile bool s_running;
static bool s_wifi_initialized;
static bool s_wifi_started;
static bool s_handlers_registered;

// 状态与最新数值(fetch 任务写,tick 在 LVGL 上下文读;均为字长以内,可接受非原子)
static volatile bal_state_t s_state;
static char s_status_text[96];
static double s_pts_5h;
static int    s_calls_5h;
static double s_pts_week;
static int    s_calls_week;

static void set_status(bal_state_t st, const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(s_status_text, sizeof(s_status_text), fmt, ap);
    va_end(ap);
    s_state = st;
}

static void on_got_ip(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg; (void)base; (void)id;
    ip_event_got_ip_t *evt = (ip_event_got_ip_t *)data;
    set_status(BAL_FETCHING, "IP " IPSTR "  fetching...", IP2STR(&evt->ip_info.ip));
    if (s_wakeup) xSemaphoreGive(s_wakeup);   // 立刻拉一次
}

static void on_disconnected(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg; (void)base; (void)id; (void)data;
    if (s_running) {
        set_status(BAL_WIFI_CONNECTING, "Wi-Fi lost, retrying...");
        esp_wifi_connect();
    }
}

static void parse_body(const char *body)
{
    cJSON *root = cJSON_Parse(body);
    if (!root) {
        set_status(BAL_ERROR, "Bad JSON");
        return;
    }
    const cJSON *w5 = cJSON_GetObjectItem(root, "window_5h");
    const cJSON *wk = cJSON_GetObjectItem(root, "week");
    const cJSON *p;
    if (w5 && (p = cJSON_GetObjectItem(w5, "points")) && cJSON_IsNumber(p)) s_pts_5h = p->valuedouble;
    if (w5 && (p = cJSON_GetObjectItem(w5, "calls")) && cJSON_IsNumber(p)) s_calls_5h = (int)p->valueint;
    if (wk && (p = cJSON_GetObjectItem(wk, "points")) && cJSON_IsNumber(p)) s_pts_week = p->valuedouble;
    if (wk && (p = cJSON_GetObjectItem(wk, "calls")) && cJSON_IsNumber(p)) s_calls_week = (int)p->valueint;
    cJSON_Delete(root);
    set_status(BAL_ONLINE, "Online  %d calls/5h", s_calls_5h);
}

static void fetch_once(void)
{
    char buf[HTTP_BUF_SIZE];
    esp_http_client_config_t cfg = {
        .url = NET_SERVER_URL,
        .timeout_ms = 8000,
        .disable_auto_redirect = false,
    };
    esp_http_client_handle_t client = esp_http_client_init(&cfg);
    if (!client) {
        set_status(BAL_ERROR, "HTTP init failed");
        return;
    }
    esp_err_t err = esp_http_client_open(client, 0);
    int len = 0;
    int code = 0;
    if (err == ESP_OK) {
        esp_http_client_fetch_headers(client);
        int r;
        while (len < (int)sizeof(buf) - 1 &&
               (r = esp_http_client_read(client, buf + len, sizeof(buf) - 1 - len)) > 0) {
            len += r;
        }
        buf[len] = 0;
        code = esp_http_client_get_status_code(client);
        esp_http_client_close(client);
    }
    esp_http_client_cleanup(client);
    if (code == 200 && len > 0) {
        parse_body(buf);
    } else {
        set_status(BAL_ERROR, "HTTP %d (len %d)", code, len);
    }
    ESP_LOGI(TAG, "fetch: code=%d len=%d state=%d", code, len, (int)s_state);
}

static void bal_task(void *arg)
{
    (void)arg;
    while (s_running) {
        xSemaphoreTake(s_wakeup, pdMS_TO_TICKS(POLL_PERIOD_MS));
        if (!s_running) break;
        fetch_once();
    }
    vTaskDelete(NULL);
}

static void wifi_stack_stop(void)
{
    if (s_wifi_started) {
        esp_wifi_stop();
        s_wifi_started = false;
    }
    if (s_handlers_registered) {
        esp_event_handler_instance_unregister(IP_EVENT, IP_EVENT_STA_GOT_IP, s_got_ip_handler);
        esp_event_handler_instance_unregister(WIFI_EVENT, WIFI_EVENT_STA_DISCONNECTED, s_discon_handler);
        s_handlers_registered = false;
    }
    if (s_wifi_initialized) {
        esp_wifi_deinit();
        s_wifi_initialized = false;
    }
    if (s_sta_netif) {
        esp_netif_destroy_default_wifi(s_sta_netif);
        s_sta_netif = NULL;
    }
}

esp_err_t demo_balance_start(void)
{
    set_status(BAL_WIFI_CONNECTING, "Wi-Fi connecting...");

    esp_err_t err = demo_radio_nvs_prepare();
    if (err != ESP_OK) goto fail;
    err = demo_radio_network_prepare();
    if (err != ESP_OK) goto fail;

    s_sta_netif = esp_netif_create_default_wifi_sta();
    if (!s_sta_netif) { err = ESP_ERR_NO_MEM; goto fail; }

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    err = esp_wifi_init(&cfg);
    if (err != ESP_OK) goto fail;
    s_wifi_initialized = true;

    err = esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP,
                                              on_got_ip, NULL, &s_got_ip_handler);
    if (err != ESP_OK) goto fail;
    err = esp_event_handler_instance_register(WIFI_EVENT, WIFI_EVENT_STA_DISCONNECTED,
                                              on_disconnected, NULL, &s_discon_handler);
    if (err != ESP_OK) goto fail;
    s_handlers_registered = true;

    wifi_config_t wc = { 0 };
    strlcpy((char *)wc.sta.ssid, NET_WIFI_SSID, sizeof(wc.sta.ssid));
    strlcpy((char *)wc.sta.password, NET_WIFI_PASS, sizeof(wc.sta.password));

    err = esp_wifi_set_storage(WIFI_STORAGE_RAM);
    if (err != ESP_OK) goto fail;
    err = esp_wifi_set_mode(WIFI_MODE_STA);
    if (err != ESP_OK) goto fail;
    err = esp_wifi_set_config(WIFI_IF_STA, &wc);
    if (err != ESP_OK) goto fail;
    err = esp_wifi_start();
    if (err != ESP_OK) goto fail;
    s_wifi_started = true;

    err = esp_wifi_connect();
    if (err != ESP_OK) goto fail;

    s_wakeup = xSemaphoreCreateBinary();
    if (!s_wakeup) { err = ESP_ERR_NO_MEM; goto fail; }
    s_running = true;
    if (xTaskCreate(bal_task, "bal_fetch", FETCH_STACK, NULL, 4, &s_task) != pdPASS) {
        s_running = false;
        vSemaphoreDelete(s_wakeup);
        s_wakeup = NULL;
        err = ESP_ERR_NO_MEM;
        goto fail;
    }
    return ESP_OK;

fail:
    wifi_stack_stop();
    set_status(BAL_ERROR, "start failed: %s", esp_err_to_name(err));
    ESP_LOGE(TAG, "余额页启动失败: %s", esp_err_to_name(err));
    return err;
}

esp_err_t demo_balance_stop(void)
{
    s_running = false;
    if (s_wakeup) xSemaphoreGive(s_wakeup);
    if (s_task) {
        vTaskDelay(pdMS_TO_TICKS(100));   // 给任务退出时间
        s_task = NULL;
    }
    if (s_wakeup) {
        vSemaphoreDelete(s_wakeup);
        s_wakeup = NULL;
    }
    wifi_stack_stop();
    return ESP_OK;
}

static void fmt_pts(char *buf, int n, const char *prefix, double pts)
{
    int whole = (int)pts;
    int tenth = (int)((pts - whole) * 10.0 + 0.5);
    if (tenth >= 10) { whole += 1; tenth -= 10; }
    snprintf(buf, n, "%s %d.%d", prefix, whole, tenth);
}
static void tick(lv_timer_t *timer)
{
    (void)timer;
    if (!s_status) return;
    lv_label_set_text(s_status, s_status_text);
    if (s_state == BAL_ONLINE) {
        lv_obj_set_style_text_color(s_status, lv_color_hex(UI_GRASS_DARK), 0);
    } else if (s_state == BAL_ERROR) {
        lv_obj_set_style_text_color(s_status, lv_color_hex(UI_RED), 0);
    } else {
        lv_obj_set_style_text_color(s_status, lv_color_hex(UI_SKY_DARK), 0);
    }
    char b5[32], bw[32];
    fmt_pts(b5, sizeof(b5), "5h", s_pts_5h);
    fmt_pts(bw, sizeof(bw), "7d", s_pts_week);
    lv_label_set_text_fmt(s_5h, "%s / %d", b5, NET_PLAN_5H);
    lv_label_set_text_fmt(s_week, "%s / %d", bw, NET_PLAN_WEEK);
}

void demo_balance_enter(void)
{
    s_pts_5h = s_pts_week = 0.0;
    s_calls_5h = s_calls_week = 0;
    strlcpy(s_status_text, "starting...", sizeof(s_status_text));
    s_state = BAL_WIFI_CONNECTING;

    s_scr = ui_pixel_screen_create("BALANCE");
    lv_obj_t *panel = ui_pixel_panel_create(s_scr, 12, 54, 216, 150, UI_PAPER);

    s_status = lv_label_create(panel);
    lv_obj_set_width(s_status, 196);
    lv_obj_set_style_text_color(s_status, lv_color_hex(UI_SKY_DARK), 0);
    lv_obj_align(s_status, LV_ALIGN_TOP_LEFT, 2, 2);
    lv_label_set_text(s_status, s_status_text);

    s_5h = lv_label_create(panel);
    lv_obj_set_style_text_font(s_5h, &lv_font_montserrat_20, 0);
    lv_obj_set_style_text_color(s_5h, lv_color_hex(UI_INK), 0);
    lv_obj_align(s_5h, LV_ALIGN_TOP_LEFT, 2, 30);
    lv_label_set_text(s_5h, "5h  --");

    s_week = lv_label_create(panel);
    lv_obj_set_style_text_font(s_week, &lv_font_montserrat_20, 0);
    lv_obj_set_style_text_color(s_week, lv_color_hex(UI_INK), 0);
    lv_obj_align(s_week, LV_ALIGN_TOP_LEFT, 2, 70);
    lv_label_set_text(s_week, "7d  --");

    s_note = lv_label_create(panel);
    lv_obj_set_width(s_note, 196);
    lv_obj_set_style_text_font(s_note, &lv_font_montserrat_14, 0);
    lv_obj_set_style_text_color(s_note, lv_color_hex(UI_INK), 0);
    lv_obj_align(s_note, LV_ALIGN_TOP_LEFT, 2, 112);
    lv_label_set_text(s_note, "local est. (hermes)\nOK: refresh now");

    ui_pixel_mascot_create(s_scr, 101, 246);
    s_timer = lv_timer_create(tick, 250, NULL);
    lv_screen_load(s_scr);
}

void demo_balance_exit(void)
{
    if (s_timer) {
        lv_timer_delete(s_timer);
        s_timer = NULL;
    }
    if (s_scr) {
        lv_obj_delete(s_scr);
        s_scr = NULL;
        s_status = s_5h = s_week = s_note = NULL;
    }
}

void demo_balance_key(bsp_btn_t btn, bsp_btn_ev_t ev)
{
    if (btn != BSP_BTN_OK || ev != BSP_BTN_CLICK) return;
    if (s_wakeup) xSemaphoreGive(s_wakeup);   // 手动立刻刷新
}
