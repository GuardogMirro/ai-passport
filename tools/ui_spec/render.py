#!/usr/bin/env python3
"""tools/ui_spec/render.py -- draw a page spec into a pixel-faithful PNG.

Geometry comes from layout.py (shared with gen_page.py); this file only draws.
It uses the theme palette, ui_pixel panel geometry, the same font files as the
firmware, and RGB565 quantization, so the output can be diffed against a serial
capture pixel by pixel (see diff_capture.py).

usage:
  python tools/ui_spec/render.py <spec.json> <out.png> --font-dir DIR [--capture]
  --font-dir  unpacked Fusion Pixel 12px family (tools/fonttools/fetch_asset.mjs)
  --capture   render only the 240x192 container over black, matching what
              tools/capture_screen.py returns; default renders the whole screen
"""
import argparse
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout as L  # noqa: E402


class Renderer:
    def __init__(self, img, font_dir):
        self.img = img
        self.draw = ImageDraw.Draw(img)
        self.font_dir = font_dir
        self._fonts = {}

    def font(self, face):
        if face not in self._fonts:
            name, size = L.FACES[face][0], L.FACES[face][1]
            self._fonts[face] = ImageFont.truetype(os.path.join(self.font_dir, name), size)
        return self._fonts[face]

    def text_width(self, face, text):
        return int(round(self.font(face).getlength(text)))

    def rect(self, x, y, w, h, c):
        if w > 0 and h > 0:
            self.draw.rectangle([x, y, x + w - 1, y + h - 1], fill=c)

    def rounded(self, x, y, w, h, r, c):
        self.draw.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=r, fill=c)

    def text(self, x, y, face, s, c):
        """1bpp text whose LVGL label box top-left sits at (x, y)."""
        _ttf, _size, line_h, base, dy_corr = L.FACES[face]
        f = self.font(face)
        ascent, descent = f.getmetrics()
        pad = 4
        mask = Image.new("L", (self.text_width(face, s) + 4, ascent + descent + 2 * pad), 0)
        ImageDraw.Draw(mask).text((0, pad), s, font=f, fill=255, anchor="la",
                                  layout_engine=ImageFont.Layout.BASIC)
        mask = mask.point(lambda v: 255 if v >= 128 else 0)
        self.img.paste(c, (x, y + (line_h - base) - (pad + ascent) + dy_corr), mask)

    def bar(self, x, y, w, h, rad, track, fill, pct, bg=None):
        """Track plus indicator: the same rounded shape clipped to pct columns,
        which is how LVGL clips a bar indicator to its own area. Corners are
        left hard-edged on purpose - LVGL anti-aliases them into the panel color
        and modelling that made the diff worse, not better, so corner blending
        is accepted as the noise floor (see diff_capture.py --max-pct).
        """
        # round half up, matching LVGL's indicator width measured on the device
        fw = (w * max(0, min(100, int(pct))) + 50) // 100
        if rad:
            self.rounded(x, y, w, h, rad, track)
        else:
            self.rect(x, y, w, h, track)
        if fw > 0:
            band = Image.new("RGB", (w, h))
            bd = ImageDraw.Draw(band)
            if rad:
                bd.rounded_rectangle([0, 0, w - 1, h - 1], radius=rad, fill=fill)
            else:
                bd.rectangle([0, 0, w - 1, h - 1], fill=fill)
            keep = Image.new("L", (w, h), 0)
            ImageDraw.Draw(keep).rectangle([0, 0, fw - 1, h - 1], fill=255)
            self.img.paste(band, (x, y), keep)


def draw_node(r, node, boxes, off=(0, 0)):
    """boxes maps a parent name to its content box in image coordinates."""
    op = node["op"]

    if op == "raw":
        r.rect(node["x"], node["y"], node["w"], node["h"], L.rgb565(node["hex"]))

    elif op == "title_plate":
        x, y, w, h = node["x"], node["y"], node["w"], node["h"]
        r.rect(x + 4, y + 4, w, h, L.rgb565("INK"))
        r.rect(x, y, w, h, L.rgb565("PAPER"))
        r.draw.rectangle([x, y, x + w - 1, y + h - 1], outline=L.rgb565("INK"), width=3)
        face = node["font"]
        line_h = L.FACES[face][2]
        tw = r.text_width(face, node["text"])
        r.text(x + (w - tw) // 2, y + (h - line_h) // 2, face, node["text"],
               L.rgb565("INK"))

    elif op == "panel":
        # panels carry container-local coords; the screen offset applies here
        x, y = node["x"] + off[0], node["y"] + off[1]
        w, h = node["w"], node["h"]
        r.rect(x + L.PANEL_SHADOW[0], y + L.PANEL_SHADOW[1], w, h, L.rgb565("INK"))
        r.rect(x, y, w, h, L.rgb565(node.get("color", "PAPER")))
        r.draw.rectangle([x, y, x + w - 1, y + h - 1], outline=L.rgb565("INK"),
                         width=L.PANEL_BORDER)
        boxes[node["var"]] = (x + L.CONTENT_INSET, y + L.CONTENT_INSET,
                              w - 2 * L.CONTENT_INSET, h - 2 * L.CONTENT_INSET,
                              L.rgb565(node.get("color", "PAPER")))
        for child in node.get("children", []):
            draw_node(r, child, boxes, off)

    elif op == "rect":
        x, y = node["x"], node["y"]
        if node.get("parent"):
            bx, by = boxes[node["parent"]][:2]
            x, y = bx + x, by + y
        r.rect(x, y, node["w"], node["h"], L.rgb565(node["color"]))

    elif op == "text":
        if node.get("text"):
            face = node["font"]
            line_h = L.FACES[face][2]
            w = r.text_width(face, node["text"])
            x, y = L.resolve(node.get("align", "TOP_LEFT"), node.get("dx", 0),
                             node.get("dy", 0), boxes[node["parent"]][:4], w, line_h)
            r.text(x, y, face, node["text"], L.rgb565(node["color"]))

    elif op == "bar":
        w, h = node["w"], node["h"]
        box = boxes[node["parent"]]
        x, y = L.resolve(node.get("align", "BOTTOM_LEFT"), node.get("dx", 0),
                         node.get("dy", 0), box[:4], w, h)
        r.bar(x, y, w, h, node.get("radius", 0), L.rgb565(node["track"]),
              L.rgb565(node["fill"]), node.get("pct", 0),
              bg=box[4] if len(box) > 4 else None)

    else:
        raise SystemExit("unknown op: %s" % op)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("out")
    ap.add_argument("--font-dir", default=os.environ.get("UI_SPEC_FONT_DIR"))
    ap.add_argument("--capture", action="store_true")
    args = ap.parse_args()
    if not args.font_dir or not os.path.isdir(args.font_dir):
        sys.exit("font dir not found (pass --font-dir or set UI_SPEC_FONT_DIR)")

    with open(args.spec, encoding="utf-8") as f:
        spec = json.load(f)
    page = L.expand(spec)
    cap = page["capture"]

    if args.capture:
        img = Image.new("RGB", (cap["w"], cap["h"]), L.rgb565("BLACK"))
        off = (0, 0)
    else:
        img = Image.new("RGB", (L.SCREEN_W, L.SCREEN_H), L.rgb565("SKY"))
        off = (cap["x"], cap["y"])
    r = Renderer(img, args.font_dir)

    boxes = {"content": (off[0], off[1], cap["w"], cap["h"])}
    if not args.capture:
        for node in page["chrome"]:
            draw_node(r, node, boxes)
    for node in page["nodes"]:
        draw_node(r, node, boxes, off)

    img.save(args.out)
    print("rendered %s (%s) -> %s" % (page["page"], page["archetype"], args.out))


if __name__ == "__main__":
    main()
