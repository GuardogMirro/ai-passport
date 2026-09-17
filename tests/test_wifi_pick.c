// tests/test_wifi_pick.c -- host tests for wifi_pick_best (no ESP-IDF).
#include <stdio.h>
#include <string.h>

#include "wifi_pick.h"

static int failures;

#define CHECK(cond, name) do { \
    if (cond) { printf("ok   %s\n", name); } \
    else { printf("FAIL %s\n", name); failures++; } \
} while (0)

int main(void)
{
    wifi_cred_t creds[3];
    memset(creds, 0, sizeof(creds));
    strcpy(creds[0].ssid, "office");
    strcpy(creds[1].ssid, "home");
    strcpy(creds[2].ssid, "phone");

    // 1. strongest match wins across profiles
    {
        const char *ss[] = { "office", "home" };
        const int16_t rr[] = { -70, -55 };
        CHECK(wifi_pick_best(creds, 3, ss, rr, 2) == 1, "stronger AP wins");
    }
    // 2. no match -> -1
    {
        const char *ss[] = { "neighbour", "other" };
        const int16_t rr[] = { -40, -50 };
        CHECK(wifi_pick_best(creds, 3, ss, rr, 2) == -1, "no match -> -1");
    }
    // 3. empty scan -> -1
    {
        CHECK(wifi_pick_best(creds, 3, NULL, NULL, 0) == -1, "empty scan -> -1");
    }
    // 4. rssi tie -> lower stored index, regardless of scan order
    {
        const char *ss[] = { "home", "office" };
        const int16_t rr[] = { -60, -60 };
        CHECK(wifi_pick_best(creds, 3, ss, rr, 2) == 0, "tie -> first stored");
    }
    // 5. duplicate scan entries for one SSID pick that profile
    {
        const char *ss[] = { "home", "home", "office" };
        const int16_t rr[] = { -80, -50, -45 };
        CHECK(wifi_pick_best(creds, 3, ss, rr, 3) == 1, "dup scan entries");
    }
    // 6. NULL scan entry is skipped
    {
        const char *ss[] = { NULL, "office" };
        const int16_t rr[] = { -30, -90 };
        CHECK(wifi_pick_best(creds, 3, ss, rr, 2) == 0, "NULL ssid skipped");
    }
    // 7. zero profiles -> -1 even with matches
    {
        const char *ss[] = { "office" };
        const int16_t rr[] = { -30 };
        CHECK(wifi_pick_best(creds, 0, ss, rr, 1) == -1, "no profiles -> -1");
    }

    if (failures) {
        printf("%d failure(s)\n", failures);
        return 1;
    }
    printf("wifi_pick tests: PASS\n");
    return 0;
}
