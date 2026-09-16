// main/http_json.h —— 最小 HTTPS GET + Bearer + cJSON 解析,数据页共用。
#pragma once

#include "cJSON.h"

#ifdef __cplusplus
extern "C" {
#endif

// GET url(支持 https,走默认证书包校验),bearer 非空时加 Authorization 头;
// 响应体按 JSON 解析。成功返回根对象(调用方负责 cJSON_Delete),
// 失败返回 NULL(原因见串口日志:HTTP 状态码或解析错误)。
cJSON *http_json_get(const char *url, const char *bearer);

#ifdef __cplusplus
}
#endif
