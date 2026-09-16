<p align="right">
  <a href="README.zh_CN.md">简体中文</a> · <strong>English</strong>
</p>

# tools/fonttools — CJK font generation chain

Generates the LVGL C font faces from an open-source pixel font. Output lands in
`assets/fonts/`; the rules for that directory are in `assets/README.md` (Fonts
section) and `assets/fonts/README.md`.

## Dependencies

- Node.js (tested on v24) plus `npm i lv_font_conv` (tested on 1.5.3, which
  brings opentype.js).
- Python 3 for the charset step (standard library only).
- Network access to GitHub Releases for the source font. Note: on this machine
  PowerShell `Invoke-WebRequest` goes through schannel and is blocked by TLS
  interception, while `node fetch` (undici) works — the download script is
  written that way on purpose.

## Command chain

```sh
# 1. Fetch the source font (match a release asset by name regex; the script
#    resolves the real browser_download_url through the API instead of guessing)
node tools/fonttools/fetch_asset.mjs TakWolf/fusion-pixel-font \
  "^fusion-pixel-font-12px-monospaced-ttf-v.*\.zip$" /tmp/fusion12.zip
#    unzip, then use fusion-pixel-12px-monospaced-zh_hans.ttf

# 2. Enumerate the requested charset offline (GB2312 rows 1-9 + level 1 + extras)
python tools/fonttools/gen_charset.py /tmp/charset.txt

# 3. Measure the family's real coverage and emit the covered subset
node tools/fonttools/emit_charset.mjs /tmp/fusion12 /tmp/charset.txt \
  tools/fonttools/charset_body.txt

# 4. Generate both faces (12px body, 24px title)
node tools/fonttools/gen_cjk_font.mjs tools/fonttools/charset_body.txt <ttf> \
  assets/fonts/ui_font_cjk_12.c 12 1 lv_font_montserrat_14
node tools/fonttools/gen_cjk_font.mjs tools/fonttools/charset_body.txt <ttf> \
  assets/fonts/ui_font_cjk_24.c 24 1 lv_font_montserrat_20

# 5. Gate: every non-ASCII UI literal must be covered by the charset
python tools/fonttools/check_font_coverage.py tools/fonttools/charset_body.txt main/*.c
```

## Script roles

| Script | Role |
| --- | --- |
| `fetch_asset.mjs` | Download a GitHub Releases asset matched by name regex, using the API-provided download URL |
| `gen_charset.py` | Enumerate the requested charset offline: GB2312 rows 1-9 (symbols, fullwidth punctuation) + level 1 (3755 hanzi) + extras |
| `emit_charset.mjs` | Measure each candidate face's coverage via opentype.js, print the table, and write the covered subset as `charset_body.txt` |
| `gen_cjk_font.mjs` | Run lv_font_conv to emit an LVGL C face; reports glyph count and size |
| `check_font_coverage.py` | Gate: fail when a UI string literal uses a glyph absent from the charset |

`charset_body.txt` is the single source of truth shared by the generator, the
compiled faces, and the gate — the font decides it, so the three cannot drift.

## Why these parameters

- `--bpp 1`: a pixel font has only two states, so 1bpp is the smallest and stays
  crisp instead of looking soft.
- `--no-compress`: avoids depending on `LV_USE_FONT_COMPRESSED`, one less config
  variable; flash has room (both faces together are about 405KB of the 7.9MB
  app partition).
- `--autohint-off`: keeps the font's own pixel grid instead of letting hinting
  move stems.
- `--no-kerning`: a monospaced pixel font needs no kerning table.
- The 24px face is an integer upscale of the 12px design (unitsPerEm 1200, so
  100 units per design pixel): each design pixel becomes exactly a 2x2 block,
  giving clean chunky pixels rather than the soft edges of re-rasterized
  vectors.
- Faces are compiled in as `const` C arrays instead of loaded from `.bin` at
  runtime: on a board without PSRAM, runtime loading would allocate tables in
  heap proportional to glyph count, which this firmware cannot afford.
