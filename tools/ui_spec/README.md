<p align="right">
  <a href="README.zh_CN.md">简体中文</a> · <strong>English</strong>
</p>

# tools/ui_spec — describe a page, preview it, generate its firmware

A page is described once, in JSON. `render.py` draws it into a PNG that matches
the panel, and `gen_page.py` translates the same description into
`main/demo_<page>.c` plus its registration. Layout lives in `layout.py` and
nowhere else, so the preview and the firmware are two renderings of one
description rather than two implementations that can drift.

## Loop

```sh
# 1. describe the page
$EDITOR tools/ui_spec/pages/<page>.json

# 2. see it (whole screen, or just the capture container)
python tools/ui_spec/render.py tools/ui_spec/pages/<page>.json /tmp/<page>.png \
  --font-dir /tmp/fusion12
python tools/ui_spec/render.py tools/ui_spec/pages/<page>.json /tmp/<page>_cap.png \
  --font-dir /tmp/fusion12 --capture

# 3. gate the glyphs, then generate and register the page
python tools/fonttools/check_font_coverage.py tools/fonttools/charset_body.txt \
  main/*.c tools/ui_spec/pages/*.json
python tools/ui_spec/gen_page.py tools/ui_spec/pages/<page>.json \
  --out main/demo_<page>.c --register --repo . --force

# 4. build, flash, capture, and diff against the preview
python tools/capture_screen.py COM5 /tmp/device.png
python tools/ui_spec/diff_capture.py /tmp/<page>_cap.png /tmp/device.png --max-pct 1.0
```

`--font-dir` points at an unpacked Fusion Pixel 12px family
(`tools/fonttools/fetch_asset.mjs` downloads it). `--capture` renders only the
240x192 container over black, which is what `capture_screen.py` returns.

## Archetypes

A spec names an archetype and its content; `layout.py` derives the geometry.
Coordinates are container-local, matching how the firmware parents children to
the capture container.

| Archetype | Shape | Example |
| --- | --- | --- |
| `dashboard` | metric blocks: 12px label, 24px hero value, bar with pace mark; then a status row | `pages/balance.json` |
| `list` | grouped rows in the iOS Settings pattern: section title, label left, value right, `>` chevron, hairline separators, movable cursor | `pages/settings.json` |

## Measured fidelity

Against a real capture of the hand-written balance page: **154 of 46080 pixels
differ (0.33%)**. Against the settings page generated end-to-end by this tool
(spec -> C -> build -> flash -> capture): **0 of 46080 pixels differ (0.00%)**.
Text x positions and ink counts match exactly; the balance-page residual is
LVGL anti-aliasing rounded bar corners into the panel color (the renderer keeps
them hard-edged — modelling the blend made the diff worse) plus one glyph
detail. `diff_capture.py --max-pct` turns that floor into a gate: a layout
error shows up as a large contiguous band, far above it.

## What the generator encodes

Rules taken from `AGENTS.md`, the agent guide and `main.c`, so generated pages
behave like hand-written ones:

- `enter`/`exit` run with the LVGL lock held by `main.c`; `key` does **not**, so
  generated key handlers take `bsp_lvgl_lock()` themselves.
- `exit` clears the screenshot target, deletes the screen and nulls pointers.
  Static pages own no tasks or timers; a spec that needs them must stop them
  before the delete.
- The OK long-press back gesture stays `main.c`'s and is never re-implemented.
- The page registers its capture container with `serial_screenshot_set_target`,
  which is what makes step 4 possible.
- `--register` patches `main/demo.h`, `main/CMakeLists.txt` and `main/main.c`:
  a `DEMOS[]` entry, the matching positional `s_ok[]` slot (an unset slot shows
  `[FAIL]` and blocks entry), the mascot moved into the grid's free cell when
  `DEMO_COUNT` is odd, and CJK-aware menu label fonts.

## Files

| File | Role |
| --- | --- |
| `layout.py` | theme constants and archetype expansion — the only place geometry is computed |
| `render.py` | layout → PNG (RGB565 quantized, real font files, calibrated baselines) |
| `gen_page.py` | layout → `main/demo_<page>.c`, plus `--register` |
| `diff_capture.py` | rendered PNG vs device capture → rate, density map, color pairs, bands |
| `pages/*.json` | page descriptions |

Text baselines carry a measured per-face correction (`dy_corr` in `layout.FACES`),
derived from device captures and consistent with the faces' dominant `.ofs_y`
(-2 at 12px, -4 at 24px). Re-measure with `diff_capture.py` after changing fonts.

## Data pages

A `"data"` section turns the page live. v1 ships one adapter:

```json
"data":   { "kind": "glm_quota", "poll_ms": 300000 },
"samples": { "w5.pct": 17, "w5.theo": 20, "w5.reset": "13:19", ... }
```

`glm_quota` fetches the Zhipu quota endpoint **directly over HTTPS** (bearer key
from net_config.h, certificate bundle verified), normalizes the two windows and
computes the pace mark on-device after SNTP sync — no PC involved, so the badge
works with the computer off. Placeholders (`{{w5.pct}}` etc.) bind widgets to
the adapter; `samples` are preview-only values and never compiled.

Device-verified end to end (2026-09-16): TLS handshake and certificate
validation pass, endpoint answers 200, and the rendered bars and pace marks
match the PC-side proxy pixel for pixel. Two firmware lessons from that run are
baked in: the 92KB screenshot buffer became lazy (allocate on capture, free
after) because a resident one starves mbedtls at 13.7KB free heap, and
WIFI_PS_NONE is avoided — it fixed nothing (the timeouts were a heap symptom)
and full-power radio correlated with phantom key events while the badge was
handled.

## Not built yet

Row actions and sub-pages, NVS-backed values, adapters beyond glm_quota, and
wiring `diff_capture.py` into CI. The LAN balance page stays hand-written;
migrating it means choosing one of the two data paths.
