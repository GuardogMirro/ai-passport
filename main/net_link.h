// main/net_link.h —— 数据页共享的 Wi-Fi STA 链路 + SNTP 对时。
// 从 demo_balance.c 的 Wi-Fi 生命周期泛化而来:同一套凭证(net_config.h)、
// RAM 存储(不落 NVS)、断线自动重连;GOT-IP 后启动 SNTP,给需要真实时间的
// 页面(理论节奏、时钟、天气)使用。
#pragma once

#include <stdbool.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef void (*net_link_cb_t)(void);

// 起链路:初始化并连接 STA(net_config.h 凭证),拿到 IP 后回调 on_got_ip
// (事件上下文,只做轻量动作,如释放唤醒信号量)并启动 SNTP 对时。
esp_err_t net_link_start(net_link_cb_t on_got_ip);

// 逆序拆卸链路(任务先于本调用停止)。
void net_link_stop(void);

// SNTP 是否已同步(time() 超过 2024 年即视为有效)。
bool net_link_time_valid(void);

#ifdef __cplusplus
}
#endif
