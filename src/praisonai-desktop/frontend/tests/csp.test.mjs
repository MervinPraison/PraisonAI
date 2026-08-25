/**
 * The page must survive the CSP the app actually ships.
 *
 * Configuring any CSP makes Tauri stamp a nonce on the page's <style> tag and
 * a hash on its inline <script> at build time. A nonce or hash in a source list
 * *voids* `'unsafe-inline'` for that directive -- so the moment a CSP exists,
 * every `style=""` attribute in the document stops applying, silently.
 *
 * The visible result was a permanently shown red Stop button, a raw file-input
 * widget, and every tool-output block expanded. Nothing errors; it just looks
 * broken on first launch.
 *
 * jsdom does not enforce CSP, so this checks the two things that can be
 * checked statically and that are exactly what regressed: no style attributes
 * in the shipped markup, and nothing building one into innerHTML.
 */
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import test from 'node:test';

const HTML = readFileSync(new URL('../../ui/index.html', import.meta.url), 'utf8');
const CONFIG = JSON.parse(
  readFileSync(new URL('../../src-tauri/tauri.conf.json', import.meta.url), 'utf8'));

/** Source lines with comments blanked out.
 *
 *  Line-prefix filtering is not enough: a continuation line inside a block
 *  comment starts with ordinary text, so this file's own explanation of the
 *  bug was reported as an instance of it. Comments are blanked rather than
 *  dropped so the line numbers still point at the real file.
 */
function codeLines() {
  const blanked = HTML.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '))
                      .replace(/(^|[^:])\/\/[^\n]*/g, (m, p) => p + ' '.repeat(m.length - p.length));
  return blanked.split('\n').map((line, i) => [i + 1, line]);
}

/** The same line from the real file, for a readable failure message. */
function sourceLine(n) {
  return HTML.split('\n')[n - 1].trim().slice(0, 80);
}

test('a CSP is configured at all', () => {
  // With csp: null there is no policy, and this whole class of bug is moot --
  // along with every protection a CSP gives. If someone removes it, this test
  // should be reconsidered deliberately, not silently.
  assert.ok(CONFIG.app.security.csp, 'no CSP is set; the page is unrestricted');
});

test('no element carries a style attribute', () => {
  const offenders = codeLines().filter(([, line]) => /\sstyle\s*=\s*["']/.test(line));
  assert.deepEqual(
    offenders.map(([n]) => `${n}: ${sourceLine(n)}`),
    [],
    'these style attributes will not apply under the shipped CSP; use a class',
  );
});

test('the utility classes that replaced them exist', () => {
  // Otherwise the elements are not hidden at all, which is the same bug with
  // a different cause.
  for (const rule of ['.is-hidden{display:none}']) {
    assert.ok(HTML.includes(rule), `missing rule: ${rule}`);
  }
});

test('nothing reveals an element by clearing an inline display', () => {
  // `el.style.display=''` restores the class-driven default -- which is now
  // `display:none`. An element hidden by a class must be revealed by removing
  // the class, or it never appears again.
  const offenders = codeLines().filter(([, line]) => /\.style\.display\s*=\s*['"]{2}/.test(line));
  for (const [n, line] of offenders) {
    const el = /(\w+)\.style\.display/.exec(line)?.[1];
    const hiddenByClass = new RegExp(`id="${el}"[^>]*class="[^"]*is-hidden`, 'i').test(HTML)
      || new RegExp(`class="[^"]*is-hidden[^"]*"[^>]*id="${el}"`, 'i').test(HTML);
    assert.ok(!hiddenByClass,
              `${n}: ${el} is hidden by a class, so clearing its inline display leaves it hidden`);
  }
});

test('the CSP lets the page reach its own engine', () => {
  // The webview talks to Python over loopback on a port chosen at runtime.
  // Without these sources every fetch and the training event stream fail.
  const csp = CONFIG.app.security.csp;
  assert.match(csp, /connect-src[^;]*127\.0\.0\.1:\*/, `connect-src cannot reach the engine: ${csp}`);
  assert.match(csp, /img-src[^;]*data:/, 'img-src blocks data: URIs');
  assert.match(csp, /img-src[^;]*blob:/, 'img-src blocks blob: URIs');
});
