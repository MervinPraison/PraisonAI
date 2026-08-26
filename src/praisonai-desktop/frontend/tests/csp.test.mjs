/**
 * The page must survive the CSP the app actually ships.
 *
 * Configuring any CSP makes Tauri stamp a nonce on the page's <style> tag and
 * a hash on its inline <script> at build time. A nonce or hash in a source list
 * *voids* `'unsafe-inline'` for that directive -- so the moment a CSP exists,
 * every `style=""` attribute in the document stops applying, silently. The
 * visible result was a permanently shown Stop button, a raw file-input widget,
 * and every tool-output block expanded.
 *
 * The first version of this file was regex guesswork and caught none of seven
 * CSP-breaking changes, including a straight revert of the fix. It now resolves
 * variables to the elements they hold before deciding whether a line is a
 * problem, and checks the other four ways a page can set style that the policy
 * blocks: a style attribute in any casing, setAttribute('style'), a <style>
 * element built at runtime, and style= concatenated into innerHTML.
 */
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import test from 'node:test';
import { JSDOM } from 'jsdom';

const HTML = readFileSync(new URL('../../ui/index.html', import.meta.url), 'utf8');
const CONFIG = JSON.parse(
  readFileSync(new URL('../../src-tauri/tauri.conf.json', import.meta.url), 'utf8'));

/** The document with comments blanked, so line numbers still line up.
 *
 *  Line-prefix filtering is not enough: a continuation line inside a block
 *  comment starts with ordinary text, so this file's own explanation of the
 *  bug was once reported as an instance of it.
 */
const CODE = HTML
  .replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '))
  .replace(/(^|[^:])\/\/[^\n]*/g, (m, p) => p + ' '.repeat(m.length - p.length));

const sourceLine = (n) => HTML.split('\n')[n - 1].trim().slice(0, 90);
const lines = () => CODE.split('\n').map((line, i) => [i + 1, line]);

/** Which ids the shipped markup hides with a class rather than an attribute. */
function idsHiddenByClass() {
  const dom = new JSDOM(HTML);
  return new Set([...dom.window.document.querySelectorAll('.is-hidden')]
    .map((el) => el.id).filter(Boolean));
}

/** Map every `const x = document.getElementById('y')` binding to its id. */
function variablesHoldingElements() {
  const map = new Map();
  const pattern = /(\w+)\s*=\s*document\.getElementById\(\s*['"]([^'"]+)['"]\s*\)/g;
  for (const [, name, id] of CODE.matchAll(pattern)) map.set(name, id);
  return map;
}

test('a CSP is configured at all', () => {
  // With csp: null there is no policy and this whole class of bug is moot --
  // along with every protection a CSP gives. Removing it should be a decision,
  // not a side effect.
  assert.ok(CONFIG.app.security.csp, 'no CSP is set; the page is unrestricted');
});

test('no element carries a style attribute, in any casing or quoting', () => {
  // STYLE="..." and style=display:none are the same thing to a parser and the
  // same casualty under the policy.
  const offenders = lines().filter(([, l]) => /\s(?:style)\s*=\s*(?:["'][^"']*["']|[^\s>]+)/i.test(l));
  assert.deepEqual(offenders.map(([n]) => `${n}: ${sourceLine(n)}`), [],
                   'these style attributes will not apply under the shipped CSP; use a class');
});

test('nothing sets a style attribute through the DOM', () => {
  // setAttribute('style', ...) is governed by style-src exactly as the markup
  // attribute is. Confirmed blocked under the real policy in a headless browser.
  const offenders = lines().filter(([, l]) => /setAttribute\(\s*['"]style['"]/i.test(l));
  assert.deepEqual(offenders.map(([n]) => `${n}: ${sourceLine(n)}`), [],
                   'setAttribute("style") is blocked; set .style.<prop> or use a class');
});

test('nothing builds a <style> element at runtime', () => {
  // A <style> created after load carries no nonce, so the policy drops it.
  const offenders = lines().filter(
    ([, l]) => /createElement\(\s*['"]style['"]/i.test(l) || /insertRule\s*\(/.test(l));
  assert.deepEqual(offenders.map(([n]) => `${n}: ${sourceLine(n)}`), [],
                   'a runtime <style> or insertRule is dropped under the shipped CSP');
});

test('no innerHTML string carries a style attribute', () => {
  // Markup assembled in JavaScript is parsed the same way as markup in the
  // file, so a style= inside it is the same casualty.
  const offenders = lines().filter(([, l]) =>
    /innerHTML|insertAdjacentHTML/.test(l) && /\sstyle\s*=/i.test(l));
  assert.deepEqual(offenders.map(([n]) => `${n}: ${sourceLine(n)}`), [],
                   'style= built into innerHTML will not apply; use a class');
});

test('every utility class that replaced an attribute still exists', () => {
  // Otherwise the elements are not hidden at all -- the same bug, arrived at
  // from the other direction.
  for (const rule of ['.is-hidden{display:none}', '.errhint{', '.logpre{', '.runshd{']) {
    assert.ok(HTML.includes(rule), `missing rule: ${rule}`);
  }
});

test('an element hidden by a class is never also driven by inline display', () => {
  // Mixing the two mechanisms is the bug, whichever value is assigned.
  //
  //   hide via `el.style.display='none'`, then reveal via
  //   `classList.remove('is-hidden')` -> the inline rule still wins, and the
  //   element stays hidden from the second turn onward.
  //
  //   hide via the class, then reveal via `el.style.display=''` -> restores
  //   the class default, which is `display:none`, so it never appears at all.
  //
  // Both are "the Stop button does not come back". So for an element the
  // markup hides with a class, any `.style.display` assignment is a defect --
  // which is why this checks the property, not the value it is given.
  //
  // The previous version matched a *variable* name against an id and so
  // checked `stopBtn` against `id="stopBtn"`, which does not exist -- the id
  // is `stop`. It caught nothing. Bindings are resolved now.
  const hidden = idsHiddenByClass();
  const held = variablesHoldingElements();
  assert.ok(hidden.size, 'no element is hidden by a class; has the fix been reverted?');
  assert.ok(held.size, 'no element bindings were found; has the page been restructured?');

  const offenders = [];
  for (const [n, line] of lines()) {
    for (const [, name] of line.matchAll(/(\w+)\.style\.display\s*=/g)) {
      const id = held.get(name);
      if (id && hidden.has(id)) {
        offenders.push(`${n}: ${name} holds #${id}, which the markup hides with a class`
                       + ` -- ${sourceLine(n)}`);
      }
    }
  }
  assert.deepEqual(offenders, [],
                   'this element is hidden by a class; show and hide it with the class');
});

test('the elements meant to start hidden actually are', () => {
  // The stylesheet has to carry the rule, not just the markup the class.
  const dom = new JSDOM(HTML);
  const { document, getComputedStyle } = dom.window;
  for (const id of ['stop', 'filein']) {
    const el = document.getElementById(id);
    assert.ok(el, `#${id} is missing from the page`);
    assert.equal(getComputedStyle(el).display, 'none', `#${id} is visible on load`);
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
