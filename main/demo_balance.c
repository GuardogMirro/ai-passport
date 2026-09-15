// main/demo_balance.c —— GLM 积分余额监控页(官方配额版 v4)。
// 双进度条+百分比+窗口重置时刻+右上角刷新时间;数值来自 tools/balance_server.py
// 代理的智谱官方端点 /api/monitor/usage/quota/limit(与 PC 侧余额卡同源同数)。
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
#include "serial_screenshot.h"
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

static lv_obj_t *s_scr;
static lv_obj_t *s_status;
static lv_obj_t *s_upd_label;
static lv_obj_t *s_val5, *s_bar5, *s_pct5, *s_title5;
static lv_obj_t *s_valw, *s_barw, *s_pctw, *s_titlew;
static lv_timer_t *s_timer;

static esp_netif_t *s_sta_netif;
static esp_event_handler_instance_t s_got_ip_handler;
static esp_event_handler_instance_t s_discon_handler;
static SemaphoreHandle_t s_wakeup;
static TaskHandle_t s_task;
static volatile bool s_running;
static bool s_wifi_initialized;
static bool s_wifi_started;
static bool s_handlers_registered;

static volatile bal_state_t s_state;
static char s_status_text[96];
static int s_used_5h, s_limit_5h;
static int s_used_wk, s_limit_wk;
static char s_reset_5h[16];
static char s_reset_wk[16];
static char s_level[8] = "GLM";
static bool s_stale;
static char s_upd_time[8] = "--:--";

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
    if (s_wakeup) xSemaphoreGive(s_wakeup);
}

static void on_disconnected(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg; (void)base; (void)id; (void)data;
    if (s_running) {
        set_status(BAL_WIFI_CONNECTING, "Wi-Fi lost, retrying...");
        esp_wifi_connect();
    }
}

// v4 schema(官方端点经 server 代理):
//   { ok, level, stale, now_local,
//     window_5h: {used, limit, pct, reset_local}, week: {...} }
static void parse_body(const char *body)
{
    cJSON *root = cJSON_Parse(body);
    if (!root) {
        set_status(BAL_ERROR, "Bad JSON");
        return;
    }
    const cJSON *ok = cJSON_GetObjectItem(root, "ok");
    if (!cJSON_IsTrue(ok)) {
        const cJSON *er = cJSON_GetObjectItem(root, "error");
        set_status(BAL_ERROR, "srv: %s",
                   (er && cJSON_IsString(er) && er->valuestring) ? er->valuestring : "not ok");
        cJSON_Delete(root);
        return;
    }
    const cJSON *w5 = cJSON_GetObjectItem(root, "window_5h");
    const cJSON *wk = cJSON_GetObjectItem(root, "week");
    const cJSON *nt = cJSON_GetObjectItem(root, "now_local");
    const cJSON *lvl = cJSON_GetObjectItem(root, "level");
    const cJSON *st = cJSON_GetObjectItem(root, "stale");
    const cJSON *p;
    if (w5) {
        if ((p = cJSON_GetObjectItem(w5, "used")) && cJSON_IsNumber(p)) s_used_5h = p->valueint;
        if ((p = cJSON_GetObjectItem(w5, "limit")) && cJSON_IsNumber(p)) s_limit_5h = p->valueint;
        if ((p = cJSON_GetObjectItem(w5, "reset_local")) && cJSON_IsString(p) && p->valuestring)
            strlcpy(s_reset_5h, p->valuestring, sizeof(s_reset_5h));
    }
    if (wk) {
        if ((p = cJSON_GetObjectItem(wk, "used")) && cJSON_IsNumber(p)) s_used_wk = p->valueint;
        if ((p = cJSON_GetObjectItem(wk, "limit")) && cJSON_IsNumber(p)) s_limit_wk = p->valueint;
        if ((p = cJSON_GetObjectItem(wk, "reset_local")) && cJSON_IsString(p) && p->valuestring)
            strlcpy(s_reset_wk, p->valuestring, sizeof(s_reset_wk));
    }
    if (nt && cJSON_IsString(nt) && nt->valuestring) strlcpy(s_upd_time, nt->valuestring, sizeof(s_upd_time));
    if (lvl && cJSON_IsString(lvl) && lvl->valuestring) strlcpy(s_level, lvl->valuestring, sizeof(s_level));
    s_stale = cJSON_IsTrue(st);
    cJSON_Delete(root);
    if (s_stale) set_status(BAL_ONLINE, "%s stale %s", s_level, s_upd_time);
    else set_status(BAL_ONLINE, "%s upd %s", s_level, s_upd_time);
}

static void fetch_once(void)
{
    char buf[HTTP_BUF_SIZE];
    esp_http_client_config_t cfg = { .url = NET_SERVER_URL, .timeout_ms = 8000 };
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
        set_status(BAL_ERROR, "HTTP %d", code);
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
    if (s_wifi_started) { esp_wifi_stop(); s_wifi_started = false; }
    if (s_handlers_registered) {
        esp_event_handler_instance_unregister(IP_EVENT, IP_EVENT_STA_GOT_IP, s_got_ip_handler);
        esp_event_handler_instance_unregister(WIFI_EVENT, WIFI_EVENT_STA_DISCONNECTED, s_discon_handler);
        s_handlers_registered = false;
    }
    if (s_wifi_initialized) { esp_wifi_deinit(); s_wifi_initialized = false; }
    if (s_sta_netif) { esp_netif_destroy_default_wifi(s_sta_netif); s_sta_netif = NULL; }
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
    vTaskDelay(pdMS_TO_TICKS(100));
    if (s_wakeup) { vSemaphoreDelete(s_wakeup); s_wakeup = NULL; }
    s_task = NULL;
    wifi_stack_stop();
    return ESP_OK;
}

// 告警色语义与 PC 侧余额卡一致:>=70% 橙、>=90% 红,常态用传入的基础色。
static void set_bar(lv_obj_t *bar, lv_obj_t *pct, int used, int limit, uint32_t base_color)
{
    int ipct = limit > 0 ? (used * 100 + limit / 2) / limit : 0;
    if (ipct < 0) ipct = 0;
    if (ipct > 100) ipct = 100;
    uint32_t color = base_color;
    if (ipct >= 90) color = UI_RED;
    else if (ipct >= 70) color = UI_ORANGE;
    lv_bar_set_value(bar, ipct, LV_ANIM_OFF);
    lv_label_set_text_fmt(pct, "%d%%", ipct);
    lv_obj_set_style_bg_color(bar, lv_color_hex(color), LV_PART_INDICATOR);
}

static void tick(lv_timer_t *timer)
{
    (void)timer;
    if (!s_status) return;
    lv_label_set_text(s_status, s_status_text);
    if (s_state == BAL_ERROR) lv_obj_set_style_text_color(s_status, lv_color_hex(UI_RED), 0);
    else if (s_state == BAL_ONLINE && s_stale) lv_obj_set_style_text_color(s_status, lv_color_hex(UI_ORANGE), 0);
    else if (s_state == BAL_ONLINE) lv_obj_set_style_text_color(s_status, lv_color_hex(UI_GRASS_DARK), 0);
    else lv_obj_set_style_text_color(s_status, lv_color_hex(UI_SKY_DARK), 0);
    if (s_upd_label) lv_label_set_text(s_upd_label, s_upd_time);
    // 配额上限以服务端官方值为准;拿不到时回退编译期档位宏。
    int lim5 = s_limit_5h > 0 ? s_limit_5h : NET_PLAN_5H;
    int limw = s_limit_wk > 0 ? s_limit_wk : NET_PLAN_WEEK;
    lv_label_set_text_fmt(s_val5, "%d / %d", s_used_5h, lim5);
    lv_label_set_text_fmt(s_valw, "%d / %d", s_used_wk, limw);
    set_bar(s_bar5, s_pct5, s_used_5h, lim5, UI_GRASS);
    set_bar(s_barw, s_pctw, s_used_wk, limw, UI_SKY);
    lv_label_set_text_fmt(s_title5, "5H RESET %s", s_reset_5h[0] ? s_reset_5h : "--:--");
    lv_label_set_text_fmt(s_titlew, "7D RESET %s", s_reset_wk[0] ? s_reset_wk : "--:--");
}

// 面板内部几何:标题 y2(14px)、数值 y20(20px)、进度条 y46 h14(共 62px,
// 面板高 72 留 10px 余量,杜绝边框/内边距裁剪)。
static lv_obj_t *build_block(lv_obj_t *parent, const char *title, int y,
                             lv_obj_t **val, lv_obj_t **bar, lv_obj_t **pct,
                             lv_obj_t **title_out)
{
    lv_obj_t *panel = ui_pixel_panel_create(parent, 12, y, 216, 72, UI_PAPER);
    lv_obj_t *t = lv_label_create(panel);
    lv_obj_set_style_text_font(t, &lv_font_montserrat_14, 0);
    lv_obj_set_style_text_color(t, lv_color_hex(UI_SKY_DARK), 0);
    lv_obj_align(t, LV_ALIGN_TOP_LEFT, 4, 2);
    lv_label_set_text(t, title);
    if (title_out) *title_out = t;
    *val = lv_label_create(panel);
    lv_obj_set_style_text_font(*val, &lv_font_montserrat_20, 0);
    lv_obj_set_style_text_color(*val, lv_color_hex(UI_INK), 0);
    lv_obj_align(*val, LV_ALIGN_TOP_LEFT, 4, 20);
    lv_label_set_text(*val, "-- / --");
    *bar = lv_bar_create(panel);
    lv_obj_set_style_bg_color(*bar, lv_color_hex(UI_MUTED), 0);
    lv_obj_set_style_bg_opa(*bar, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(*bar, 0, 0);
    lv_bar_set_range(*bar, 0, 100);
    lv_obj_set_size(*bar, 132, 14);
    lv_obj_align(*bar, LV_ALIGN_BOTTOM_LEFT, 4, -4);
    *pct = lv_label_create(panel);
    lv_obj_set_style_text_font(*pct, &lv_font_montserrat_14, 0);
    lv_obj_set_style_text_color(*pct, lv_color_hex(UI_INK), 0);
    lv_obj_align(*pct, LV_ALIGN_BOTTOM_RIGHT, -6, -6);
    lv_label_set_text(*pct, "-%");
    return panel;
}

void demo_balance_enter(void)
{
    s_used_5h = s_limit_5h = s_used_wk = s_limit_wk = 0;
    s_reset_5h[0] = s_reset_wk[0] = '\0';
    strlcpy(s_level, "GLM", sizeof(s_level));
    s_stale = false;
    strlcpy(s_upd_time, "--:--", sizeof(s_upd_time));
    strlcpy(s_status_text, "starting...", sizeof(s_status_text));
    s_state = BAL_WIFI_CONNECTING;

    s_scr = ui_pixel_screen_create("BALANCE");
    // 截屏验证容器:240x192,内容整体收进来(截屏服务按容器渲染)
    lv_obj_t *content = lv_obj_create(s_scr);
    lv_obj_set_size(content, 240, 192);
    lv_obj_set_pos(content, 0, 0);
    lv_obj_set_style_bg_opa(content, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(content, 0, 0);
    lv_obj_set_style_pad_all(content, 0, 0);
    lv_obj_set_scrollbar_mode(content, LV_SCROLLBAR_MODE_OFF);
    serial_screenshot_set_target(content);

    build_block(content, "5H WINDOW", 10, &s_val5, &s_bar5, &s_pct5, &s_title5);
    build_block(content, "7D WINDOW", 96, &s_valw, &s_barw, &s_pctw, &s_titlew);

    s_status = lv_label_create(content);
    lv_obj_set_width(s_status, 216);
    lv_obj_set_style_text_font(s_status, &lv_font_montserrat_14, 0);
    lv_obj_set_style_text_color(s_status, lv_color_hex(UI_SKY_DARK), 0);
    lv_obj_align(s_status, LV_ALIGN_TOP_LEFT, 4, 168);
    lv_label_set_text(s_status, s_status_text);

    s_upd_label = lv_label_create(content);
    lv_obj_set_style_text_font(s_upd_label, &lv_font_montserrat_14, 0);
    lv_obj_set_style_text_color(s_upd_label, lv_color_hex(UI_INK), 0);
    lv_obj_align(s_upd_label, LV_ALIGN_TOP_RIGHT, -6, 168);
    lv_label_set_text(s_upd_label, s_upd_time);

    s_timer = lv_timer_create(tick, 250, NULL);
    lv_screen_load(s_scr);
}

void demo_balance_exit(void)
{
    serial_screenshot_set_target(NULL);
    if (s_timer) { lv_timer_delete(s_timer); s_timer = NULL; }
    if (s_scr) {
        lv_obj_delete(s_scr);
        s_scr = NULL;
        s_status = NULL;
        s_upd_label = NULL;
        s_val5 = s_bar5 = s_pct5 = NULL;
        s_valw = s_barw = s_pctw = NULL;
        s_title5 = s_titlew = NULL;
    }
}

void demo_balance_key(bsp_btn_t btn, bsp_btn_ev_t ev)
{
    if (btn != BSP_BTN_OK || ev != BSP_BTN_CLICK) return;
    if (s_wakeup) xSemaphoreGive(s_wakeup);
}
