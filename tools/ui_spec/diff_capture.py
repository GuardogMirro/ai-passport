#!/usr/bin/env python3
"""tools/ui_spec/diff_capture.py -- compare a rendered preview with a device capture.

Reports mismatch rate, an 8px density map, and per-cluster bounding boxes, so a
layout error (big contiguous block) is distinguishable from glyph rasterization
differences (thin, scattered inside text rows).

usage: python tools/ui_spec/diff_capture.py <rendered.png> <device.png>
"""
import sys

from PIL import Image


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    a = Image.open(sys.argv[1]).convert("RGB")
    b = Image.open(sys.argv[2]).convert("RGB")
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

    print("pixels: %d | mismatched: %d (%.2f%%)" % (W * H, total, 100.0 * total / (W * H)))

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

    # row bands containing mismatches, to separate text rows from chrome
    bands = []
    y = 0
    while y < H:
        if any(diff[y]):
            start = y
            while y < H and any(diff[y]):
                y += 1
            n = sum(1 for yy in range(start, y) for xx in range(W) if diff[yy][xx])
            xs = [xx for yy in range(start, y) for xx in range(W) if diff[yy][xx]]
            bands.append((start, y - 1, n, min(xs), max(xs)))
        else:
            y += 1
    print("\nmismatch bands (y0-y1, count, x range):")
    for s, e, n, x0, x1 in bands:
        print("  y%3d-%3d  n=%5d  x%d-%d" % (s, e, n, x0, x1))
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
