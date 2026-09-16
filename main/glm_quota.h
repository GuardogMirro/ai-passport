// main/glm_quota.h —— 智谱官方配额端点适配器(设备直连)。
// GET https://open.bigmodel.cn/api/monitor/usage/quota/limit(Bearer 套餐 key),
// 把 data.limits[](unit 3=小时窗 / 6=周窗)归一成扁平结构,并在设备端按
// PC 余额卡同款刻度算法算理论节奏(需要 SNTP 已对时,未对时 theo=-1)。
// key 来自 net_config.h 的 NET_BIGMODEL_KEY(git 忽略,与 Wi-Fi 凭证同路)。
#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    int used;            // 已用积分
    int limit;           // 窗口上限
    int pct;             // 官方已用百分比
    int theo;            // 理论节奏百分比;未对时时为 -1
    char reset_local[16]; // 重置时刻本地时间(小时窗 "HH:MM",周窗 "MM-DD HH:MM")
} glm_window_t;

typedef struct {
    bool ok;
    char level[8];       // 套餐档位("max" 等)
    char now_local[6];   // 取数时刻 "HH:MM"(需已对时,否则 "--:--")
    glm_window_t w5;     // 5 小时窗
    glm_window_t wk;     // 7 天窗
    char err[48];        // 失败原因(上屏用,不含敏感信息)
} glm_quota_t;

// 同步取一次;成功填 *q 并返回 ESP_OK。线程:工作任务(阻塞 ~数秒)。
esp_err_t glm_quota_fetch(glm_quota_t *q);

#ifdef __cplusplus
}
#endif
