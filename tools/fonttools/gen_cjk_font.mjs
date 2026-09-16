// gen_cjk_font.mjs -- generate the LVGL CJK font C array from Ark Pixel 16px (OFL-1.1).
//
// Why a compiled-in C array (not a runtime .bin):
//   the board has no PSRAM and ~111KB free DRAM; a C array keeps glyph bitmaps
//   and descriptor tables in flash (const), costing zero heap. Runtime binfont
//   loading would allocate tables proportional to glyph count.
//
// Usage: node gen_cjk_font.mjs <charset.txt> <font.ttf> <out.c> [size] [bpp]
import { spawnSync } from 'node:child_process';
import { readFileSync, statSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const conv = join(here, 'node_modules', 'lv_font_conv', 'lv_font_conv.js');

const charsetPath = process.argv[2] || join(here, 'charset.txt');
const fontPath = process.argv[3] || join(here, 'ark', 'ark-pixel-16px-monospaced-zh_cn.ttf');
const outPath = process.argv[4] || join(here, 'ui_font_cjk_16.c');
const size = process.argv[5] || '16';
const bpp = process.argv[6] || '1';
const fallback = process.argv[7] || 'lv_font_montserrat_14';
const fontName = 'ui_font_cjk_' + size;

const symbols = readFileSync(charsetPath, 'utf8');
if (!existsSync(fontPath)) { console.error('font not found:', fontPath); process.exit(1); }
console.log(`charset ${symbols.length} chars | font ${fontPath} | size ${size} bpp ${bpp} -> ${outPath}`);

const args = [
  conv,
  '--font', fontPath,
  '--size', size,
  '--bpp', bpp,
  '--format', 'lvgl',
  '--no-compress',
  '--autohint-off',
  '--no-kerning',
  '--lv-include', 'lvgl.h',
  '--lv-font-name', fontName,
  '--lv-fallback', fallback,
  '--symbols', symbols,
  '-o', outPath,
];

const r = spawnSync(process.execPath, args, { stdio: 'inherit' });
if (r.status !== 0) { console.error('converter failed, status', r.status); process.exit(r.status || 1); }

const src = readFileSync(outPath, 'utf8');
const glyphCount = (src.match(/\.bitmap_index =/g) || []).length;
const cmaps = (src.match(/static const lv_font_fmt_txt_cmap_t/g) || []).length;
console.log('---');
console.log('output bytes:', statSync(outPath).size, '(~' + Math.round(statSync(outPath).size / 1024) + 'KB C source)');
console.log('glyph descriptors:', glyphCount, '| cmap tables:', cmaps);
console.log('font symbol:', fontName);
