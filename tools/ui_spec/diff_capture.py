#!/usr/bin/env python3
"""tools/ui_spec/diff_capture.py -- compare a rendered preview with a device capture.

Reports mismatch rate, an 8px density map, color pairs and per-band bounding
boxes, so a layout error (large contiguous band) is distinguishable from the
known noise floor: LVGL anti-aliases rounded bar corners into the panel color
while the renderer keeps them hard-edged, leaving a few dozen pixels per bar.

--max-pct turns that floor into an explicit gate: exit 0 while the mismatch rate
stays under it, so CI can fail on gross layout drift without failing on corner
blending.

usage: python tools/ui_spec/diff_capture.py <rendered.png> <device.png> [--max-pct 1.0]
"""
import argparse
import sys

from PIL import Image


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rendered")
    ap.add_argument("device")
    ap.add_argument("--max-pct", type=float, default=None,
                    help="pass when the mismatch rate is under this percentage")
    args = ap.parse_args()

    a = Image.open(args.rendered).convert("RGB")
    b = Image.open(args.device).convert("RGB")
    if a.size != b.size:
        print("SIZE MISMATCH: rendered %s vs device %s" % (a.size, b.size))
        return 1
    W, H = a.size
    pa, pb = a.load(), b.load()

    diff = [[False] * W for _ in range(H)]
    total = 0
    pairs = {}
    for y in range(H):
        for x in range(W):
            if pa[x, y] != pb[x, y]:
                diff[y][x] = True
                total += 1
                key = (pa[x, y], pb[x, y])
                pairs[key] = pairs.get(key, 0) + 1

    pct = 100.0 * total / (W * H)
    print("pixels: %d | mismatched: %d (%.2f%%)" % (W * H, total, pct))

    print("\n8px density map (# >=50%, + >=15%, . >0, ' ' = identical):")
    step = 8
    print("    " + "".join(str((x // step) % 10) for x in range(0, W, step)))
    for by in range(0, H, step):
        row = ""
        for bx in range(0, W, step):
            n = sum(1 for y in range(by, min(by + step, H))
                    for x in range(bx, min(bx + step, W)) if diff[y][x])
            cell = step * step
            row += "#" if n >= cell * 0.5 else ("+" if n >= cell * 0.15 else ("." if n else " "))
        print("%3d %s" % (by, row))

    print("\ntop color pairs (rendered -> device):")
    for (ca, cb), n in sorted(pairs.items(), key=lambda kv: -kv[1])[:10]:
        print("  #%02X%02X%02X -> #%02X%02X%02X  x%d" % (ca + cb + (n,)))

    bands = []
    y = 0
    while y < H:
        if any(diff[y]):
            start = y
            while y < H and any(diff[y]):
                y += 1
            xs = [xx for yy in range(start, y) for xx in range(W) if diff[yy][xx]]
            bands.append((start, y - 1, len(xs), min(xs), max(xs)))
        else:
            y += 1
    print("\nmismatch bands (y0-y1, count, x range):")
    for s, e, n, x0, x1 in bands:
        print("  y%3d-%3d  n=%5d  x%d-%d" % (s, e, n, x0, x1))

    if args.max_pct is None:
        return 0 if total == 0 else 1
    if pct <= args.max_pct:
        print("\nPASS: %.2f%% <= --max-pct %.2f%%" % (pct, args.max_pct))
        return 0
    print("\nFAIL: %.2f%% > --max-pct %.2f%%" % (pct, args.max_pct))
    return 1


if __name__ == "__main__":
    sys.exit(main())
