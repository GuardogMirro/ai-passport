// main/net_link.c —— Wi-Fi STA 链路 + SNTP,数据页共用。
#include "net_link.h"

#include "demo_radio.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_netif_sntp.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>
#include <time.h>

#if __has_include("net_config.h")
#include "net_config.h"
#else
#include "net_config.defaults.h"
#endif

static const char *TAG = "net_link";

static esp_netif_t *s_sta;
static esp_event_handler_instance_t s_got_ip;
static esp_event_handler_instance_t s_discon;
static net_link_cb_t s_cb;
static bool s_wifi_init;
static bool s_wifi_started;
static bool s_handlers;
static bool s_sntp_init;

static void on_got_ip(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg; (void)base; (void)id;
    ip_event_got_ip_t *evt = (ip_event_got_ip_t *)data;
    ESP_LOGI(TAG, "got ip " IPSTR, IP2STR(&evt->ip_info.ip));
    if (!s_sntp_init) {
        esp_sntp_config_t cfg = ESP_NETIF_SNTP_DEFAULT_CONFIG("ntp.aliyun.com");
        esp_netif_sntp_init(&cfg);
        s_sntp_init = true;
    }
    if (s_cb) s_cb();
}

static void on_disconnected(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg; (void)base; (void)id; (void)data;
    ESP_LOGW(TAG, "wi-fi lost, reconnecting");
    esp_wifi_connect();
}

esp_err_t net_link_start(net_link_cb_t on_got_ip_cb)
{
    s_cb = on_got_ip_cb;
    esp_err_t err = demo_radio_nvs_prepare();
    if (err != ESP_OK) goto fail;
    err = demo_radio_network_prepare();
    if (err != ESP_OK) goto fail;
    s_sta = esp_netif_create_default_wifi_sta();
    if (!s_sta) { err = ESP_ERR_NO_MEM; goto fail; }
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    err = esp_wifi_init(&cfg);
    if (err != ESP_OK) goto fail;
    s_wifi_init = true;
    err = esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP,
                                              on_got_ip, NULL, &s_got_ip);
    if (err != ESP_OK) goto fail;
    err = esp_event_handler_instance_register(WIFI_EVENT, WIFI_EVENT_STA_DISCONNECTED,
                                              on_disconnected, NULL, &s_discon);
    if (err != ESP_OK) goto fail;
    s_handlers = true;
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
    // 省电模式保持默认:实测 WIFI_PS_NONE(全功率常开)会干扰 GPIO0 按键
    // ADC 采样,页面出现"幽灵 OK 长按"自动退回菜单(2026-09-16);而堆余量
    // 修好后(截屏缓冲改懒分配),默认省电下取数不再超时。
    err = esp_wifi_connect();
    if (err != ESP_OK) goto fail;
    return ESP_OK;
fail:
    ESP_LOGE(TAG, "net_link_start failed: %s", esp_err_to_name(err));
    net_link_stop();
    return err;
}

void net_link_stop(void)
{
    if (s_wifi_started) { esp_wifi_stop(); s_wifi_started = false; }
    if (s_handlers) {
        esp_event_handler_instance_unregister(IP_EVENT, IP_EVENT_STA_GOT_IP, s_got_ip);
        esp_event_handler_instance_unregister(WIFI_EVENT, WIFI_EVENT_STA_DISCONNECTED, s_discon);
        s_handlers = false;
    }
    if (s_wifi_init) { esp_wifi_deinit(); s_wifi_init = false; }
    if (s_sta) { esp_netif_destroy_default_wifi(s_sta); s_sta = NULL; }
    s_cb = NULL;
}

bool net_link_time_valid(void)
{
    return time(NULL) > 1700000000;  // 2023-11 之后即视为已对时
}
