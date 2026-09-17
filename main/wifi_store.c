// main/wifi_store.c -- persistent multi-profile Wi-Fi credentials (NVS).
// Layout: namespace "wifistore", key "n" = profile count (u8),
// keys "c0".."c7" = blob {ssid[]\0pass[]\0} (wifi_cred_t as written,
// trailing bytes zero-padded). Deleting compacts the remaining entries.
#include "wifi_store.h"

#include "esp_log.h"
#include "nvs.h"
#include "nvs_flash.h"
#include <string.h>

#if __has_include("net_config.h")
#include "net_config.h"
#else
#include "net_config.defaults.h"
#endif

static const char *TAG = "wifi_store";
static const char *NS = "wifistore";

static esp_err_t store_save_all(nvs_handle_t h, const wifi_store_t *ws)
{
    esp_err_t err = nvs_set_u8(h, "n", (uint8_t)ws->count);
    if (err != ESP_OK) return err;
    for (size_t i = 0; i < ws->count; i++) {
        char key[] = { 'c', (char)('0' + i), 0 };
        err = nvs_set_blob(h, key, &ws->creds[i], sizeof(ws->creds[i]));
        if (err != ESP_OK) return err;
    }
    // Clear slots left behind by a delete/compact (NOT_FOUND is fine).
    for (size_t i = ws->count; i < WIFI_STORE_MAX; i++) {
        char key[] = { 'c', (char)('0' + i), 0 };
        esp_err_t e2 = nvs_erase_key(h, key);
        (void)e2;
    }
    return nvs_commit(h);
}

esp_err_t wifi_store_load(wifi_store_t *ws)
{
    memset(ws, 0, sizeof(*ws));
    nvs_handle_t h;
    esp_err_t err = nvs_open(NS, NVS_READWRITE, &h);
    if (err != ESP_OK) return err;

    uint8_t n = 0;
    err = nvs_get_u8(h, "n", &n);
    if (err == ESP_ERR_NVS_NOT_FOUND) n = 0;
    else if (err != ESP_OK) { nvs_close(h); return err; }
    if (n > WIFI_STORE_MAX) n = WIFI_STORE_MAX;

    for (size_t i = 0; i < n; i++) {
        char key[] = { 'c', (char)('0' + i), 0 };
        size_t len = sizeof(ws->creds[i]);
        err = nvs_get_blob(h, key, &ws->creds[i], &len);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "profile %u unreadable: %s", (unsigned)i, esp_err_to_name(err));
            ws->count = 0;   // corrupt store: start over rather than half-load
            nvs_close(h);
            return ESP_OK;
        }
        ws->count++;
    }

    // First run: seed the compiled-in credentials (when they are real).
    if (ws->count == 0 && strlen(NET_WIFI_SSID) + 1 <= WIFI_SSID_MAX &&
        strcmp(NET_WIFI_SSID, "SET-ME") != 0) {
        strlcpy(ws->creds[0].ssid, NET_WIFI_SSID, WIFI_SSID_MAX);
        strlcpy(ws->creds[0].pass, NET_WIFI_PASS, WIFI_PASS_MAX);
        ws->count = 1;
        err = store_save_all(h, ws);
        if (err != ESP_OK) ESP_LOGW(TAG, "seed save failed: %s", esp_err_to_name(err));
        else ESP_LOGI(TAG, "seeded compiled profile '%s'", NET_WIFI_SSID);
    }

    nvs_close(h);
    ESP_LOGI(TAG, "loaded %u profile(s)", (unsigned)ws->count);
    return ESP_OK;
}

esp_err_t wifi_store_add(const char *ssid, const char *pass)
{
    if (!ssid || !*ssid || !pass) return ESP_ERR_INVALID_ARG;
    if (strlen(ssid) >= WIFI_SSID_MAX || strlen(pass) >= WIFI_PASS_MAX)
        return ESP_ERR_INVALID_SIZE;

    wifi_store_t ws;
    memset(&ws, 0, sizeof(ws));
    esp_err_t err = wifi_store_load(&ws);
    if (err != ESP_OK) return err;

    size_t slot = ws.count;   // upsert: replace in place when SSID exists
    for (size_t i = 0; i < ws.count; i++) {
        if (strcmp(ws.creds[i].ssid, ssid) == 0) { slot = i; break; }
    }
    if (slot == ws.count) {
        if (ws.count >= WIFI_STORE_MAX) return ESP_ERR_NO_MEM;
        ws.count++;
    }
    strlcpy(ws.creds[slot].ssid, ssid, WIFI_SSID_MAX);
    strlcpy(ws.creds[slot].pass, pass, WIFI_PASS_MAX);

    nvs_handle_t h;
    err = nvs_open(NS, NVS_READWRITE, &h);
    if (err != ESP_OK) return err;
    err = store_save_all(h, &ws);
    nvs_close(h);
    if (err == ESP_OK) ESP_LOGI(TAG, "stored profile '%s' (%u total)", ssid, (unsigned)ws.count);
    return err;
}

esp_err_t wifi_store_del(const char *ssid)
{
    wifi_store_t ws;
    memset(&ws, 0, sizeof(ws));
    esp_err_t err = wifi_store_load(&ws);
    if (err != ESP_OK) return err;

    size_t keep = 0;
    for (size_t i = 0; i < ws.count; i++) {
        if (strcmp(ws.creds[i].ssid, ssid) == 0) continue;
        ws.creds[keep++] = ws.creds[i];
    }
    if (keep == ws.count) return ESP_ERR_NOT_FOUND;
    ws.count = keep;

    nvs_handle_t h;
    err = nvs_open(NS, NVS_READWRITE, &h);
    if (err != ESP_OK) return err;
    err = store_save_all(h, &ws);
    nvs_close(h);
    if (err == ESP_OK) ESP_LOGI(TAG, "removed profile '%s' (%u left)", ssid, (unsigned)ws.count);
    return err;
}
