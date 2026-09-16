// main/http_json.c —— HTTPS GET + Bearer + cJSON。
// 响应体限制在 HTTP_BUF_SIZE 内(任务栈缓冲),余额接口实测 ~600B,余量充足。
#include "http_json.h"

#include "esp_crt_bundle.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_system.h"
#include <string.h>

#define HTTP_BUF_SIZE 2048
#define HTTP_TIMEOUT_MS 10000

static const char *TAG = "http_json";

cJSON *http_json_get(const char *url, const char *bearer)
{
    // 无 PSRAM、92KB 截屏缓冲常驻:TLS 缓冲必须用小档(sdkconfig.defaults 里
    // IN/OUT=4096/1024),这行日志用来核对取数时的堆余量。
    ESP_LOGI(TAG, "free heap %u bytes", (unsigned)esp_get_free_heap_size());
    char buf[HTTP_BUF_SIZE];
    esp_http_client_config_t cfg = {
        .url = url,
        .timeout_ms = HTTP_TIMEOUT_MS,
        .crt_bundle_attach = esp_crt_bundle_attach,
    };
    ESP_LOGI(TAG, "GET %s%s", url, (bearer && bearer[0]) ? " (auth)" : "");

    esp_http_client_handle_t cl = esp_http_client_init(&cfg);
    if (!cl) { ESP_LOGE(TAG, "client init failed"); return NULL; }
    if (bearer && bearer[0]) {
        char auth[600];
        snprintf(auth, sizeof(auth), "Bearer %s", bearer);
        esp_http_client_set_header(cl, "Authorization", auth);
    }
    esp_err_t err = esp_http_client_open(cl, 0);
    int len = 0, code = 0;
    if (err == ESP_OK) {
        esp_http_client_fetch_headers(cl);
        int r;
        while (len < (int)sizeof(buf) - 1 &&
               (r = esp_http_client_read(cl, buf + len, sizeof(buf) - 1 - len)) > 0) {
            len += r;
        }
        buf[len] = 0;
        code = esp_http_client_get_status_code(cl);
        esp_http_client_close(cl);
    }
    esp_http_client_cleanup(cl);
    ESP_LOGI(TAG, "code=%d len=%d", code, len);
    if (code != 200 || len <= 0) {
        ESP_LOGE(TAG, "http failed: code=%d len=%d", code, len);
        return NULL;
    }
    cJSON *root = cJSON_Parse(buf);
    if (!root) ESP_LOGE(TAG, "json parse failed (%d bytes)", len);
    return root;
}
