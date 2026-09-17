// main/wifi_store.h -- persistent multi-profile Wi-Fi credentials (NVS).
#pragma once

#include "wifi_pick.h"

#include "esp_err.h"

// Load all stored profiles. On the very first run (store empty) the
// compiled-in credentials from net_config.h are seeded in, so an
// already-flashed device migrates to the store without reconfiguration.
esp_err_t wifi_store_load(wifi_store_t *store);

// Insert or update (same SSID replaces the password). Returns ESP_ERR_NO_MEM
// when the store is full. SSID/pass length limits: see wifi_pick.h.
esp_err_t wifi_store_add(const char *ssid, const char *pass);

esp_err_t wifi_store_del(const char *ssid);
