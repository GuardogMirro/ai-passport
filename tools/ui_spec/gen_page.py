#!/usr/bin/env python3
"""tools/ui_spec/gen_page.py -- generate main/demo_<page>.c from a page spec.

The generator is a translator, not a layout engine: all geometry comes from
layout.py, the same expansion render.py draws. So the preview and the firmware
are two renderings of one description, and diff_capture.py is the empirical
check that they still agree.

Static pages (no "data" section) render their spec text as-is. Data pages add
a fetch task bound through {{placeholder}} templates:

    "data":  { "kind": "glm_quota", "poll_ms": 300000 }
    "samples": { "w5.pct": 2, ... }        # preview values, never compiled
    { "value": "{{w5.pct}}% / {{w5.theo}}%", "pct": "{{w5.pct}}", ... }

v1 ships one adapter: glm_quota fetches the Zhipu quota endpoint directly over
HTTPS (bearer key from net_config.h), normalizes the windows and computes the
pace mark on-device after SNTP sync. Preview substitutes "samples"; the
generator keeps the templates and emits runtime formatting instead.

Firmware rules this encoder obeys (from AGENTS.md, the agent guide and main.c):
  * enter/exit are called with the LVGL lock held by main.c, key() is NOT -
    so generated key handlers take bsp_lvgl_lock() themselves; the fetch task
    also locks around every widget update;
  * exit deletes the screen and nulls pointers; stop() halts the task and the
    network link BEFORE exit runs (main.c calls stop first);
  * the OK long-press global back gesture is main.c's, never re-implemented;
  * the page registers its 240x192 capture container with the screenshot
    service so previews can be diffed against real captures;
  * --register patches demo.h / CMakeLists / main.c: DEMOS[] entry (with
    start/stop for data pages), the positional s_ok[] slot, the mascot's free
    cell when DEMO_COUNT is odd, and ASCII-aware menu label fonts.

usage:
  python tools/ui_spec/gen_page.py <spec.json> --out main/demo_<page>.c [--force]
      [--register] [--repo .]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout as L  # noqa: E402

INDENT = "    "

# glm_quota adapter: placeholder -> (C argument, printf type)
GLM_ARGS = {
    "w5.used": ("q->w5.used", "d"), "w5.limit": ("q->w5.limit", "d"),
    "w5.pct": ("q->w5.pct", "d"), "w5.theo": ("t5", "s"),
    "w5.reset": ("q->w5.reset_local", "s"),
    "wk.used": ("q->wk.used", "d"), "wk.limit": ("q->wk.limit", "d"),
    "wk.pct": ("q->wk.pct", "d"), "wk.theo": ("tw", "s"),
    "wk.reset": ("q->wk.reset_local", "s"),
    "now_local": ("q->now_local", "s"),
}
PLACEHOLDER_RE = re.compile(r"\{\{(\w+(?:\.\w+)*)\}\}")


def c_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def has_non_ascii(s):
    return any(ord(ch) > 0x7F for ch in s)


def var_of(node):
    return "s_cursor" if node.get("var") == "cursor" else node.get("var", "o")


def declare(v, static_all=False):
    """Statics are declared at file scope; re-declaring one inside enter() would
    shadow it and leave the file-scope pointer NULL."""
    if v.startswith("s_") or static_all:
        return ""
    return "lv_obj_t *"


def emit_node(node, out, depth=1, static_all=False):
    """Append C statements for one layout node."""
    pad = INDENT * depth
    op = node["op"]
    v = var_of(node)

    if op == "panel":
        out.append('%s%s%s = ui_pixel_panel_create(s_content, %d, %d, %d, %d, UI_%s);'
                   % (pad, declare(v, static_all), v, node["x"], node["y"],
                      node["w"], node["h"], node["color"]))
        for child in node.get("children", []):
            emit_node(child, out, depth, static_all)
        return

    par = "s_content" if node.get("parent") == "content" else node["parent"]
    if op == "text":
        out.append('%s%s%s = lv_label_create(%s);' % (pad, declare(v, static_all), v, par))
        out.append('%slv_obj_set_style_text_font(%s, %s, 0);'
                   % (pad, v, L.FONT_ACCESSOR[node["font"]]))
        out.append('%slv_obj_set_style_text_color(%s, lv_color_hex(UI_%s), 0);'
                   % (pad, v, node["color"]))
        out.append('%slv_obj_align(%s, LV_ALIGN_%s, %d, %d);'
                   % (pad, v, node.get("align", "TOP_LEFT"), node.get("dx", 0), node.get("dy", 0)))
        out.append('%slv_label_set_text(%s, %s);' % (pad, v, c_str(node.get("text", ""))))
        return

    if op == "rect":
        out.append('%s%s%s = lv_obj_create(%s);' % (pad, declare(v, static_all), v, par))
        out.append('%slv_obj_remove_flag(%s, LV_OBJ_FLAG_SCROLLABLE);' % (pad, v))
        out.append('%slv_obj_set_size(%s, %d, %d);' % (pad, v, node["w"], node["h"]))
        out.append('%slv_obj_set_pos(%s, %d, %d);' % (pad, v, node["x"], node["y"]))
        if node.get("hidden"):
            out.append('%slv_obj_add_flag(%s, LV_OBJ_FLAG_HIDDEN);' % (pad, v))
        out.append('%slv_obj_set_style_radius(%s, 0, 0);' % (pad, v))
        out.append('%slv_obj_set_style_border_width(%s, 0, 0);' % (pad, v))
        out.append('%slv_obj_set_style_pad_all(%s, 0, 0);' % (pad, v))
        out.append('%slv_obj_set_style_bg_color(%s, lv_color_hex(UI_%s), 0);'
                   % (pad, v, node["color"]))
        out.append('%slv_obj_set_style_bg_opa(%s, LV_OPA_COVER, 0);' % (pad, v))
        return

    if op == "bar":
        out.append('%s%s%s = lv_bar_create(%s);' % (pad, declare(v, static_all), v, par))
        out.append('%slv_obj_set_style_bg_color(%s, lv_color_hex(UI_%s), 0);'
                   % (pad, v, node["track"]))
        out.append('%slv_obj_set_style_bg_opa(%s, LV_OPA_COVER, 0);' % (pad, v))
        out.append('%slv_obj_set_style_border_width(%s, 0, 0);' % (pad, v))
        if node.get("radius"):
            out.append('%slv_obj_set_style_radius(%s, %d, 0);' % (pad, v, node["radius"]))
            out.append('%slv_obj_set_style_radius(%s, %d, LV_PART_INDICATOR);'
                       % (pad, v, node["radius"]))
        out.append('%slv_bar_set_range(%s, 0, 100);' % (pad, v))
        out.append('%slv_obj_set_size(%s, %d, %d);' % (pad, v, node["w"], node["h"]))
        out.append('%slv_obj_align(%s, LV_ALIGN_%s, %d, %d);'
                   % (pad, v, node.get("align", "BOTTOM_LEFT"), node.get("dx", 0), node.get("dy", 0)))
        out.append('%slv_bar_set_value(%s, %d, LV_ANIM_OFF);' % (pad, v, int(node.get("pct", 0))))
        out.append('%slv_obj_set_style_bg_color(%s, lv_color_hex(UI_%s), LV_PART_INDICATOR);'
                   % (pad, v, node["fill"]))
        return

    raise SystemExit("generator: unsupported op %r" % op)


def collect_vars(nodes, acc):
    for n in nodes:
        if n["op"] == "panel":
            acc.append(n["var"])
            collect_vars(n.get("children", []), acc)
        else:
            acc.append(var_of(n))
    return acc


def template_to_fmt(text, args_map):
    """'{{w5.pct}}% / {{w5.theo}}%' -> ('%d%% / %s%%', ['q->w5.pct', 't5']).
    Literal percent signs are escaped; 'state' maps to the precomposed string."""
    out = []
    args = []
    pos = 0
    for m in PLACEHOLDER_RE.finditer(text):
        out.append(text[pos:m.start()].replace("%", "%%"))
        key = m.group(1)
        if key == "state":
            out.append("%s")
            args.append("state")
        else:
            arg, typ = args_map[key]
            out.append("%" + typ)
            args.append(arg)
        pos = m.end()
    out.append(text[pos:].replace("%", "%%"))
    return "".join(out), args


def gen_glm_apply(page):
    """apply_data() for the glm_quota adapter: bind placeholders to widgets."""
    lines = []
    metrics = []
    for node in page["nodes"]:
        if node["op"] != "panel":
            continue
        m = {"bar": None, "mark": None, "label": None, "value": None,
             "width": None, "mark_y": None}
        for ch in node.get("children", []):
            if ch["op"] == "text" and ch.get("var", "").startswith("lbl"):
                m["label"] = ch
            elif ch["op"] == "text" and ch.get("var", "").startswith("val"):
                m["value"] = ch
            elif ch["op"] == "bar":
                m["bar"] = ch
                m["width"] = ch["w"]
            elif ch["op"] == "rect" and ch.get("var", "").startswith("mk"):
                m["mark"] = ch
        if m["bar"]:
            metrics.append(m)

    lines += [
        "// 取数成功:把窗口数据落到控件(跨任务,持 LVGL 锁)。",
        "// theo 未对时为 -1:数值显示 --,刻度线隐藏。",
        "static void apply_data(const glm_quota_t *q)",
        "{",
        "    char t5[16], tw[16], state[48];",
        "    if (q->w5.theo >= 0) snprintf(t5, sizeof(t5), \"%d\", q->w5.theo);",
        "    else strlcpy(t5, \"--\", sizeof(t5));",
        "    if (q->wk.theo >= 0) snprintf(tw, sizeof(tw), \"%d\", q->wk.theo);",
        "    else strlcpy(tw, \"--\", sizeof(tw));",
        "    snprintf(state, sizeof(state), \"在线 %s\", q->level);",
        "",
        "    if (!bsp_lvgl_lock(500)) return;",
    ]
    for m in metrics:
        bar, mark = m["bar"], m["mark"]
        src = bar.get("bind", "w5")
        fmt_s, args = template_to_fmt(m["value"]["text"], GLM_ARGS)
        lines.append('    lv_label_set_text_fmt(%s, %s, %s);'
                     % (m["value"]["var"], c_str(fmt_s), ", ".join(args)))
        lines.append('    lv_bar_set_value(%s, q->%s.pct, LV_ANIM_OFF);' % (bar["var"], src))
        lines.append('    lv_obj_set_style_bg_color(%s, lv_color_hex(warn_color(q->%s.pct, q->%s.theo, UI_%s)), LV_PART_INDICATOR);'
                     % (bar["var"], src, src, bar["fill"]))
        if m["label"] and PLACEHOLDER_RE.search(m["label"].get("text", "")):
            fmt_s, args = template_to_fmt(m["label"]["text"], GLM_ARGS)
            lines.append('    lv_label_set_text_fmt(%s, %s, %s);'
                         % (m["label"]["var"], c_str(fmt_s), ", ".join(args)))
        if mark:
            lines.append('    if (q->%s.theo >= 0) {' % src)
            lines.append('        lv_obj_set_pos(%s, 4 + q->%s.theo * %d / 100, %d);'
                         % (mark["var"], src, m["width"], mark["y"]))
            lines.append('        lv_obj_clear_flag(%s, LV_OBJ_FLAG_HIDDEN);' % mark["var"])
            lines.append('    } else {')
            lines.append('        lv_obj_add_flag(%s, LV_OBJ_FLAG_HIDDEN);' % mark["var"])
            lines.append('    }')
    st = {}
    for node in page["nodes"]:
        if node["op"] == "text" and node.get("parent") == "content":
            if node.get("var") == "stl":
                st["left"] = node
            elif node.get("var") == "str":
                st["right"] = node
    if "left" in st and PLACEHOLDER_RE.search(st["left"].get("text", "")):
        fmt_s, args = template_to_fmt(st["left"]["text"], GLM_ARGS)
        lines.append('    lv_label_set_text_fmt(%s, %s, %s);'
                     % ("stl", c_str(fmt_s), ", ".join(args)))
        lines.append('    lv_obj_set_style_text_color(stl, lv_color_hex(UI_GRASS_DARK), 0);')
    if "right" in st and PLACEHOLDER_RE.search(st["right"].get("text", "")):
        fmt_s, args = template_to_fmt(st["right"]["text"], GLM_ARGS)
        lines.append('    lv_label_set_text_fmt(str, %s, %s);'
                     % (c_str(fmt_s), ", ".join(args)))
    lines += [
        "    bsp_lvgl_unlock();",
        "}",
        "",
        "// 取数失败:状态行红字显示原因(其余控件保持上次值)。",
        "static void apply_error(const char *msg)",
        "{",
        "    if (!stl) return;",
        "    if (!bsp_lvgl_lock(500)) return;",
        "    lv_label_set_text(stl, msg);",
        "    lv_obj_set_style_text_color(stl, lv_color_hex(UI_RED), 0);",
        "    bsp_lvgl_unlock();",
        "}",
    ]
    return lines


def gen_glm_task(page_name, poll_ms):
    return [
        "// 拉数据:GOT-IP 或周期到点唤醒;首次取数前最多等 6 秒 SNTP,",
        "// 否则理论节奏(theo)算不出来。",
        "static void fetch_task(void *arg)",
        "{",
        "    (void)arg;",
        "    while (s_running) {",
        "        xSemaphoreTake(s_wakeup, pdMS_TO_TICKS(%d));" % poll_ms,
        "        if (!s_running) break;",
        "        for (int i = 0; i < 60 && s_running && !net_link_time_valid(); i++) {",
        "            vTaskDelay(pdMS_TO_TICKS(100));",
        "        }",
        "        glm_quota_t q;",
        "        if (glm_quota_fetch(&q) == ESP_OK) apply_data(&q);",
        "        else apply_error(q.err[0] ? q.err : \"取数失败\");",
        "    }",
        "    vTaskDelete(NULL);",
        "}",
        "",
        "static void on_got_ip(void)",
        "{",
        "    if (s_wakeup) xSemaphoreGive(s_wakeup);",
        "}",
        "",
        "esp_err_t demo_%s_start(void)" % page_name,
        "{",
        "    s_wakeup = xSemaphoreCreateBinary();",
        "    if (!s_wakeup) return ESP_ERR_NO_MEM;",
        "    esp_err_t err = net_link_start(on_got_ip);",
        "    if (err != ESP_OK) {",
        "        vSemaphoreDelete(s_wakeup);",
        "        s_wakeup = NULL;",
        "        return err;",
        "    }",
        "    s_running = true;",
        "    if (xTaskCreate(fetch_task, \"data_fetch\", 8192, NULL, 4, &s_task) != pdPASS) {",
        "        s_running = false;",
        "        net_link_stop();",
        "        vSemaphoreDelete(s_wakeup);",
        "        s_wakeup = NULL;",
        "        return ESP_ERR_NO_MEM;",
        "    }",
        "    return ESP_OK;",
        "}",
        "",
        "esp_err_t demo_%s_stop(void)" % page_name,
        "{",
        "    s_running = false;",
        "    if (s_wakeup) xSemaphoreGive(s_wakeup);",
        "    vTaskDelay(pdMS_TO_TICKS(100));   // 让任务先退出,再拆链路",
        "    if (s_wakeup) { vSemaphoreDelete(s_wakeup); s_wakeup = NULL; }",
        "    s_task = NULL;",
        "    net_link_stop();",
        "    return ESP_OK;",
        "}",
    ]


def gen_c(page, spec, page_name):
    cap = page["capture"]
    title = page["title"]
    nav = page["nav"]
    data = page.get("data")
    has_data = bool(data and data.get("kind") == "glm_quota")
    title_call = ('ui_pixel_screen_create_font(%s, ui_pixel_font_title())' % c_str(title)
                  if has_non_ascii(title) else 'ui_pixel_screen_create(%s)' % c_str(title))

    head = [
        "// main/demo_%s.c -- GENERATED from tools/ui_spec/pages/%s.json by" % (page_name, page["page"]),
        "// tools/ui_spec/gen_page.py. Do not edit by hand: change the spec, re-run the",
        "// generator, re-render the preview and diff it against a device capture.",
        '#include "demo.h"',
        '#include "bsp_display.h"   // bsp_lvgl_lock: key()/task run without the lock',
        '#include "ui_pixel.h"',
        '#include "serial_screenshot.h"',
    ]
    if has_data:
        head += [
            '#include "glm_quota.h"',
            '#include "net_link.h"',
            '#include "esp_err.h"',
            '#include "freertos/FreeRTOS.h"',
            '#include "freertos/semphr.h"',
            '#include "freertos/task.h"',
            '#include <string.h>',
        ]
    head += [
        '#include "lvgl.h"',
        "",
        "static lv_obj_t *s_scr;",
        "static lv_obj_t *s_content;",
    ]

    helpers = []
    if has_data:
        head.append("static SemaphoreHandle_t s_wakeup;")
        head.append("static TaskHandle_t s_task;")
        head.append("static volatile bool s_running;")
        head += ["static lv_obj_t *%s;" % v for v in collect_vars(page["nodes"], [])]
        helpers += [
            "// 与 PC 余额卡同款告警语义:超理论橙,>=90% 或超理论 20 个百分点红。",
            "static uint32_t warn_color(int pct, int theo, uint32_t base)",
            "{",
            "    if (pct >= 90 || (theo >= 0 && pct - theo >= 20)) return UI_RED;",
            "    if (theo >= 0 && pct > theo) return UI_ORANGE;",
            "    return base;",
            "}",
            "",
        ]
        helpers += gen_glm_apply(page)
        helpers.append("")
        helpers += gen_glm_task(page_name, int(data.get("poll_ms", 300000)))
    elif nav:
        n = len(nav["rows"])
        head.append("static lv_obj_t *s_cursor;")
        head.append("#define ROW_COUNT %d" % n)
        head.append("static lv_obj_t *s_row_panel[ROW_COUNT];")
        head.append("static int s_row_y[ROW_COUNT];")
        head.append("static int s_sel;")
        helpers += [
            "// Move the cursor to a row; rows may live in different panels.",
            "static void select_row(int sel)",
            "{",
            "    if (!s_cursor || sel < 0 || sel >= ROW_COUNT) return;",
            "    s_sel = sel;",
            "    lv_obj_set_parent(s_cursor, s_row_panel[sel]);",
            "    lv_obj_set_pos(s_cursor, 0, s_row_y[sel] + 2);",
            "}",
        ]

    body = []
    body.append("")
    body.append("void demo_%s_enter(void)" % page_name)
    body.append("{")
    body.append(INDENT + "s_scr = %s;" % title_call)
    body.append("")
    body.append(INDENT + "// 截屏验证容器:内容与容器同坐标,截屏服务按容器渲染。")
    body.append(INDENT + "// 起点 y%d 避开标题牌(y8-41,投影到 y45)。" % cap["y"])
    body.append(INDENT + "s_content = lv_obj_create(s_scr);")
    body.append(INDENT + "lv_obj_set_size(s_content, %d, %d);" % (cap["w"], cap["h"]))
    body.append(INDENT + "lv_obj_set_pos(s_content, %d, %d);" % (cap["x"], cap["y"]))
    body.append(INDENT + "lv_obj_set_style_bg_opa(s_content, LV_OPA_TRANSP, 0);")
    body.append(INDENT + "lv_obj_set_style_border_width(s_content, 0, 0);")
    body.append(INDENT + "lv_obj_set_style_pad_all(s_content, 0, 0);")
    body.append(INDENT + "lv_obj_set_scrollbar_mode(s_content, LV_SCROLLBAR_MODE_OFF);")
    body.append(INDENT + "serial_screenshot_set_target(s_content);")
    body.append("")
    for node in page["nodes"]:
        emit_node(node, body, static_all=has_data)
        body.append("")

    if nav:
        for i, row in enumerate(nav["rows"]):
            body.append(INDENT + "s_row_panel[%d] = %s;" % (i, row["panel"]))
            body.append(INDENT + "s_row_y[%d] = %d;" % (i, row["y"]))
        body.append(INDENT + "select_row(%d);" % int(nav.get("selected", 0)))
        body.append("")

    body.append(INDENT + "lv_screen_load(s_scr);")
    body.append("}")

    body.append("")
    body.append("void demo_%s_exit(void)" % page_name)
    body.append("{")
    body.append(INDENT + "serial_screenshot_set_target(NULL);")
    body.append(INDENT + "if (s_scr) {")
    if has_data:
        body.append(INDENT * 2 + "lv_obj_delete(s_scr);   // stop() 已先停任务与链路")
    else:
        body.append(INDENT * 2 + "lv_obj_delete(s_scr);   // static page: no tasks or timers to stop")
    body.append(INDENT * 2 + "s_scr = NULL;")
    body.append(INDENT * 2 + "s_content = NULL;")
    if nav:
        body.append(INDENT * 2 + "s_cursor = NULL;")
        body.append(INDENT * 2 + "s_sel = 0;")
    body.append(INDENT + "}")
    body.append("}")

    body.append("")
    if has_data:
        body.append("void demo_%s_key(bsp_btn_t btn, bsp_btn_ev_t ev)" % page_name)
        body.append("{")
        body.append(INDENT + "if (btn != BSP_BTN_OK || ev != BSP_BTN_CLICK) return;")
        body.append(INDENT + "if (s_wakeup) xSemaphoreGive(s_wakeup);   // 手动刷新")
        body.append("}")
    elif nav:
        body.append("void demo_%s_key(bsp_btn_t btn, bsp_btn_ev_t ev)" % page_name)
        body.append("{")
        body.append(INDENT + "if (ev != BSP_BTN_CLICK) return;   // OK long-press back is main.c's")
        body.append(INDENT + "if (btn != BSP_BTN_UP && btn != BSP_BTN_DOWN) return;")
        body.append(INDENT + "// main.c forwards key events without the LVGL lock.")
        body.append(INDENT + "if (!bsp_lvgl_lock(200)) return;")
        body.append(INDENT + "int sel = s_sel + (btn == BSP_BTN_DOWN ? 1 : -1);")
        body.append(INDENT + "if (sel < 0) sel = ROW_COUNT - 1;")
        body.append(INDENT + "if (sel >= ROW_COUNT) sel = 0;")
        body.append(INDENT + "select_row(sel);")
        body.append(INDENT + "bsp_lvgl_unlock();")
        body.append("}")
    else:
        body.append("void demo_%s_key(bsp_btn_t btn, bsp_btn_ev_t ev)" % page_name)
        body.append("{")
        body.append(INDENT + "(void)btn; (void)ev;   // static page; OK long-press back is main.c's")
        body.append("}")

    return "\n".join(head + helpers + body) + "\n"


# ---- registration -----------------------------------------------------------

def patch(path, old, new, note, already):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if already in text:
        print("  skip %s (%s)" % (os.path.basename(path), note))
        return False
    if old not in text:
        raise SystemExit("register: anchor not found in %s for %s\nexpected:\n%s"
                         % (path, note, old))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text.replace(old, new, 1))
    print("  patched %s (%s)" % (os.path.basename(path), note))
    return True


def register(repo, page_name, menu_name, has_lifecycle):
    print("registering demo_%s:" % page_name)
    decl = ("\n// %s page (generated from tools/ui_spec/pages/%s.json).\n"
            "void demo_%s_enter(void); void demo_%s_exit(void);\n"
            "void demo_%s_key(bsp_btn_t btn, bsp_btn_ev_t ev);\n"
            % (page_name.capitalize(), page_name, page_name, page_name, page_name))
    if has_lifecycle:
        decl += "esp_err_t demo_%s_start(void); esp_err_t demo_%s_stop(void);\n" % (
            page_name, page_name)
    dh = os.path.join(repo, "main", "demo.h")
    with open(dh, encoding="utf-8") as f:
        cur = f.read()
    if "demo_%s_enter" % page_name not in cur:
        with open(dh, "w", encoding="utf-8", newline="\n") as f:
            f.write(cur.rstrip("\n") + "\n" + decl)
        print("  patched demo.h (declarations)")
    else:
        print("  skip demo.h (declarations present)")

    patch(os.path.join(repo, "main", "CMakeLists.txt"),
          '         "serial_screenshot.c"\n',
          '         "serial_screenshot.c"\n         "demo_%s.c"\n' % page_name,
          "SRCS", 'demo_%s.c' % page_name)

    main_c = os.path.join(repo, "main", "main.c")
    with open(main_c, encoding="utf-8") as f:
        text = f.read()

    if has_lifecycle:
        entry = ('    { .name = %s, .enter = demo_%s_enter, .exit = demo_%s_exit,\n'
                 '      .key = demo_%s_key, .start = demo_%s_start, .stop = demo_%s_stop },'
                 % (c_str(menu_name), page_name, page_name, page_name, page_name, page_name))
    else:
        entry = ('    { .name = %s, .enter = demo_%s_enter, .exit = demo_%s_exit,\n'
                 '      .key = demo_%s_key },' % (c_str(menu_name), page_name, page_name, page_name))
    if "demo_%s_enter" % page_name not in text:
        m = re.search(r"(static const demo_entry_t DEMOS\[\] = \{.*?)(\n\};)", text, re.S)
        if not m:
            raise SystemExit("register: DEMOS[] not found in main.c")
        text = text[:m.end(1)] + "\n" + entry + text[m.start(2):]
        print("  patched main.c (DEMOS[] entry)")
    else:
        print("  skip main.c DEMOS[] (entry present)")

    slots = [int(x) for x in re.findall(r"s_ok\[(\d+)\]\s*=", text)]
    if slots:
        nxt = max(slots) + 1
        if "s_ok[%d]" % nxt not in text:
            anchor = re.search(r"[^\n]*s_ok\[%d\][^\n]*\n" % max(slots), text)
            text = (text[:anchor.end()]
                    + "    s_ok[%d] = true;                                   "
                      "// %s: 页面内自行降级\n" % (nxt, page_name.capitalize())
                    + text[anchor.end():])
            print("  patched main.c (s_ok[%d])" % nxt)
        else:
            print("  skip main.c s_ok[%d] (present)" % nxt)

    old_mascot = "    s_mascot = ui_pixel_mascot_create(s_menu_scr, 101, 242);"
    new_mascot = ("    // 吉祥物落在网格的第一个空位(奇数项时右列那格空着);排满则落在下方。\n"
                  "    if (DEMO_COUNT % 2 == 1) {\n"
                  "        s_mascot = ui_pixel_mascot_create(s_menu_scr, 123,\n"
                  "                                          52 + (int)(DEMO_COUNT / 2) * 47);\n"
                  "    } else {\n"
                  "        s_mascot = ui_pixel_mascot_create(s_menu_scr, 101, 242);\n"
                  "    }")
    if old_mascot in text:
        text = text.replace(old_mascot, new_mascot, 1)
        print("  patched main.c (mascot cell rule)")
    else:
        print("  skip main.c mascot (rule already present or anchor changed)")

    old_font = ("        lv_obj_set_style_text_font(s_rows[i], &lv_font_montserrat_14, 0);")
    new_font = ("        bool ascii_name = true;\n"
                "        for (const char *p = DEMOS[i].name; *p; p++) {\n"
                "            if ((unsigned char)*p > 0x7F) { ascii_name = false; break; }\n"
                "        }\n"
                "        lv_obj_set_style_text_font(s_rows[i],\n"
                "            ascii_name ? &lv_font_montserrat_14 : ui_pixel_font_body(), 0);")
    if old_font in text:
        text = text.replace(old_font, new_font, 1)
        print("  patched main.c (menu label font)")
    else:
        print("  skip main.c menu font (already patched or anchor changed)")

    with open(main_c, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--out", required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--register", action="store_true")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--menu-name", default=None)
    args = ap.parse_args()

    with open(args.spec, encoding="utf-8") as f:
        spec = json.load(f)
    page = L.expand(spec, samples=False)
    page_name = page["page"]

    if os.path.exists(args.out) and not args.force:
        raise SystemExit("refusing to overwrite %s (pass --force)" % args.out)
    src = gen_c(page, spec, page_name)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(src)
    print("generated %s (%d lines, archetype %s%s)"
          % (args.out, src.count("\n"), page["archetype"],
             ", data=glm_quota" if page.get("data") else ""))
    if args.register:
        register(args.repo, page_name, args.menu_name or page["title"] or page_name,
                 has_lifecycle=bool(page.get("data")))


if __name__ == "__main__":
    main()
