// emit_charset.mjs -- measure a candidate font family's real coverage of the
// requested charset, then emit the covered subset as the build charset.
//
// The font is the source of truth: instead of maintaining a hand-written drop
// list, this writes exactly the characters the chosen face can render, so
// check_font_coverage.py and the generated faces can never disagree.
//
// usage: node emit_charset.mjs <font-dir> <charset.txt> [out-charset.txt]
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(join(here, 'node_modules', 'lv_font_conv', 'package.json'));
const opentype = require('opentype.js');

const [dirArg, charsetArg, outArg] = process.argv.slice(2);
const dir = dirArg || join(here, 'fusion12');
const charsetPath = charsetArg || join(here, 'charset.txt');
const outPath = outArg || join(here, 'charset_body.txt');

const wanted = [...new Set([...readFileSync(charsetPath, 'utf8')])].map(c => c.codePointAt(0));
const files = readdirSync(dir).filter(f => f.endsWith('.ttf')).sort();
if (!files.length) { console.error('no .ttf in', dir); process.exit(1); }

const coveredBy = new Map(); // codepoint -> first font that covers it
for (const f of files) {
  const font = opentype.loadSync(join(dir, f));
  let hit = 0;
  for (const cp of wanted) {
    if (font.charToGlyph(String.fromCodePoint(cp)).index !== 0) {
      hit++;
      if (!coveredBy.has(cp)) coveredBy.set(cp, f);
    }
  }
  console.log(`${f.padEnd(42)} glyphs=${String(font.numGlyphs).padStart(6)} hit=${hit}/${wanted.length}`);
}

const missing = wanted.filter(cp => !coveredBy.has(cp)).sort((a, b) => a - b);
const kept = wanted.filter(cp => coveredBy.has(cp)).sort((a, b) => a - b);
writeFileSync(outPath, kept.map(cp => String.fromCodePoint(cp)).join(''), 'utf8');

console.log('---');
console.log('union coverage:', coveredBy.size, '/', wanted.length, '| dropped:', missing.length);
console.log('dropped codepoints:', missing.map(c => 'U+' + c.toString(16).toUpperCase()).join(' '));
console.log('wrote', kept.length, 'chars ->', outPath);
const tally = {};
for (const f of coveredBy.values()) tally[f] = (tally[f] || 0) + 1;
console.log('primary source tally:', JSON.stringify(tally));
