// probe_coverage.mjs -- per-variant and union coverage of our charset across all TTFs in a dir
import { createRequire } from 'node:module';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(join(here, 'node_modules', 'lv_font_conv', 'package.json'));
const opentype = require('opentype.js');

const dir = process.argv[2] || join(here, 'ark12');
const charset = [...readFileSync(join(here, 'charset.txt'), 'utf8')];
const wanted = new Set(charset.map(c => c.codePointAt(0)));

const files = readdirSync(dir).filter(f => f.endsWith('.ttf')).sort();
const coveredBy = new Map(); // codepoint -> first font that has it
const perFont = {};

for (const f of files) {
  const font = opentype.loadSync(join(dir, f));
  let hit = 0;
  for (const cp of wanted) {
    if (font.charToGlyph(String.fromCodePoint(cp)).index !== 0) {
      hit++;
      if (!coveredBy.has(cp)) coveredBy.set(cp, f);
    }
  }
  perFont[f] = { glyphs: font.numGlyphs, hit };
  console.log(`${f.padEnd(40)} glyphs=${String(font.numGlyphs).padStart(6)} charsetHit=${hit}/${wanted.size}`);
}

const missing = [...wanted].filter(cp => !coveredBy.has(cp)).sort((a, b) => a - b);
console.log('---');
console.log('union coverage:', coveredBy.size, '/', wanted.size, '| still missing:', missing.length);
if (missing.length) {
  console.log('missing codepoints:', missing.slice(0, 50).map(c => 'U+' + c.toString(16).toUpperCase()).join(' '));
  console.log('missing chars:', missing.slice(0, 50).map(c => String.fromCodePoint(c)).join(''));
}
// which font is the primary source for most chars
const tally = {};
for (const f of coveredBy.values()) tally[f] = (tally[f] || 0) + 1;
console.log('primary source tally:', JSON.stringify(tally));
