// main/wifi_pick.c -- Wi-Fi profile selection, pure logic (host-testable).
#include "wifi_pick.h"

#include <string.h>

int wifi_pick_best(const wifi_cred_t *creds, size_t count,
                   const char *const *ssids, const int16_t *rssis, size_t n)
{
    int best = -1;
    int16_t best_rssi = INT16_MIN;
    for (size_t i = 0; i < n; i++) {
        if (!ssids[i]) continue;
        for (size_t p = 0; p < count; p++) {
            if (strcmp(creds[p].ssid, ssids[i]) != 0) continue;
            // Higher rssi wins; equal rssi resolves to the lower stored
            // index so the outcome does not depend on scan order.
            if (best < 0 || rssis[i] > best_rssi ||
                (rssis[i] == best_rssi && (int)p < best)) {
                best = (int)p;
                best_rssi = rssis[i];
            }
            break;   // one scan entry matches at most one profile (upserted)
        }
    }
    return best;
}
