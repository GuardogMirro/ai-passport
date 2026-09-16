// main/demo_balance_direct.c -- GENERATED from tools/ui_spec/pages/balance_direct.json by
// tools/ui_spec/gen_page.py. Do not edit by hand: change the spec, re-run the
// generator, re-render the preview and diff it against a device capture.
#include "demo.h"
#include "bsp_display.h"   // bsp_lvgl_lock: key()/task run without the lock
#include "ui_pixel.h"
#include "serial_screenshot.h"
#include "glm_quota.h"
#include "net_link.h"
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include <string.h>
#include "lvgl.h"

static lv_obj_t *s_scr;
static lv_obj_t *s_content;
static SemaphoreHandle_t s_wakeup;
static TaskHandle_t s_task;
static volatile bool s_running;
static lv_obj_t *blk0;
static lv_obj_t *lbl0;
static lv_obj_t *val0;
static lv_obj_t *bar0;
static lv_obj_t *mk0;
static lv_obj_t *blk1;
static lv_obj_t *lbl1;
static lv_obj_t *val1;
static lv_obj_t *bar1;
static lv_obj_t *mk1;
static lv_obj_t *stl;
static lv_obj_t *str;
// 与 PC 余额卡同款告警语义:超理论橙,>=90% 或超理论 20 个百分点红。
static uint32_t warn_color(int pct, int theo, uint32_t base)
{
    if (pct >= 90 || (theo >= 0 && pct - theo >= 20)) return UI_RED;
    if (theo >= 0 && pct > theo) return UI_ORANGE;
    return base;
}

// 取数成功:把窗口数据落到控件(跨任务,持 LVGL 锁)。
// theo 未对时为 -1:数值显示 --,刻度线隐藏。
static void apply_data(const glm_quota_t *q)
{
    char t5[16], tw[16], state[48];
    if (q->w5.theo >= 0) snprintf(t5, sizeof(t5), "%d", q->w5.theo);
    else strlcpy(t5, "--", sizeof(t5));
    if (q->wk.theo >= 0) snprintf(tw, sizeof(tw), "%d", q->wk.theo);
    else strlcpy(tw, "--", sizeof(tw));
    snprintf(state, sizeof(state), "在线 %s", q->level);

    if (!bsp_lvgl_lock(500)) return;
    lv_label_set_text_fmt(val0, "%d%% / %s%%", q->w5.pct, t5);
    lv_bar_set_value(bar0, q->w5.pct, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(bar0, lv_color_hex(warn_color(q->w5.pct, q->w5.theo, UI_GRASS)), LV_PART_INDICATOR);
    lv_label_set_text_fmt(lbl0, "5小时窗 重置 %s", q->w5.reset_local);
    if (q->w5.theo >= 0) {
        lv_obj_set_pos(mk0, 4 + q->w5.theo * 132 / 100, 39);
        lv_obj_clear_flag(mk0, LV_OBJ_FLAG_HIDDEN);
    } else {
        lv_obj_add_flag(mk0, LV_OBJ_FLAG_HIDDEN);
    }
    lv_label_set_text_fmt(val1, "%d%% / %s%%", q->wk.pct, tw);
    lv_bar_set_value(bar1, q->wk.pct, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(bar1, lv_color_hex(warn_color(q->wk.pct, q->wk.theo, UI_SKY)), LV_PART_INDICATOR);
    lv_label_set_text_fmt(lbl1, "7天窗 重置 %s", q->wk.reset_local);
    if (q->wk.theo >= 0) {
        lv_obj_set_pos(mk1, 4 + q->wk.theo * 132 / 100, 39);
        lv_obj_clear_flag(mk1, LV_OBJ_FLAG_HIDDEN);
    } else {
        lv_obj_add_flag(mk1, LV_OBJ_FLAG_HIDDEN);
    }
    lv_label_set_text_fmt(stl, "%s", state);
    lv_obj_set_style_text_color(stl, lv_color_hex(UI_GRASS_DARK), 0);
    lv_label_set_text_fmt(str, "更新 %s", q->now_local);
    bsp_lvgl_unlock();
}

// 取数失败:状态行红字显示原因(其余控件保持上次值)。
static void apply_error(const char *msg)
{
    if (!stl) return;
    if (!bsp_lvgl_lock(500)) return;
    lv_label_set_text(stl, msg);
    lv_obj_set_style_text_color(stl, lv_color_hex(UI_RED), 0);
    bsp_lvgl_unlock();
}

// 过渡态(对时中等):状态行蓝灰字,与成功(绿)/失败(红)区分。
static void apply_status(const char *msg)
{
    if (!stl) return;
    if (!bsp_lvgl_lock(500)) return;
    lv_label_set_text(stl, msg);
    lv_obj_set_style_text_color(stl, lv_color_hex(UI_SKY_DARK), 0);
    bsp_lvgl_unlock();
}

// 拉数据:GOT-IP 或周期到点唤醒。取数前必须等 SNTP 对时:TLS 证书
// 验证依赖正确时间,未对时就请求必失败,页面表现为"网络或服务错误"
// (2026-09-16 排障:间歇性报错的根源)。最多等 30 秒,期间状态行提示
// 对时中;仍未对上则跳过本轮取数,下个周期(或手动刷新)再试。
static void fetch_task(void *arg)
{
    (void)arg;
    while (s_running) {
        xSemaphoreTake(s_wakeup, pdMS_TO_TICKS(300000));
        if (!s_running) break;
        if (!net_link_time_valid()) apply_status("对时中…");
        for (int i = 0; i < 300 && s_running && !net_link_time_valid(); i++) {
            vTaskDelay(pdMS_TO_TICKS(100));
        }
        if (!s_running) break;
        if (!net_link_time_valid()) {
            apply_error("对时未成,稍后重试");
            continue;
        }
        glm_quota_t q;
        if (glm_quota_fetch(&q) == ESP_OK) apply_data(&q);
        else apply_error(q.err[0] ? q.err : "取数失败");
    }
    vTaskDelete(NULL);
}

static void on_got_ip(void)
{
    if (s_wakeup) xSemaphoreGive(s_wakeup);
}

esp_err_t demo_balance_direct_start(void)
{
    s_wakeup = xSemaphoreCreateBinary();
    if (!s_wakeup) return ESP_ERR_NO_MEM;
    esp_err_t err = net_link_start(on_got_ip);
    if (err != ESP_OK) {
        vSemaphoreDelete(s_wakeup);
        s_wakeup = NULL;
        return err;
    }
    s_running = true;
    if (xTaskCreate(fetch_task, "data_fetch", 8192, NULL, 4, &s_task) != pdPASS) {
        s_running = false;
        net_link_stop();
        vSemaphoreDelete(s_wakeup);
        s_wakeup = NULL;
        return ESP_ERR_NO_MEM;
    }
    return ESP_OK;
}

esp_err_t demo_balance_direct_stop(void)
{
    s_running = false;
    if (s_wakeup) xSemaphoreGive(s_wakeup);
    vTaskDelay(pdMS_TO_TICKS(100));   // 让任务先退出,再拆链路
    if (s_wakeup) { vSemaphoreDelete(s_wakeup); s_wakeup = NULL; }
    s_task = NULL;
    net_link_stop();
    return ESP_OK;
}

void demo_balance_direct_enter(void)
{
    s_scr = ui_pixel_screen_create_font("余额直连", ui_pixel_font_title());

    // 截屏验证容器:内容与容器同坐标,截屏服务按容器渲染。
    // 起点 y48 避开标题牌(y8-41,投影到 y45)。
    s_content = lv_obj_create(s_scr);
    lv_obj_set_size(s_content, 240, 192);
    lv_obj_set_pos(s_content, 0, 48);
    lv_obj_set_style_bg_opa(s_content, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(s_content, 0, 0);
    lv_obj_set_style_pad_all(s_content, 0, 0);
    lv_obj_set_scrollbar_mode(s_content, LV_SCROLLBAR_MODE_OFF);
    serial_screenshot_set_target(s_content);

    blk0 = ui_pixel_panel_create(s_content, 12, 8, 216, 78, UI_PAPER);
    lbl0 = lv_label_create(blk0);
    lv_obj_set_style_text_font(lbl0, ui_pixel_font_body(), 0);
    lv_obj_set_style_text_color(lbl0, lv_color_hex(UI_SKY_DARK), 0);
    lv_obj_align(lbl0, LV_ALIGN_TOP_LEFT, 4, 1);
    lv_label_set_text(lbl0, "5小时窗 重置 {{w5.reset}}");
    val0 = lv_label_create(blk0);
    lv_obj_set_style_text_font(val0, ui_pixel_font_title(), 0);
    lv_obj_set_style_text_color(val0, lv_color_hex(UI_INK), 0);
    lv_obj_align(val0, LV_ALIGN_TOP_LEFT, 4, 15);
    lv_label_set_text(val0, "{{w5.pct}}% / {{w5.theo}}%");
    bar0 = lv_bar_create(blk0);
    lv_obj_set_style_bg_color(bar0, lv_color_hex(UI_MUTED), 0);
    lv_obj_set_style_bg_opa(bar0, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(bar0, 0, 0);
    lv_obj_set_style_radius(bar0, 7, 0);
    lv_obj_set_style_radius(bar0, 7, LV_PART_INDICATOR);
    lv_bar_set_range(bar0, 0, 100);
    lv_obj_set_size(bar0, 132, 14);
    lv_obj_align(bar0, LV_ALIGN_BOTTOM_LEFT, 4, -3);
    lv_bar_set_value(bar0, 0, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(bar0, lv_color_hex(UI_GRASS), LV_PART_INDICATOR);
    mk0 = lv_obj_create(blk0);
    lv_obj_remove_flag(mk0, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_size(mk0, 2, 14);
    lv_obj_set_pos(mk0, 4, 39);
    lv_obj_add_flag(mk0, LV_OBJ_FLAG_HIDDEN);
    lv_obj_set_style_radius(mk0, 0, 0);
    lv_obj_set_style_border_width(mk0, 0, 0);
    lv_obj_set_style_pad_all(mk0, 0, 0);
    lv_obj_set_style_bg_color(mk0, lv_color_hex(UI_INK), 0);
    lv_obj_set_style_bg_opa(mk0, LV_OPA_COVER, 0);

    blk1 = ui_pixel_panel_create(s_content, 12, 92, 216, 78, UI_PAPER);
    lbl1 = lv_label_create(blk1);
    lv_obj_set_style_text_font(lbl1, ui_pixel_font_body(), 0);
    lv_obj_set_style_text_color(lbl1, lv_color_hex(UI_SKY_DARK), 0);
    lv_obj_align(lbl1, LV_ALIGN_TOP_LEFT, 4, 1);
    lv_label_set_text(lbl1, "7天窗 重置 {{wk.reset}}");
    val1 = lv_label_create(blk1);
    lv_obj_set_style_text_font(val1, ui_pixel_font_title(), 0);
    lv_obj_set_style_text_color(val1, lv_color_hex(UI_INK), 0);
    lv_obj_align(val1, LV_ALIGN_TOP_LEFT, 4, 15);
    lv_label_set_text(val1, "{{wk.pct}}% / {{wk.theo}}%");
    bar1 = lv_bar_create(blk1);
    lv_obj_set_style_bg_color(bar1, lv_color_hex(UI_MUTED), 0);
    lv_obj_set_style_bg_opa(bar1, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(bar1, 0, 0);
    lv_obj_set_style_radius(bar1, 7, 0);
    lv_obj_set_style_radius(bar1, 7, LV_PART_INDICATOR);
    lv_bar_set_range(bar1, 0, 100);
    lv_obj_set_size(bar1, 132, 14);
    lv_obj_align(bar1, LV_ALIGN_BOTTOM_LEFT, 4, -3);
    lv_bar_set_value(bar1, 0, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(bar1, lv_color_hex(UI_SKY), LV_PART_INDICATOR);
    mk1 = lv_obj_create(blk1);
    lv_obj_remove_flag(mk1, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_size(mk1, 2, 14);
    lv_obj_set_pos(mk1, 4, 39);
    lv_obj_add_flag(mk1, LV_OBJ_FLAG_HIDDEN);
    lv_obj_set_style_radius(mk1, 0, 0);
    lv_obj_set_style_border_width(mk1, 0, 0);
    lv_obj_set_style_pad_all(mk1, 0, 0);
    lv_obj_set_style_bg_color(mk1, lv_color_hex(UI_INK), 0);
    lv_obj_set_style_bg_opa(mk1, LV_OPA_COVER, 0);

    stl = lv_label_create(s_content);
    lv_obj_set_style_text_font(stl, ui_pixel_font_body(), 0);
    lv_obj_set_style_text_color(stl, lv_color_hex(UI_GRASS_DARK), 0);
    lv_obj_align(stl, LV_ALIGN_TOP_LEFT, 4, 172);
    lv_label_set_text(stl, "{{state}}");

    str = lv_label_create(s_content);
    lv_obj_set_style_text_font(str, ui_pixel_font_body(), 0);
    lv_obj_set_style_text_color(str, lv_color_hex(UI_INK), 0);
    lv_obj_align(str, LV_ALIGN_TOP_RIGHT, -6, 172);
    lv_label_set_text(str, "更新 {{now_local}}");

    lv_screen_load(s_scr);
}

void demo_balance_direct_exit(void)
{
    serial_screenshot_set_target(NULL);
    if (s_scr) {
        lv_obj_delete(s_scr);   // stop() 已先停任务与链路
        s_scr = NULL;
        s_content = NULL;
    }
}

void demo_balance_direct_key(bsp_btn_t btn, bsp_btn_ev_t ev)
{
    if (btn != BSP_BTN_OK || ev != BSP_BTN_CLICK) return;
    if (s_wakeup) xSemaphoreGive(s_wakeup);   // 手动刷新
}
