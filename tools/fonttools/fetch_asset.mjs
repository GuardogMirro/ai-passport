// fetch_asset.mjs -- download any GitHub release asset by name pattern, via API url
// usage: node fetch_asset.mjs <owner/repo> <name-regex> <out-path>
import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';

const [repo, pattern, out] = process.argv.slice(2);
if (!repo || !pattern || !out) { console.error('usage: fetch_asset.mjs <owner/repo> <regex> <out>'); process.exit(2); }

const rel = await (await fetch(`https://api.github.com/repos/${repo}/releases/latest`, {
  headers: { 'user-agent': 'font-fetch' }, signal: AbortSignal.timeout(30000)
})).json();
const re = new RegExp(pattern);
const asset = (rel.assets || []).find(a => re.test(a.name));
if (!asset) { console.error('no asset matching', pattern, 'in', rel.tag_name); process.exit(1); }
console.log('asset:', asset.name, (asset.size / 1048576).toFixed(1) + 'MB');

const r = await fetch(asset.browser_download_url, {
  headers: { 'user-agent': 'font-fetch' }, signal: AbortSignal.timeout(600000), redirect: 'follow'
});
if (!r.ok) { console.error('HTTP', r.status); process.exit(1); }
const buf = Buffer.from(await r.arrayBuffer());
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, buf);
console.log('wrote', buf.length, 'bytes ->', out);
