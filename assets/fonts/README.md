<p align="right">
  <a href="README.zh_CN.md">简体中文</a> · <strong>English</strong>
</p>

# CJK Pixel Font Faces

Chinese text on the device is rendered by these two faces, compiled into the
firmware. Latin letters and digits fall back to Montserrat.

## Files and naming

| File | Symbol | Size | Use |
| --- | --- | --- | --- |
| `ui_font_cjk_12.c` | `ui_font_cjk_12` | 12px | body text, labels, status line — `ui_pixel_font_body()` |
| `ui_font_cjk_24.c` | `ui_font_cjk_24` | 24px (integer 2x of the 12px design) | titles, hero numbers — `ui_pixel_font_title()` |

Naming: `ui_font_cjk_<px>.c`, and the symbol matches the file name. Both are
`lv_font_conv` output (bitmaps + glyph tables + cmap) kept as `const` data in
flash, so they cost **zero heap**. This board has no PSRAM and little spare
internal DRAM; runtime `.bin` font loading is avoided because it builds tables
in heap proportional to the glyph count.

## Integration

- `main/CMakeLists.txt` lists both `.c` files in `SRCS`.
- Application code takes faces only through `ui_pixel_font_body()` and
  `ui_pixel_font_title()` in `main/ui_pixel.h` (one theme-layer entry point);
  it does not extern the symbols directly.
- For a Chinese screen title use
  `ui_pixel_screen_create_font(title, ui_pixel_font_title())`. ASCII-only titles
  keep using `ui_pixel_screen_create(title)`.

## Charset

4505 glyphs, listed in `tools/fonttools/charset_body.txt`. Requested set:
ASCII `0x20-0x7E`, GB2312 rows 1-9 (682 chars: fullwidth punctuation such as
U+FF0C and U+FF1A, fullwidth alphanumerics, unit symbols), GB2312 level 1
(3755 chars), plus a few extras — 4538 in total. The source font covers 4505 of
them; the 33 uncovered ones are math symbols (U+2208, U+2211, U+221A, U+2264 and
neighbours) that no UI string needs, and `emit_charset.mjs` drops them by
measuring the font instead of keeping a hand-written exclusion list.

Check coverage before building, so a missing glyph is reported as an error
instead of showing up as a placeholder box on the panel:

```sh
python tools/fonttools/check_font_coverage.py tools/fonttools/charset_body.txt main/*.c
```

## Source and license

- Source font: **Fusion Pixel 12px Monospaced zh_hans**, v2026.09.01, from
  `TakWolf/fusion-pixel-font`, under the **SIL Open Font License 1.1** (full
  text in `OFL.txt` beside this file).
- Selection was measured on 2026-09-16 rather than assumed: Ark Pixel 10px and
  16px are reduced sets covering 3721 of 3895 of the then-charset (174 GB2312
  level-1 chars absent, including U+5373, U+52BF, U+6267, U+60A0, U+60D1), and
  the union of all seven Ark Pixel 12px language variants also stops at 3721.
  Fusion Pixel 12px covers everything except the math symbols above.
- Windows system fonts (SimHei, SimSun, YaHei) are Microsoft-licensed and not
  redistributable, so they are not used here.

## Regeneration

See `tools/fonttools/README.md`: one command chain, about a minute, needs
Node.js and `npm i lv_font_conv`.
