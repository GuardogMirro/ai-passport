// main/net_config.defaults.h -- committed fallback used when the git-ignored
// net_config.h (real credentials) is absent, e.g. in CI. Never put secrets here.
#pragma once

#define NET_WIFI_SSID "SET-ME"
#define NET_WIFI_PASS "SET-ME"
#define NET_BIGMODEL_KEY "SET-ME"

// Balance page settings.
#define NET_SERVER_URL "http://192.168.1.37:8765/balance"
// Plan quotas for display: Lite 2000/10000, Pro 12000/60000, Max 28000/140000.
#define NET_PLAN_5H 28000
#define NET_PLAN_WEEK 140000
