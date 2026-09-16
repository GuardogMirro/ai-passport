#!/usr/bin/env python3
"""tools/ui_spec/gen_page.py -- generate main/demo_<page>.c from a page spec.

The generator is a translator, not a layout engine: all geometry comes from
layout.py, the same expansion render.py draws. So the preview and the firmware
are two renderings of one description, and diff_capture.py is the empirical
check that they still agree.

Firmware rules this encoder obeys (from AGENTS.md, the agent guide and main.c):
  * enter/exit are called with the LVGL lock held by main.c, key() is NOT -
    so generated key handlers take bsp_lvgl_lock() themselves;
  * a page owns its screen: exit() deletes it and nulls every pointer (static
    pages have no tasks or timers; if a spec ever needs them, stop them first);
  * the OK long-press global back gesture is main.c's, never re-implemented;
  * the page registers its 240x192 capture container with the screenshot
    service so previews can be diffed against real captures;
  * registration touches DEMOS[] and the matching s_ok[] slot, because
    s_ok[] is indexed positionally and an unset slot shows [FAIL] and blocks
    entry; with an odd DEMO_COUNT the mascot moves into the grid's free cell.

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


def c_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def has_non_ascii(s):
    return any(ord(ch) > 0x7F for ch in s)


def var_of(node):
    return "s_cursor" if node.get("var") == "cursor" else node.get("var", "o")


def declare(v):
    """Statics are declared at file scope; re-declaring one inside enter() would
    shadow it and leave the file-scope pointer NULL."""
    return "" if v.startswith("s_") else "lv_obj_t *"


def parent_var(node):
    return "s_content" if node.get("parent") == "content" else node["parent"]


def emit_node(node, out, depth=1):
    """Append C statements for one layout node."""
    pad = INDENT * depth
    op = node["op"]
    v = var_of(node)

    if op == "panel":
        out.append('%slv_obj_t *%s = ui_pixel_panel_create(s_content, %d, %d, %d, %d, UI_%s);'
                   % (pad, v, node["x"], node["y"], node["w"], node["h"], node["color"]))
        for child in node.get("children", []):
            emit_node(child, out, depth)
        return

    par = parent_var(node)
    if op == "text":
        out.append('%s%s%s = lv_label_create(%s);' % (pad, declare(v), v, par))
        out.append('%slv_obj_set_style_text_font(%s, %s, 0);'
                   % (pad, v, L.FONT_ACCESSOR[node["font"]]))
        out.append('%slv_obj_set_style_text_color(%s, lv_color_hex(UI_%s), 0);'
                   % (pad, v, node["color"]))
        out.append('%slv_obj_align(%s, LV_ALIGN_%s, %d, %d);'
                   % (pad, v, node.get("align", "TOP_LEFT"), node.get("dx", 0), node.get("dy", 0)))
        out.append('%slv_label_set_text(%s, %s);' % (pad, v, c_str(node.get("text", ""))))
        return

    if op == "rect":
        out.append('%s%s%s = lv_obj_create(%s);' % (pad, declare(v), v, par))
        out.append('%slv_obj_remove_flag(%s, LV_OBJ_FLAG_SCROLLABLE);' % (pad, v))
        out.append('%slv_obj_set_size(%s, %d, %d);' % (pad, v, node["w"], node["h"]))
        out.append('%slv_obj_set_pos(%s, %d, %d);' % (pad, v, node["x"], node["y"]))
        out.append('%slv_obj_set_style_radius(%s, 0, 0);' % (pad, v))
        out.append('%slv_obj_set_style_border_width(%s, 0, 0);' % (pad, v))
        out.append('%slv_obj_set_style_pad_all(%s, 0, 0);' % (pad, v))
        out.append('%slv_obj_set_style_bg_color(%s, lv_color_hex(UI_%s), 0);'
                   % (pad, v, node["color"]))
        out.append('%slv_obj_set_style_bg_opa(%s, LV_OPA_COVER, 0);' % (pad, v))
        return

    if op == "bar":
        out.append('%s%s%s = lv_bar_create(%s);' % (pad, declare(v), v, par))
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


def gen_c(page, spec, page_name):
    cap = page["capture"]
    title = page["title"]
    nav = page["nav"]
    title_call = ('ui_pixel_screen_create_font(%s, ui_pixel_font_title())' % c_str(title)
                  if has_non_ascii(title) else 'ui_pixel_screen_create(%s)' % c_str(title))

    head = [
        "// main/demo_%s.c -- GENERATED from tools/ui_spec/pages/%s.json by" % (page_name, page["page"]),
        "// tools/ui_spec/gen_page.py. Do not edit by hand: change the spec, re-run the",
        "// generator, re-render the preview and diff it against a device capture.",
        '#include "demo.h"',
        '#include "bsp_display.h"   // bsp_lvgl_lock: key() runs without the lock',
        '#include "ui_pixel.h"',
        '#include "serial_screenshot.h"',
        '#include "lvgl.h"',
        "",
        "static lv_obj_t *s_scr;",
        "static lv_obj_t *s_content;",
    ]

    statics, helpers = [], []
    if nav:
        n = len(nav["rows"])
        head.append("static lv_obj_t *s_cursor;")
        head.append("#define ROW_COUNT %d" % n)
        head.append("static lv_obj_t *s_row_panel[ROW_COUNT];")
        head.append("static int s_row_y[ROW_COUNT];")
        head.append("static int s_sel;")
        helpers += [
            "",
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
        emit_node(node, body)
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
    body.append(INDENT * 2 + "lv_obj_delete(s_scr);   // static page: no tasks or timers to stop")
    body.append(INDENT * 2 + "s_scr = NULL;")
    body.append(INDENT * 2 + "s_content = NULL;")
    if nav:
        body.append(INDENT * 2 + "s_cursor = NULL;")
        body.append(INDENT * 2 + "s_sel = 0;")
    body.append(INDENT + "}")
    body.append("}")

    body.append("")
    if nav:
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

    return "\n".join(head + statics + helpers + body) + "\n"


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


def register(repo, page_name, menu_name):
    print("registering demo_%s:" % page_name)
    decl = ("\n// %s page (generated from tools/ui_spec/pages/%s.json).\n"
            "void demo_%s_enter(void); void demo_%s_exit(void);\n"
            "void demo_%s_key(bsp_btn_t btn, bsp_btn_ev_t ev);\n"
            % (page_name.capitalize(), page_name, page_name, page_name, page_name))
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

    # 1. DEMOS[] entry (insert before the array's closing brace)
    entry = ('    { .name = %s, .enter = demo_%s_enter, .exit = demo_%s_exit,\n'
             '      .key = demo_%s_key },\n' % (c_str(menu_name), page_name, page_name, page_name))
    if "demo_%s_enter" % page_name not in text:
        m = re.search(r"(static const demo_entry_t DEMOS\[\] = \{.*?)(\n\};)", text, re.S)
        if not m:
            raise SystemExit("register: DEMOS[] not found in main.c")
        text = text[:m.end(1)] + "\n" + entry.rstrip("\n") + text[m.start(2):]
        print("  patched main.c (DEMOS[] entry)")
    else:
        print("  skip main.c DEMOS[] (entry present)")

    # 2. s_ok[] slot: positional, so an unset slot shows [FAIL] and blocks entry
    slots = [int(x) for x in re.findall(r"s_ok\[(\d+)\]\s*=", text)]
    if slots:
        nxt = max(slots) + 1
        if "s_ok[%d]" % nxt not in text:
            anchor = re.search(r"[^\n]*s_ok\[%d\][^\n]*\n" % max(slots), text)
            text = (text[:anchor.end()]
                    + "    s_ok[%d] = true;                                   "
                      "// %s: 静态页面,无外设依赖\n" % (nxt, page_name.capitalize())
                    + text[anchor.end():])
            print("  patched main.c (s_ok[%d])" % nxt)
        else:
            print("  skip main.c s_ok[%d] (present)" % nxt)

    # 3. mascot: with an odd card count the grid's last right cell is free
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

    # 4. menu labels: CJK names need the CJK face, ASCII names keep Montserrat
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
    page = L.expand(spec)
    page_name = page["page"]

    if os.path.exists(args.out) and not args.force:
        raise SystemExit("refusing to overwrite %s (pass --force)" % args.out)
    src = gen_c(page, spec, page_name)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(src)
    print("generated %s (%d lines, archetype %s)"
          % (args.out, src.count("\n"), page["archetype"]))
    if args.register:
        register(args.repo, page_name, args.menu_name or page["title"] or page_name)


if __name__ == "__main__":
    main()
