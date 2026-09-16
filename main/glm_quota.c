// main/glm_quota.c —— 智谱官方配额端点的设备直连适配器。
#include "glm_quota.h"

#include "http_json.h"
#include "net_link.h"
#include "esp_log.h"
#include <stdio.h>
#include <string.h>
#include <time.h>

#if __has_include("net_config.h")
#include "net_config.h"
#else
#include "net_config.defaults.h"
#endif

#define GLM_QUOTA_URL "https://open.bigmodel.cn/api/monitor/usage/quota/limit"

static const char *TAG = "glm_quota";

static double jnum(const cJSON *obj, const char *key, double def)
{
    const cJSON *v = cJSON_GetObjectItem(obj, key);
    return cJSON_IsNumber(v) ? v->valuedouble : def;
}

// 北京时间(UTC+8)格式化,不依赖系统 TZ 设置。
static void fmt_cst(int64_t epoch_ms, bool with_date, char *out, int n)
{
    time_t t = (time_t)(epoch_ms / 1000) + 8 * 3600;
    struct tm tm;
    gmtime_r(&t, &tm);
    if (with_date) {
        snprintf(out, n, "%02d-%02d %02d:%02d", tm.tm_mon + 1, tm.tm_mday,
                 tm.tm_hour, tm.tm_min);
    } else {
        snprintf(out, n, "%02d:%02d", tm.tm_hour, tm.tm_min);
    }
}

// PC 余额卡同款理论节奏:窗口已过时间按刻度取整(小时窗 1h、周窗 12h,
// 开始的刻度就算),如 5h 窗过 49 分钟 -> 1/5 = 20%。
static int theory_pct(int unit, int number, int64_t reset_ms, int64_t now_ms)
{
    int64_t total, tick;
    if (unit == 3) { total = (int64_t)number * 3600000; tick = 3600000; }
    else if (unit == 6) { total = (int64_t)number * 7 * 24 * 3600000; tick = 12 * 3600000; }
    else return -1;
    int64_t elapsed = total - (reset_ms - now_ms);
    if (elapsed < 0) elapsed = 0;
    if (elapsed > total) elapsed = total;
    int64_t ticks = (elapsed + tick - 1) / tick;
    return (int)(ticks * tick * 100 / total);
}

static void fill_window(glm_window_t *w, const cJSON *L, int unit, int number,
                        int64_t now_ms)
{
    int64_t reset = (int64_t)jnum(L, "nextResetTime", 0);
    w->used = (int)jnum(L, "currentValue", 0);
    w->limit = (int)jnum(L, "usage", 0);
    w->pct = (int)jnum(L, "percentage", 0);
    w->theo = net_link_time_valid() ? theory_pct(unit, number, reset, now_ms) : -1;
    fmt_cst(reset, unit == 6, w->reset_local, sizeof(w->reset_local));
}

esp_err_t glm_quota_fetch(glm_quota_t *q)
{
    memset(q, 0, sizeof(*q));
    q->w5.theo = q->wk.theo = -1;

    cJSON *root = http_json_get(GLM_QUOTA_URL, NET_BIGMODEL_KEY);
    if (!root) {
        strlcpy(q->err, "网络或服务错误", sizeof(q->err));
        return ESP_FAIL;
    }
    const cJSON *ok = cJSON_GetObjectItem(root, "success");
    const cJSON *data = cJSON_GetObjectItem(root, "data");
    const cJSON *limits = data ? cJSON_GetObjectItem(data, "limits") : NULL;
    if (!cJSON_IsTrue(ok) || !cJSON_IsArray(limits)) {
        strlcpy(q->err, "接口响应异常", sizeof(q->err));
        cJSON_Delete(root);
        return ESP_FAIL;
    }
    const cJSON *lvl = cJSON_GetObjectItem(data, "level");
    if (cJSON_IsString(lvl) && lvl->valuestring) {
        strlcpy(q->level, lvl->valuestring, sizeof(q->level));
    }
    int64_t now_ms = (int64_t)time(NULL) * 1000;
    bool got5 = false, gotw = false;
    const cJSON *L;
    cJSON_ArrayForEach(L, limits) {
        int unit = (int)jnum(L, "unit", -1);
        int number = (int)jnum(L, "number", 1);
        if (unit == 3 && !got5) {
            fill_window(&q->w5, L, unit, number, now_ms);
            got5 = true;
        } else if (unit == 6 && !gotw) {
            fill_window(&q->wk, L, unit, number, now_ms);
            gotw = true;
        }
    }
    cJSON_Delete(root);
    if (!got5 || !gotw) {
        strlcpy(q->err, "窗口数据缺失", sizeof(q->err));
        return ESP_FAIL;
    }
    if (net_link_time_valid()) {
        fmt_cst(now_ms, false, q->now_local, sizeof(q->now_local));
    } else {
        strlcpy(q->now_local, "--:--", sizeof(q->now_local));
    }
    q->ok = true;
    ESP_LOGI(TAG, "quota ok: level=%s 5h=%d/%d theo=%d wk=%d/%d theo=%d",
             q->level, q->w5.used, q->w5.limit, q->w5.theo,
             q->wk.used, q->wk.limit, q->wk.theo);
    return ESP_OK;
}
