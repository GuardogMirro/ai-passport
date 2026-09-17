// main/wifi_pick.h -- Wi-Fi profile selection, pure logic (host-testable).
#pragma once

#include <stddef.h>
#include <stdint.h>

#define WIFI_STORE_MAX 8
#define WIFI_SSID_MAX 33   // 802.11 limit 32 octets + NUL
#define WIFI_PASS_MAX 64   // WPA2 passphrase limit 63 chars + NUL

typedef struct {
    char ssid[WIFI_SSID_MAX];
    char pass[WIFI_PASS_MAX];
} wifi_cred_t;

typedef struct {
    wifi_cred_t creds[WIFI_STORE_MAX];
    size_t count;
} wifi_store_t;

// Pick the stored profile that matches the strongest scanned AP.
// creds: stored profiles (count entries); ssids/rssis: scan results (n entries).
// Returns the index into creds, or -1 when no scan result matches any profile.
// Ties on rssi resolve to the lower stored index (stable, office-first ordering).
int wifi_pick_best(const wifi_cred_t *creds, size_t count,
                   const char *const *ssids, const int16_t *rssis, size_t n);
