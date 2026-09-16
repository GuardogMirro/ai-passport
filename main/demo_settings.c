// main/demo_settings.c -- GENERATED from tools/ui_spec/pages/settings.json by
// tools/ui_spec/gen_page.py. Do not edit by hand: change the spec, re-run the
// generator, re-render the preview and diff it against a device capture.
#include "demo.h"
#include "bsp_display.h"   // bsp_lvgl_lock: key() runs without the lock
#include "ui_pixel.h"
#include "serial_screenshot.h"
#include "lvgl.h"

static lv_obj_t *s_scr;
static lv_obj_t *s_content;
static lv_obj_t *s_cursor;
#define ROW_COUNT 4
static lv_obj_t *s_row_panel[ROW_COUNT];
static int s_row_y[ROW_COUNT];
static int s_sel;

// Move the cursor to a row; rows may live in different panels.
static void select_row(int sel)
{
    if (!s_cursor || sel < 0 || sel >= ROW_COUNT) return;
    s_sel = sel;
    lv_obj_set_parent(s_cursor, s_row_panel[sel]);
    lv_obj_set_pos(s_cursor, 0, s_row_y[sel] + 2);
}

void demo_settings_enter(void)
{
    s_scr = ui_pixel_screen_create_font("设置", ui_pixel_font_title());

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

    lv_obj_t *sec0 = ui_pixel_panel_create(s_content, 12, 8, 216, 80, UI_PAPER);
    lv_obj_t *sh0 = lv_label_create(sec0);
    lv_obj_set_style_text_font(sh0, ui_pixel_font_body(), 0);
    lv_obj_set_style_text_color(sh0, lv_color_hex(UI_SKY_DARK), 0);
    lv_obj_align(sh0, LV_ALIGN_TOP_LEFT, 4, 0);
    lv_label_set_text(sh0, "显示");
    lv_obj_t *lb0_0 = lv_label_create(sec0);
    lv_obj_set_style_text_font(lb0_0, ui_pixel_font_body(), 0);
    lv_obj_set_style_text_color(lb0_0, lv_color_hex(UI_INK), 0);
    lv_obj_align(lb0_0, LV_ALIGN_TOP_LEFT, 10, 20);
    lv_label_set_text(lb0_0, "亮度");
    lv_obj_t *vl0_0 = lv_label_create(sec0);
    lv_obj_set_style_text_font(vl0_0, ui_pixel_font_body(), 0);
    lv_obj_set_style_text_color(vl0_0, lv_color_hex(UI_SKY_DARK), 0);
    lv_obj_align(vl0_0, LV_ALIGN_TOP_RIGHT, -16, 20);
    lv_label_set_text(vl0_0, "80%");
    lv_obj_t *ch0_0 = lv_label_create(sec0);
    lv_obj_set_style_text_font(ch0_0, ui_pixel_font_body(), 0);
    lv_obj_set_style_text_color(ch0_0, lv_color_hex(UI_INK), 0);
    lv_obj_align(ch0_0, LV_ALIGN_TOP_RIGHT, -6, 20);
    lv_label_set_text(ch0_0, ">");
    lv_obj_t *rl0_1 = lv_obj_create(sec0);
    lv_obj_remove_flag(rl0_1, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_size(rl0_1, 186, 1);
    lv_obj_set_pos(rl0_1, 4, 44);
    lv_obj_set_style_radius(rl0_1, 0, 0);
    lv_obj_set_style_border_width(rl0_1, 0, 0);
    lv_obj_set_style_pad_all(rl0_1, 0, 0);
    lv_obj_set_style_bg_color(rl0_1, lv_color_hex(UI_MUTED), 0);
    lv_obj_set_style_bg_opa(rl0_1, LV_OPA_COVER, 0);
    lv_obj_t *lb0_1 = lv_label_create(sec0);
    lv_obj_set_style_text_font(lb0_1, ui_pixel_font_body(), 0);
    lv_obj_set_style_text_color(lb0_1, lv_color_hex(UI_INK), 0);
    lv_obj_align(lb0_1, LV_ALIGN_TOP_LEFT, 10, 50);
    lv_label_set_text(lb0_1, "自动息屏");
    lv_obj_t *vl0_1 = lv_label_create(sec0);
    lv_obj_set_style_text_font(vl0_1, ui_pixel_font_body(), 0);
    lv_obj_set_style_text_color(vl0_1, lv_color_hex(UI_SKY_DARK), 0);
    lv_obj_align(vl0_1, LV_ALIGN_TOP_RIGHT, -6, 50);
    lv_label_set_text(vl0_1, "5 分钟");
    s_cursor = lv_obj_create(sec0);
    lv_obj_remove_flag(s_cursor, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_size(s_cursor, 3, 26);
    lv_obj_set_pos(s_cursor, 0, 16);
    lv_obj_set_style_radius(s_cursor, 0, 0);
    lv_obj_set_style_border_width(s_cursor, 0, 0);
    lv_obj_set_style_pad_all(s_cursor, 0, 0);
    lv_obj_set_style_bg_color(s_cursor, lv_color_hex(UI_YELLOW), 0);
    lv_obj_set_style_bg_opa(s_cursor, LV_OPA_COVER, 0);

    lv_obj_t *sec1 = ui_pixel_panel_create(s_content, 12, 96, 216, 80, UI_PAPER);
    lv_obj_t *sh1 = lv_label_create(sec1);
    lv_obj_set_style_text_font(sh1, ui_pixel_font_body(), 0);
    lv_obj_set_style_text_color(sh1, lv_color_hex(UI_SKY_DARK), 0);
    lv_obj_align(sh1, LV_ALIGN_TOP_LEFT, 4, 0);
    lv_label_set_text(sh1, "数据");
    lv_obj_t *lb1_0 = lv_label_create(sec1);
    lv_obj_set_style_text_font(lb1_0, ui_pixel_font_body(), 0);
    lv_obj_set_style_text_color(lb1_0, lv_color_hex(UI_INK), 0);
    lv_obj_align(lb1_0, LV_ALIGN_TOP_LEFT, 10, 20);
    lv_label_set_text(lb1_0, "刷新间隔");
    lv_obj_t *vl1_0 = lv_label_create(sec1);
    lv_obj_set_style_text_font(vl1_0, ui_pixel_font_body(), 0);
    lv_obj_set_style_text_color(vl1_0, lv_color_hex(UI_SKY_DARK), 0);
    lv_obj_align(vl1_0, LV_ALIGN_TOP_RIGHT, -16, 20);
    lv_label_set_text(vl1_0, "5 分钟");
    lv_obj_t *ch1_0 = lv_label_create(sec1);
    lv_obj_set_style_text_font(ch1_0, ui_pixel_font_body(), 0);
    lv_obj_set_style_text_color(ch1_0, lv_color_hex(UI_INK), 0);
    lv_obj_align(ch1_0, LV_ALIGN_TOP_RIGHT, -6, 20);
    lv_label_set_text(ch1_0, ">");
    lv_obj_t *rl1_1 = lv_obj_create(sec1);
    lv_obj_remove_flag(rl1_1, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_size(rl1_1, 186, 1);
    lv_obj_set_pos(rl1_1, 4, 44);
    lv_obj_set_style_radius(rl1_1, 0, 0);
    lv_obj_set_style_border_width(rl1_1, 0, 0);
    lv_obj_set_style_pad_all(rl1_1, 0, 0);
    lv_obj_set_style_bg_color(rl1_1, lv_color_hex(UI_MUTED), 0);
    lv_obj_set_style_bg_opa(rl1_1, LV_OPA_COVER, 0);
    lv_obj_t *lb1_1 = lv_label_create(sec1);
    lv_obj_set_style_text_font(lb1_1, ui_pixel_font_body(), 0);
    lv_obj_set_style_text_color(lb1_1, lv_color_hex(UI_INK), 0);
    lv_obj_align(lb1_1, LV_ALIGN_TOP_LEFT, 10, 50);
    lv_label_set_text(lb1_1, "关于本机");
    lv_obj_t *ch1_1 = lv_label_create(sec1);
    lv_obj_set_style_text_font(ch1_1, ui_pixel_font_body(), 0);
    lv_obj_set_style_text_color(ch1_1, lv_color_hex(UI_INK), 0);
    lv_obj_align(ch1_1, LV_ALIGN_TOP_RIGHT, -6, 50);
    lv_label_set_text(ch1_1, ">");

    s_row_panel[0] = sec0;
    s_row_y[0] = 14;
    s_row_panel[1] = sec0;
    s_row_y[1] = 44;
    s_row_panel[2] = sec1;
    s_row_y[2] = 14;
    s_row_panel[3] = sec1;
    s_row_y[3] = 44;
    select_row(0);

    lv_screen_load(s_scr);
}

void demo_settings_exit(void)
{
    serial_screenshot_set_target(NULL);
    if (s_scr) {
        lv_obj_delete(s_scr);   // static page: no tasks or timers to stop
        s_scr = NULL;
        s_content = NULL;
        s_cursor = NULL;
        s_sel = 0;
    }
}

void demo_settings_key(bsp_btn_t btn, bsp_btn_ev_t ev)
{
    if (ev != BSP_BTN_CLICK) return;   // OK long-press back is main.c's
    if (btn != BSP_BTN_UP && btn != BSP_BTN_DOWN) return;
    // main.c forwards key events without the LVGL lock.
    if (!bsp_lvgl_lock(200)) return;
    int sel = s_sel + (btn == BSP_BTN_DOWN ? 1 : -1);
    if (sel < 0) sel = ROW_COUNT - 1;
    if (sel >= ROW_COUNT) sel = 0;
    select_row(sel);
    bsp_lvgl_unlock();
}
