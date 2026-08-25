/**
 * The settings registry lives inlined in ui/index.html, because the page is one
 * classic script and a module import would not execute in a file: webview.
 *
 * Two standalone copies existed alongside it, imported by nothing, and one had
 * drifted three whole sections behind. This regenerates them from the shipped
 * block so the copies cannot lie. `--check` fails instead of writing, which is
 * what registry-drift.test.mjs runs.
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const HTML = fileURLToPath(new URL('../ui/index.html', import.meta.url));
const TARGETS = ['../ui/settings-registry.js', '../frontend/src/settings-registry.js']
  .map((p) => fileURLToPath(new URL(p, import.meta.url)));

const HEADER = `/**
 * Settings as data -- GENERATED. Do not edit.
 *
 * The shipped copy is the block inlined in ui/index.html. Regenerate with
 * \`node tools/sync-registry.mjs\`; \`--check\` verifies without writing.
 */
`;

export function extract(html = readFileSync(HTML, 'utf8')) {
  const start = html.indexOf('const SECTIONS = [');
  const end = html.indexOf('window.__REGISTRY__');
  if (start < 0 || end < 0 || end < start) {
    throw new Error('the registry block is no longer where it was in ui/index.html');
  }
  const body = html.slice(start, end).trimEnd();
  return `${HEADER}export ${body.replaceAll('\nfunction ', '\nexport function ')
    .replace('const SECTIONS', 'const SECTIONS')}\n`;
}

const want = extract();
const check = process.argv.includes('--check');
let drifted = [];
for (const t of TARGETS) {
  let have = '';
  try { have = readFileSync(t, 'utf8'); } catch {}
  if (have === want) continue;
  if (check) drifted.push(t);
  else writeFileSync(t, want);
}
if (check && drifted.length) {
  console.error('registry copies have drifted:\n  ' + drifted.join('\n  '));
  process.exit(1);
}
if (!check) console.log(`synced ${TARGETS.length} registry copies`);
