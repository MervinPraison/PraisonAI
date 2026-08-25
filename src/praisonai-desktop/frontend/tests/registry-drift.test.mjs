/**
 * The registry copies must match the block the app actually ships.
 *
 * frontend/src/settings-registry.js had drifted three whole sections behind
 * ui/index.html -- missing Data, About and Integrations, with a different
 * api_key description. Nothing imported it, so nothing noticed. A stale copy of
 * a registry is worse than no copy: it is the file someone reads to find out
 * what the settings are.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const TOOL = fileURLToPath(new URL('../../tools/sync-registry.mjs', import.meta.url));
const HTML = fileURLToPath(new URL('../../ui/index.html', import.meta.url));

test('the registry copies are in sync with ui/index.html', () => {
  execFileSync(process.execPath, [TOOL, '--check'], { stdio: 'pipe' });
});

test('every setting names a section that exists', () => {
  // A setting whose section has no tab is rendered by nothing -- the same
  // silent-nothing shape as a setting that is stored and never read.
  const html = readFileSync(HTML, 'utf8');
  const sections = [...html.matchAll(/\{ id: "(\w+)",/g)].map((m) => m[1]);
  assert.equal(sections.length, 8, `sections changed: ${sections.join(',')}`);
  const keys = [...html.matchAll(/\{ key: "(\w+)", section: "(\w+)"/g)];
  // A lower bound, so a truncated block is caught; raise it when adding
  // settings rather than letting it decay.
  assert.ok(keys.length >= 29, `only ${keys.length} settings found`);
  for (const [, key, section] of keys) {
    assert.ok(sections.includes(section), `${key} is in unknown section "${section}"`);
  }
});
