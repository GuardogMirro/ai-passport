#!/usr/bin/env python3
"""tools/ui_spec/render.py -- render a page spec into a pixel-faithful PNG.

The preview is the contract between a human description and the firmware: it
uses the same palette, the same panel geometry and the same font files the
device uses, and it quantizes to RGB565 exactly like the panel does, so a
rendered page can be diffed against a serial screenshot pixel by pixel.

Archetypes expand into geometry here, so a spec stays declarative:
  dashboard  metric blocks (label + hero value + bar with pace mark)
  list       grouped rows, iOS-Settings style (label left, value right, chevron)

usage:
  python tools/ui_spec/render.py <spec.json> <out.png> [--font-dir DIR]
      [--capture] [--screen]
  --capture  render only the 240x192 screenshot container over black
             (matches what tools/capture_screen.py returns)
  --screen   render the full 240x320 screen including sky, plate and grass
"""
import argparse
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

# ---- theme: single source of truth, mirrors main/ui_pixel.h -----------------
PALETTE = {
    "SKY": 0x1689E8, "SKY_DARK": 0x0872C9, "INK": 0x17202A, "PAPER": 0xF4F4EA,
    "GRASS": 0x82BE2D, "GRASS_DARK": 0x55951D, "YELLOW": 0xFFD928,
    "ORANGE": 0xFFB23E, "RED": 0xE43B2F, "MUTED": 0xD9E7EC,
    "WHITE": 0xFFFFFF, "BLACK": 0x000000,
}

PANEL_BORDER = 4      # ui_pixel_panel_create: border_width 4
PANEL_PAD = 7         # ui_pixel_panel_create: pad_all 7
PANEL_SHADOW = (5, 6) # ui_pixel_panel_create: ink block offset
CONTENT_INSET = PANEL_BORDER + PANEL_PAD  # 11: child (0,0) inside a panel

SCREEN_W, SCREEN_H = 240, 320
CAPTURE_W, CAPTURE_H = 240, 192

# Font faces: (ttf basename, px size, lvgl line_height, lvgl base_line, dy_corr).
# line_height/base_line are the values lv_font_conv wrote into the generated
# faces. dy_corr is measured, not derived: device captures put glyph ink 1px
# (12px face) and 2px (24px face) below a pure-baseline model, which tracks the
# faces' dominant .ofs_y (-2 and -4, read from assets/fonts/ui_font_cjk_*.c).
# Re-measure with tools/ui_spec/diff_capture.py after changing fonts.
FACES = {
    "cjk12": ("fusion-pixel-12px-monospaced-zh_hans.ttf", 12, 11, 2, 1),
    "cjk24": ("fusion-pixel-12px-monospaced-zh_hans.ttf", 24, 22, 4, 2),
}


def rgb565(color):
    """Quantize a 24-bit color the way the ST7789 panel stores it."""
    r, g, b = (color >> 16) & 255, (color >> 8) & 255, color & 255
    return ((r >> 3) << 3, (g >> 2) << 2, (b >> 3) << 3)


def color(name):
    return rgb565(PALETTE[name] if isinstance(name, str) else name)


class Renderer:
    def __init__(self, img, font_dir):
        self.img = img
        self.draw = ImageDraw.Draw(img)
        self.font_dir = font_dir
        self._fonts = {}

    def font(self, face):
        if face not in self._fonts:
            name, size = FACES[face][0], FACES[face][1]
            path = os.path.join(self.font_dir, name)
            self._fonts[face] = ImageFont.truetype(path, size)
        return self._fonts[face]

    def metrics(self, face):
        return FACES[face][2], FACES[face][3]

    def dy_corr(self, face):
        return FACES[face][4]

    def text_width(self, face, text):
        return int(round(self.font(face).getlength(text)))

    def rect(self, x, y, w, h, c):
        self.draw.rectangle([x, y, x + w - 1, y + h - 1], fill=c)

    def rounded(self, x, y, w, h, r, c):
        self.draw.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=r, fill=c)

    def text(self, x, y, face, text, c):
        """Draw 1bpp text with its LVGL label box top-left at (x, y).

        LVGL puts the first baseline at label_top + (line_height - base_line);
        FreeType reports the ascent, so the mask is pasted at the offset that
        lands the baseline exactly there. Calibrated against device captures:
        x is exact and ink counts match, so glyph shapes agree.
        """
        line_h, base = self.metrics(face)
        f = self.font(face)
        ascent, descent = f.getmetrics()
        pad = 4
        w = self.text_width(face, text) + 4
        mask = Image.new("L", (w, ascent + descent + 2 * pad), 0)
        ImageDraw.Draw(mask).text((0, pad), text, font=f, fill=255, anchor="la",
                                  layout_engine=ImageFont.Layout.BASIC)
        mask = mask.point(lambda v: 255 if v >= 128 else 0)
        paste_y = y + (line_h - base) - (pad + ascent) + self.dy_corr(face)
        self.img.paste(c, (x, paste_y), mask)


def align_xy(align, dx, dy, box, w, h):
    """LVGL-style alignment of a w x h child inside box=(bx,by,bw,bh)."""
    bx, by, bw, bh = box
    if align in ("TOP_LEFT", "LEFT"):     x, y = bx, by
    elif align in ("TOP_RIGHT", "RIGHT"): x, y = bx + bw - w, by
    elif align == "TOP_MID":              x, y = bx + (bw - w) // 2, by
    elif align in ("BOTTOM_LEFT",):       x, y = bx, by + bh - h
    elif align in ("BOTTOM_RIGHT",):      x, y = bx + bw - w, by + bh - h
    elif align == "BOTTOM_MID":           x, y = bx + (bw - w) // 2, by + bh - h
    elif align == "CENTER":               x, y = bx + (bw - w) // 2, by + (bh - h) // 2
    else:                                 x, y = bx, by
    return x + dx, y + dy


# ---- archetype expansion ----------------------------------------------------

def expand_dashboard(spec):
    """Metric blocks stacked vertically, then a status row - the balance layout."""
    nodes = []
    gap = spec.get("gap", 6)
    top = spec.get("top", 8)
    height = spec.get("block_height", 78)
    metrics = spec.get("metrics", [])
    for i, m in enumerate(metrics):
        y = top + i * (height + gap)
        nodes.append({"type": "panel", "x": 12, "y": y, "w": 216, "h": height,
                      "color": m.get("color", "PAPER"), "children": [
            {"type": "label", "text": m.get("label", ""), "font": "cjk12",
             "color": "SKY_DARK", "align": "TOP_LEFT", "dx": 4, "dy": 1},
            {"type": "label", "text": m.get("value", ""), "font": "cjk24",
             "color": m.get("value_color", "INK"), "align": "TOP_LEFT", "dx": 4, "dy": 15},
            {"type": "bar", "pct": m.get("pct", 0), "mark": m.get("mark"),
             "w": 132, "h": 14, "align": "BOTTOM_LEFT", "dx": 4, "dy": -3,
             "track": "MUTED", "fill": m.get("fill", "GRASS"), "radius": 7},
        ]})
    st = spec.get("status")
    if st:
        n = len(metrics)
        # panels_bottom + 2, matching the firmware's status row placement
        sy = st.get("y", top + (n - 1) * (height + gap) + height + 2)
        nodes.append({"type": "label", "text": st.get("left", ""), "font": "cjk12",
                      "color": st.get("left_color", "GRASS_DARK"),
                      "align": "TOP_LEFT", "dx": 4, "dy": sy, "root": True})
        nodes.append({"type": "label", "text": st.get("right", ""), "font": "cjk12",
                      "color": "INK", "align": "TOP_RIGHT", "dx": -6, "dy": sy,
                      "root": True})
    return nodes


def expand_list(spec):
    """Grouped rows (iOS Settings pattern): section title, then rows of
    label-left / value-right / chevron, each group on its own paper panel."""
    nodes = []
    y = spec.get("top", 8)
    row_h = spec.get("row_height", 30)
    for sec in spec.get("sections", []):
        rows = sec.get("rows", [])
        head = 14 if sec.get("title") else 0
        h = head + len(rows) * row_h + 6
        children = []
        if sec.get("title"):
            children.append({"type": "label", "text": sec["title"], "font": "cjk12",
                             "color": "SKY_DARK", "align": "TOP_LEFT", "dx": 4, "dy": 0})
        for i, row in enumerate(rows):
            ry = head + i * row_h
            children.append({"type": "label", "text": row.get("label", ""), "font": "cjk12",
                             "color": "INK", "align": "TOP_LEFT", "dx": 4, "dy": ry + 6})
            if row.get("value"):
                children.append({"type": "label", "text": row["value"], "font": "cjk12",
                                 "color": "SKY_DARK", "align": "TOP_RIGHT", "dx": -16,
                                 "dy": ry + 6})
            if row.get("chevron"):
                children.append({"type": "chevron", "align": "TOP_RIGHT",
                                 "dx": -10, "dy": ry + 8, "color": "INK"})
            if i:
                children.append({"type": "rule", "x": 4, "y": ry, "w": 196,
                                 "color": "MUTED"})
        nodes.append({"type": "panel", "x": 12, "y": y, "w": 216, "h": h,
                      "color": "PAPER", "children": children})
        y += h + spec.get("gap", 8)
    return nodes


ARCHETYPES = {"dashboard": expand_dashboard, "list": expand_list}


# ---- node drawing -----------------------------------------------------------

def draw_node(r, node, box):
    kind = node["type"]
    if kind == "panel":
        x, y, w, h = node["x"], node["y"], node["w"], node["h"]
        r.rect(x + PANEL_SHADOW[0], y + PANEL_SHADOW[1], w, h, color("INK"))
        r.rect(x, y, w, h, color(node.get("color", "PAPER")))
        r.draw.rectangle([x, y, x + w - 1, y + h - 1], outline=color("INK"),
                         width=PANEL_BORDER)
        inner = (x + CONTENT_INSET, y + CONTENT_INSET,
                 w - 2 * CONTENT_INSET, h - 2 * CONTENT_INSET)
        for child in node.get("children", []):
            draw_node(r, child, inner)
        return

    if kind == "label":
        text = node.get("text", "")
        if not text:
            return
        face = node.get("font", "cjk12")
        line_h, _ = r.metrics(face)
        w = r.text_width(face, text)
        bx, by, bw, bh = box
        x, y = align_xy(node.get("align", "TOP_LEFT"), node.get("dx", 0),
                        node.get("dy", 0), box, w, line_h)
        r.text(x, y, face, text, color(node.get("color", "INK")))
        return

    if kind == "bar":
        w, h = node["w"], node["h"]
        x, y = align_xy(node.get("align", "BOTTOM_LEFT"), node.get("dx", 0),
                        node.get("dy", 0), box, w, h)
        rad = node.get("radius", 0)
        pct = max(0, min(100, int(node.get("pct", 0))))
        if rad:
            r.rounded(x, y, w, h, rad, color(node.get("track", "MUTED")))
        else:
            r.rect(x, y, w, h, color(node.get("track", "MUTED")))
        fw = w * pct // 100
        if fw > 0:
            if rad:
                r.rounded(x, y, max(fw, 2 * rad), h, rad, color(node.get("fill", "GRASS")))
                if fw < 2 * rad:  # thin fill: clip to the real width
                    r.rect(x + fw, y, 2 * rad - fw, h, color(node.get("track", "MUTED")))
            else:
                r.rect(x, y, fw, h, color(node.get("fill", "GRASS")))
        mark = node.get("mark")
        if mark is not None and 0 <= mark <= 100:
            mx = x + mark * w // 100
            r.rect(mx, y, 2, h, color("INK"))
        return

    if kind == "rect":
        x, y = node.get("x", 0), node.get("y", 0)
        bx, by, _, _ = box
        r.rect(bx + x, by + y, node["w"], node["h"], color(node.get("color", "INK")))
        return

    if kind == "rule":
        bx, by, _, _ = box
        r.rect(bx + node["x"], by + node["y"], node["w"], 1, color(node.get("color", "MUTED")))
        return

    if kind == "chevron":
        x, y = align_xy(node.get("align", "TOP_RIGHT"), node.get("dx", 0),
                        node.get("dy", 0), box, 6, 10)
        c = color(node.get("color", "INK"))
        for i in range(5):  # 像素风右箭头 '>'
            r.rect(x + i, y + i, 1, 1, c)
            r.rect(x + i, y + 8 - i, 1, 1, c)
        return

    raise SystemExit("unknown node type: %s" % kind)


def draw_screen_chrome(r, title, title_font):
    """ui_pixel_screen_create: sky, cloud, grass, title plate."""
    r.rect(0, 0, SCREEN_W, SCREEN_H, color("SKY"))
    cx, cy = 188, 8  # add_cloud
    r.rect(cx + 1, cy + 7, 43, 10, color("INK"))
    r.rect(cx + 5, cy + 4, 35, 10, color("WHITE"))
    r.rect(cx + 12, cy, 10, 9, color("WHITE"))
    r.rect(cx + 27, cy + 1, 9, 8, color("WHITE"))
    r.rect(0, 286, 240, 34, color("GRASS"))
    r.rect(0, 286, 240, 4, rgb565(0xA7D93E))
    for x in range(0, 240, 30):
        r.rect(x, 312, 18, 8, color("GRASS_DARK"))
        r.rect(x + 18, 316, 12, 4, rgb565(0x75452E))
    r.rect(9, 12, 151, 33, color("INK"))
    r.rect(5, 8, 151, 33, color("PAPER"))
    r.draw.rectangle([5, 8, 155, 40], outline=color("INK"), width=3)
    tw = r.text_width(title_font, title)
    line_h, _ = r.metrics(title_font)
    r.text(5 + (151 - tw) // 2, 8 + (33 - line_h) // 2, title_font, title, color("INK"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("out")
    ap.add_argument("--font-dir", default=None)
    ap.add_argument("--capture", action="store_true",
                    help="render only the 240x192 container over black")
    args = ap.parse_args()

    with open(args.spec, encoding="utf-8") as f:
        spec = json.load(f)
    font_dir = args.font_dir or os.environ.get("UI_SPEC_FONT_DIR")
    if not font_dir or not os.path.isdir(font_dir):
        sys.exit("font dir not found (pass --font-dir or set UI_SPEC_FONT_DIR): %r" % font_dir)

    archetype = spec.get("type", "dashboard")
    if archetype not in ARCHETYPES:
        sys.exit("unknown archetype %r; have: %s" % (archetype, ", ".join(ARCHETYPES)))
    nodes = ARCHETYPES[archetype](spec)

    # Spec coordinates are container-local, matching how the firmware adds
    # children to the 240x192 screenshot container.
    cap = spec.get("capture", {"x": 0, "y": 48, "w": CAPTURE_W, "h": CAPTURE_H})
    if args.capture:
        img = Image.new("RGB", (cap["w"], cap["h"]), color("BLACK"))
        r = Renderer(img, font_dir)
        box = (0, 0, cap["w"], cap["h"])
    else:
        img = Image.new("RGB", (SCREEN_W, SCREEN_H), color("SKY"))
        r = Renderer(img, font_dir)
        draw_screen_chrome(r, spec.get("title", ""), spec.get("title_font", "cjk24"))
        box = (cap["x"], cap["y"], cap["w"], cap["h"])

    for node in nodes:
        node.pop("root", None)
        draw_node(r, node, box)

    img.save(args.out)
    print("rendered %s (%s) -> %s" % (spec.get("page", "?"), archetype, args.out))


if __name__ == "__main__":
    main()
