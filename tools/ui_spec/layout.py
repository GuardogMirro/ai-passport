#!/usr/bin/env python3
"""tools/ui_spec/layout.py -- single source of truth for page geometry.

One expansion, two consumers: render.py draws it, gen_page.py translates it to
C. Neither backend computes positions, so the preview and the firmware cannot
drift apart; diff_capture.py stays as the empirical check.

Coordinate model (identical to the firmware's):
  * panel nodes carry container-local x/y/w/h, matching children parented to
    the 240x192 screenshot container;
  * child nodes carry (parent, align, dx, dy) exactly as lv_obj_align takes
    them, so C emission is a direct translation;
  * a panel's content box is inset by CONTENT_INSET (4px border + 7px padding),
    which is where LVGL resolves both alignment and lv_obj_set_pos.
"""

import json

PALETTE = {
    "SKY": 0x1689E8, "SKY_DARK": 0x0872C9, "INK": 0x17202A, "PAPER": 0xF4F4EA,
    "GRASS": 0x82BE2D, "GRASS_DARK": 0x55951D, "YELLOW": 0xFFD928,
    "ORANGE": 0xFFB23E, "RED": 0xE43B2F, "MUTED": 0xD9E7EC,
    "WHITE": 0xFFFFFF, "BLACK": 0x000000,
}

PANEL_BORDER = 4       # ui_pixel_panel_create: border_width
PANEL_PAD = 7          # ui_pixel_panel_create: pad_all
PANEL_SHADOW = (5, 6)  # ui_pixel_panel_create: ink block offset
CONTENT_INSET = PANEL_BORDER + PANEL_PAD

SCREEN_W, SCREEN_H = 240, 320
CAPTURE_W, CAPTURE_H = 240, 192
CAPTURE_DEFAULT = {"x": 0, "y": 48, "w": CAPTURE_W, "h": CAPTURE_H}

# Faces: (ttf basename, px size, lvgl line_height, lvgl base_line, dy_corr).
# line_height/base_line come from the generated faces in assets/fonts;
# dy_corr is measured against device captures and tracks the faces' dominant
# .ofs_y (-2 at 12px, -4 at 24px). Re-measure after changing fonts.
FACES = {
    "cjk12": ("fusion-pixel-12px-monospaced-zh_hans.ttf", 12, 11, 2, 1),
    "cjk24": ("fusion-pixel-12px-monospaced-zh_hans.ttf", 24, 22, 4, 2),
}

FONT_ACCESSOR = {"cjk12": "ui_pixel_font_body()", "cjk24": "ui_pixel_font_title()"}


def rgb565(color):
    """Quantize a 24-bit color the way the ST7789 panel stores it."""
    if isinstance(color, str):
        color = PALETTE[color]
    r, g, b = (color >> 16) & 255, (color >> 8) & 255, color & 255
    return ((r >> 3) << 3, (g >> 2) << 2, (b >> 3) << 3)


def content_box(panel):
    """A panel's content area, in container coordinates."""
    return (panel["x"] + CONTENT_INSET, panel["y"] + CONTENT_INSET,
            panel["w"] - 2 * CONTENT_INSET, panel["h"] - 2 * CONTENT_INSET)


def as_int(v, default=0):
    """Numeric field that may be a {{placeholder}} string in generator mode:
    substituted ints pass through, placeholders return the default."""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        try:
            return int(v)
        except ValueError:
            return default
    return default


def is_placeholder(v):
    return isinstance(v, str) and v.startswith("{{")


def resolve(align, dx, dy, box, w, h):
    """LVGL-style alignment of a w x h child inside box -> absolute x, y."""
    bx, by, bw, bh = box
    if align in ("TOP_LEFT", "LEFT"):       x, y = bx, by
    elif align in ("TOP_RIGHT", "RIGHT"):   x, y = bx + bw - w, by
    elif align == "TOP_MID":                x, y = bx + (bw - w) // 2, by
    elif align == "BOTTOM_LEFT":            x, y = bx, by + bh - h
    elif align == "BOTTOM_RIGHT":           x, y = bx + bw - w, by + bh - h
    elif align == "BOTTOM_MID":             x, y = bx + (bw - w) // 2, by + bh - h
    elif align == "CENTER":                 x, y = bx + (bw - w) // 2, by + (bh - h) // 2
    else:                                   x, y = bx, by
    return x + dx, y + dy


# ---- archetypes -------------------------------------------------------------

def expand_dashboard(spec):
    """Metric blocks (label / hero value / bar with pace mark) + status row."""
    nodes = []
    top = spec.get("top", 8)
    gap = spec.get("gap", 6)
    height = spec.get("block_height", 78)
    metrics = spec.get("metrics", [])

    for i, m in enumerate(metrics):
        y = top + i * (height + gap)
        panel = {"op": "panel", "var": "blk%d" % i, "x": 12, "y": y, "w": 216,
                 "h": height, "color": m.get("color", "PAPER"), "children": []}
        cb = content_box(panel)
        if m.get("label"):
            panel["children"].append({
                "op": "text", "var": "lbl%d" % i, "parent": panel["var"],
                "align": "TOP_LEFT", "dx": 4, "dy": 1, "font": "cjk12",
                "color": "SKY_DARK", "text": m["label"]})
        if m.get("value"):
            panel["children"].append({
                "op": "text", "var": "val%d" % i, "parent": panel["var"],
                "align": "TOP_LEFT", "dx": 4, "dy": 15, "font": "cjk24",
                "color": m.get("value_color", "INK"), "text": m["value"]})
        bar_h = m.get("bar_height", 14)
        bar_w = m.get("bar_width", 132)
        bar_dy = m.get("bar_dy", -3)
        pct_raw = m.get("pct", 0)
        mark_raw = m.get("mark")
        bar_node = {
            "op": "bar", "var": "bar%d" % i, "parent": panel["var"],
            "align": "BOTTOM_LEFT", "dx": 4, "dy": bar_dy, "w": bar_w, "h": bar_h,
            "radius": m.get("radius", 7), "track": "MUTED",
            "fill": m.get("fill", "GRASS"), "pct": as_int(pct_raw)}
        if is_placeholder(pct_raw):
            # remember which window this bar binds to (w5/wk) for the generator
            bar_node["bind"] = pct_raw.strip("{} ").split(".")[0]
        panel["children"].append(bar_node)
        mark = mark_raw
        if mark is not None:
            # bar top inside the content box, so the mark shares the bar's rows
            bar_top = cb[3] + bar_dy - bar_h
            ph = is_placeholder(mark)
            mx = 4 if ph else 4 + as_int(mark) * bar_w // 100
            panel["children"].append({
                "op": "rect", "var": "mk%d" % i, "parent": panel["var"],
                "x": min(mx, 4 + bar_w - 2), "y": bar_top, "w": 2, "h": bar_h,
                "color": "INK", "hidden": ph})
        nodes.append(panel)

    st = spec.get("status")
    if st:
        n = len(metrics)
        sy = st.get("y", top + (n - 1) * (height + gap) + height + 2)
        if st.get("left"):
            nodes.append({"op": "text", "var": "stl", "parent": "content",
                          "align": "TOP_LEFT", "dx": 4, "dy": sy, "font": "cjk12",
                          "color": st.get("left_color", "GRASS_DARK"),
                          "text": st["left"]})
        if st.get("right"):
            nodes.append({"op": "text", "var": "str", "parent": "content",
                          "align": "TOP_RIGHT", "dx": -6, "dy": sy, "font": "cjk12",
                          "color": st.get("right_color", "INK"), "text": st["right"]})
    return {"nodes": nodes, "nav": None}


def expand_list(spec):
    """Grouped rows, iOS Settings pattern: section title, label left, value
    right, optional chevron, hairline separators, and a movable cursor."""
    nodes = []
    nav_rows = []
    panels = []
    y = spec.get("top", 8)
    gap = spec.get("gap", 8)
    row_h = spec.get("row_height", 30)
    head_h = spec.get("section_head", 14)
    selectable = spec.get("selectable", True)

    for si, sec in enumerate(spec.get("sections", [])):
        rows = sec.get("rows", [])
        head = head_h if sec.get("title") else 0
        h = head + len(rows) * row_h + 6
        panel = {"op": "panel", "var": "sec%d" % si, "x": 12, "y": y, "w": 216,
                 "h": h, "color": sec.get("color", "PAPER"), "children": []}
        if sec.get("title"):
            panel["children"].append({
                "op": "text", "var": "sh%d" % si, "parent": panel["var"],
                "align": "TOP_LEFT", "dx": 4, "dy": 0, "font": "cjk12",
                "color": "SKY_DARK", "text": sec["title"]})
        for ri, row in enumerate(rows):
            ry = head + ri * row_h
            if ri:
                panel["children"].append({
                    "op": "rect", "var": "rl%d_%d" % (si, ri), "parent": panel["var"],
                    "x": 4, "y": ry, "w": panel["w"] - 2 * CONTENT_INSET - 8, "h": 1,
                    "color": "MUTED"})
            panel["children"].append({
                "op": "text", "var": "lb%d_%d" % (si, ri), "parent": panel["var"],
                "align": "TOP_LEFT", "dx": 10, "dy": ry + 6, "font": "cjk12",
                "color": "INK", "text": row.get("label", "")})
            if row.get("value"):
                panel["children"].append({
                    "op": "text", "var": "vl%d_%d" % (si, ri), "parent": panel["var"],
                    "align": "TOP_RIGHT", "dx": -16 if row.get("chevron") else -6,
                    "dy": ry + 6, "font": "cjk12", "color": "SKY_DARK",
                    "text": row["value"]})
            if row.get("chevron"):
                # the font's own '>' glyph, so preview and firmware share one
                # representation instead of a hand-drawn arrow
                panel["children"].append({
                    "op": "text", "var": "ch%d_%d" % (si, ri), "parent": panel["var"],
                    "align": "TOP_RIGHT", "dx": -6, "dy": ry + 6, "font": "cjk12",
                    "color": "INK", "text": ">"})
            nav_rows.append({"panel": panel["var"], "y": ry, "h": row_h,
                             "label": row.get("label", ""),
                             "action": row.get("action")})
        nodes.append(panel)
        panels.append(panel)
        y += h + gap

    nav = None
    if selectable and nav_rows:
        sel = max(0, min(int(spec.get("selected", 0)), len(nav_rows) - 1))
        row = nav_rows[sel]
        host = next(p for p in panels if p["var"] == row["panel"])
        host["children"].append({
            "op": "rect", "var": "cursor", "parent": host["var"],
            "x": 0, "y": row["y"] + 2, "w": 3, "h": row["h"] - 4,
            "color": spec.get("cursor_color", "YELLOW")})
        nav = {"rows": nav_rows, "row_height": row_h, "selected": sel,
               "head": head_h, "cursor_var": "cursor"}
    return {"nodes": nodes, "nav": nav}


ARCHETYPES = {"dashboard": expand_dashboard, "list": expand_list}


def screen_chrome(spec):
    """ui_pixel_screen_create: sky, cloud, grass, title plate (screen coords)."""
    title = spec.get("title", "")
    face = spec.get("title_font", "cjk24")
    nodes = [
        {"op": "rect", "x": 0, "y": 0, "w": SCREEN_W, "h": SCREEN_H, "color": "SKY"},
        # add_cloud(188, 8)
        {"op": "rect", "x": 189, "y": 15, "w": 43, "h": 10, "color": "INK"},
        {"op": "rect", "x": 193, "y": 12, "w": 35, "h": 10, "color": "WHITE"},
        {"op": "rect", "x": 200, "y": 8, "w": 10, "h": 9, "color": "WHITE"},
        {"op": "rect", "x": 215, "y": 9, "w": 9, "h": 8, "color": "WHITE"},
        # grass ground
        {"op": "rect", "x": 0, "y": 286, "w": 240, "h": 34, "color": "GRASS"},
        {"op": "raw", "x": 0, "y": 286, "w": 240, "h": 4, "hex": 0xA7D93E},
        {"op": "title_plate", "x": 5, "y": 8, "w": 151, "h": 33,
         "text": title, "font": face},
    ]
    for x in range(0, 240, 30):
        nodes.append({"op": "rect", "x": x, "y": 312, "w": 18, "h": 8, "color": "GRASS_DARK"})
        nodes.append({"op": "raw", "x": x + 18, "y": 316, "w": 12, "h": 4, "hex": 0x75452E})
    return nodes


def _subst_text(s, samples):
    for k, v in samples.items():
        s = s.replace("{{%s}}" % k, str(v))
    return s


def _substitute_spec(spec):
    """Preview mode: replace placeholders in a spec copy with sample values,
    BEFORE expansion (the expanders need pct/mark as ints)."""
    sp = json.loads(json.dumps(spec))
    s = sp.get("samples", {})
    if not s:
        return sp
    for m in sp.get("metrics", []):
        for f in ("pct", "mark"):
            v = m.get(f)
            if isinstance(v, str):
                m[f] = int(s.get(v.strip("{} "), 0))
        for f in ("label", "value"):
            if isinstance(m.get(f), str):
                m[f] = _subst_text(m[f], s)
    st = sp.get("status")
    if isinstance(st, dict):
        for f in ("left", "right"):
            if isinstance(st.get(f), str):
                st[f] = _subst_text(st[f], s)
    return sp


def expand(spec, samples=True):
    """spec -> {archetype, capture, title, chrome, nodes, nav}.

    Pass samples=False to keep {{key}} placeholders in place (the code
    generator does this so it can bind them at runtime); spec["samples"]
    supplies the preview values."""
    archetype = spec.get("type", "dashboard")
    if archetype not in ARCHETYPES:
        raise SystemExit("unknown archetype %r; have: %s"
                         % (archetype, ", ".join(sorted(ARCHETYPES))))
    body = ARCHETYPES[archetype](_substitute_spec(spec) if samples else spec)
    return {
        "page": spec.get("page", "page"),
        "archetype": archetype,
        "capture": spec.get("capture", dict(CAPTURE_DEFAULT)),
        "title": spec.get("title", ""),
        "title_font": spec.get("title_font", "cjk24"),
        "chrome": screen_chrome(spec),
        "nodes": body["nodes"],
        "nav": body["nav"],
        "data": spec.get("data"),
        "samples": spec.get("samples", {}),
    }
