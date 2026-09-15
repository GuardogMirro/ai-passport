// main/serial_screenshot.c —— FAP_SCREENSHOT_V1 串口截屏协议(设备侧)。
// 主机经 USB-CDC 发送 "FAP_SCREENSHOT_V1",本机回传整屏 RGB565 小端像素。
// 实现要点来自 docs/reference/y2lin/serial-screenshot-protocol.md:
// 显式安装 usb_serial_jtag 驱动、读任务低优先级并让出 CPU、子串匹配命令、
// 静态预留整屏缓冲、512 字节以下分块发送、传输窗口内静音日志、失败不回包。
#include "serial_screenshot.h"

#include "bsp_display.h"
#include "driver/usb_serial_jtag.h"
#include "esp_heap_caps.h"
#include "driver/usb_serial_jtag_vfs.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "lvgl.h"
#include "lv_async.h"
#include "lv_snapshot.h"
#include <stdio.h>
#include <string.h>

#define SNAP_W 240
#define SNAP_H 192   // 内存预算内可整块分配的高度(92KB < 最大连续块)
#define SNAP_BYTES (SNAP_W * SNAP_H * 2)
#define SNAP_CHUNK 128          // 须小于 tx 环形缓冲容量
#define CMD "FAP_SCREENSHOT_V1"
#define CMD_LEN (sizeof(CMD) - 1)

static uint8_t *s_snap_buf;   // 运行时从内部堆分配,失败按协议静默放弃
static char s_win[CMD_LEN * 2];
static lv_obj_t *s_target;
static int s_win_len;


static SemaphoreHandle_t s_render_done;
static volatile lv_result_t s_render_result;

// 在 LVGL 任务上下文内执行渲染(lv_async_call 回调),避免外部任务持锁渲染。
static void render_in_lvgl(void *arg)
{
    lv_obj_t *obj = (lv_obj_t *)arg;
    lv_draw_buf_t db;
    lv_draw_buf_init(&db, SNAP_W, SNAP_H, LV_COLOR_FORMAT_RGB565, 0,
                     s_snap_buf, SNAP_BYTES);
    s_render_result = lv_snapshot_take_to_draw_buf(obj, LV_COLOR_FORMAT_RGB565, &db);
    if (s_render_done) xSemaphoreGive(s_render_done);
}

static void send_screenshot(void)
{

    if (!s_snap_buf) {
        s_snap_buf = heap_caps_malloc(SNAP_BYTES, MALLOC_CAP_INTERNAL);
    }
    if (!s_snap_buf) {
        ESP_LOGW("snap", "no contiguous %d bytes: largest=%u free=%u", SNAP_BYTES,
                 (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL),
                 (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL));
        return;
    }


    lv_obj_t *obj = s_target ? s_target : lv_screen_active();
    int32_t ow = lv_obj_get_width(obj);
    int32_t oh = lv_obj_get_height(obj);
    if (ow > SNAP_W || oh > SNAP_H) {
        ESP_LOGW("snap", "target %ldx%ld exceeds buffer %dx%d", (long)ow, (long)oh, SNAP_W, SNAP_H);
        return;
    }

    if (!s_render_done) s_render_done = xSemaphoreCreateBinary();
    xSemaphoreTake(s_render_done, 0);
    s_render_result = LV_RESULT_INVALID;
    if (lv_async_call(render_in_lvgl, obj) != LV_RESULT_OK) {
        ESP_LOGW("snap", "async call failed");
        return;
    }
    if (!xSemaphoreTake(s_render_done, pdMS_TO_TICKS(3000))) {
        ESP_LOGW("snap", "render timeout");
        return;
    }
    lv_result_t r = s_render_result;

    if (r != LV_RESULT_OK) {
        ESP_LOGW("snap", "snapshot render failed");
        return;
    }

    esp_log_level_t prev = esp_log_level_get("*");
    esp_log_level_set("*", ESP_LOG_NONE);
    char hdr[64];
    int hl = snprintf(hdr, sizeof(hdr), "FAP_SCREENSHOT_V1 %d %d RGB565LE %d\n",
                      SNAP_W, SNAP_H, SNAP_BYTES);

    usb_serial_jtag_write_bytes((const uint8_t *)hdr, hl, pdMS_TO_TICKS(1000));

    for (int off = 0; off < SNAP_BYTES; off += SNAP_CHUNK) {
        int n = (SNAP_BYTES - off) > SNAP_CHUNK ? SNAP_CHUNK : (SNAP_BYTES - off);
        int wr = usb_serial_jtag_write_bytes(s_snap_buf + off, n, pdMS_TO_TICKS(1500));
        if (wr < n) break;
    }
    esp_log_level_set("*", prev);

}

static void snap_task(void *arg)
{
    (void)arg;
    usb_serial_jtag_driver_config_t cfg = USB_SERIAL_JTAG_DRIVER_CONFIG_DEFAULT();
    if (usb_serial_jtag_driver_install(&cfg) == ESP_OK) {
        usb_serial_jtag_vfs_use_driver();
    }
    vTaskDelay(pdMS_TO_TICKS(500));
    uint8_t byte;
    for (;;) {
        int n = usb_serial_jtag_read_bytes(&byte, 1, pdMS_TO_TICKS(200));
        if (n == 1) {
            if (byte == '\n' || byte == '\r') {
                s_win_len = 0;
            } else if (s_win_len < (int)sizeof(s_win) - 1) {
                s_win[s_win_len++] = (char)byte;
                s_win[s_win_len] = 0;
                if (s_win_len >= (int)CMD_LEN &&
                    memcmp(s_win + s_win_len - CMD_LEN, CMD, CMD_LEN) == 0) {
                    s_win_len = 0;
                    send_screenshot();
                }
            } else {
                memmove(s_win, s_win + 1, s_win_len - 1);
                s_win[CMD_LEN * 2 - 2] = (char)byte;
                if (memcmp(s_win + s_win_len - 1 - CMD_LEN, CMD, CMD_LEN) == 0) {
                    s_win_len = 0;
                    send_screenshot();
                }
            }
        } else {
            vTaskDelay(pdMS_TO_TICKS(100));   // 无数据/出错都退避,勿忙等(踩过坑:超时返回 0 也算)
        }
    }
}

void serial_screenshot_init(void)
{
    // 开机早期(Wi-Fi/HTTP 尚未启动、堆最完整时)一次性预留整屏缓冲。
    s_snap_buf = heap_caps_malloc(SNAP_BYTES, MALLOC_CAP_INTERNAL);
    ESP_LOGI("snap", "buffer=%p largest_free=%u",
             s_snap_buf, (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL));
    xTaskCreate(snap_task, "snap_shot", 8192, NULL, 3, NULL);
}

void serial_screenshot_set_target(lv_obj_t *target)
{
    s_target = target;
}
