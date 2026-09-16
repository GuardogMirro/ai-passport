<p align="right">
  <a href="README.zh_CN.md">简体中文</a> · <strong>English</strong>
</p>

# tools/ui_spec — declarative page descriptions and pixel-faithful previews

A page is described once, in JSON, and rendered on the host into a PNG that
matches what the panel shows. The preview is the review surface: layout is
checked on screen in a second, before any firmware build, and the same file is
the input for code generation.

## Why a preview can be trusted

`render.py` draws with the same palette as `main/ui_pixel.h`, the same panel
geometry as `ui_pixel_panel_create` (4px ink border, 7px padding, ink shadow at
+5/+6), the same font files the device uses, and it quantizes every color to
RGB565 the way the ST7789 stores it. Measured against a real serial capture of
the balance page: **128 of 46080 pixels differ (0.28%)**, all of them on
anti-aliased bar corners plus one glyph rasterization detail — no layout error.
Text x positions and ink counts match exactly.

Reproduce:

```sh
python tools/ui_spec/render.py tools/ui_spec/pages/balance.json /tmp/preview.png \
  --font-dir /tmp/fusion12 --capture
python tools/capture_screen.py COM5 /tmp/device.png   # device must show that page
python tools/ui_spec/diff_capture.py /tmp/preview.png /tmp/device.png
```

`--font-dir` points at an unpacked Fusion Pixel 12px family
(`tools/fonttools/fetch_asset.mjs` downloads it). `--capture` renders only the
240x192 screenshot container over black, which is what `capture_screen.py`
returns; without it the full 240x320 screen is drawn, including sky, cloud,
grass and the title plate.

## Archetypes

A spec names an archetype and its content; geometry is derived here, so
descriptions stay declarative.

| Archetype | Shape | Used by |
| --- | --- | --- |
| `dashboard` | stacked metric blocks: 12px label, 24px hero value, bar with a pace mark; then a status row | balance page |
| `list` | grouped rows in the iOS Settings pattern: section title, rows of label-left / value-right / chevron, hairline separators | settings-style menus |

Coordinates in a spec are container-local, matching how the firmware parents
children to the 240x192 capture container.

## Files

| File | Role |
| --- | --- |
| `render.py` | spec → PNG (archetype expansion, theme geometry, RGB565 quantization, calibrated text baseline) |
| `diff_capture.py` | rendered PNG vs device capture → mismatch rate, 8px density map, color pairs, mismatch bands |
| `pages/*.json` | page descriptions |

Text baselines carry a measured per-face correction (`dy_corr` in `FACES`),
derived from device captures and consistent with the faces' dominant `.ofs_y`
(-2 at 12px, -4 at 24px). Re-measure it with `diff_capture.py` after changing
fonts.

## Before rendering or building

Screen text must exist in the compiled charset, otherwise the panel draws a
placeholder box:

```sh
python tools/fonttools/check_font_coverage.py tools/fonttools/charset_body.txt \
  main/*.c tools/ui_spec/pages/*.json
```

The gate reads `.json` specs as well as C sources.

## Not built yet

The spec → C generator (emitting `main/demo_<page>.c` plus `DEMOS[]`
registration) and wiring `diff_capture.py` into CI. Today the preview and the
gate are the working parts; firmware pages are still written by hand.
