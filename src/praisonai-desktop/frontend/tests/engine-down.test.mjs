/**
 * What the app does when the engine failed to start.
 *
 * Every button below used to be a complete no-op in this state: the handler
 * built a URL containing `127.0.0.1:null`, the fetch threw, and the throw
 * happened *before* `overlay.classList.add('open')` -- so the click produced
 * nothing at all, not even an error. The Engine log was the worst of them: the
 * one panel that explains why the engine failed was unreachable exactly when
 * the engine had failed.
 *
 * The existing suites all boot with a healthy engine stub, so all three passed.
 */
import { readFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { extname } from 'node:path';
import { JSDOM } from 'jsdom';
import assert from 'node:assert/strict';
import test from 'node:test';

const HTML = readFileSync(new URL('../../ui/index.html', import.meta.url), 'utf8');
const SRV = createServer((req, res) => {
  const f = req.url === '/' ? '/index.html' : req.url.split('?')[0];
  try {
    const b = readFileSync(new URL('../../ui' + f, import.meta.url));
    res.writeHead(200, { 'content-type': extname(f) === '.js' ? 'text/javascript' : 'text/html' });
    res.end(b);
  } catch { res.writeHead(404); res.end(); }
});
await new Promise((r) => SRV.listen(0, r));
SRV.unref();
const ORIGIN = 'http://127.0.0.1:' + SRV.address().port;
process.on('exit', () => SRV.close());

/** Boot with the shell reporting that the engine could not start. */
async function bootFailed() {
  const rejections = [];
  const dom = new JSDOM(HTML, {
    runScripts: 'dangerously', resources: 'usable', url: ORIGIN + '/',
    beforeParse(w) {
      w.__TAURI__ = { core: { invoke: async () => ({
        state: 'failed', reason: 'Engine crashed',
        detail: 'exited before it was ready', tail: 'traceback' }) },
        event: { listen: async () => () => {} } };
      // Any request in this state is a bug: there is no port to talk to.
      w.fetch = async () => { throw new TypeError('fetch failed'); };
      w.requestAnimationFrame = (cb) => setTimeout(cb, 0);
      w.navigator.clipboard = { writeText: async () => {} };
      w.confirm = () => true; w.prompt = () => 'x'; w.alert = () => {}; w.scrollTo = () => {};
      w.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
      w.addEventListener('unhandledrejection', (e) => rejections.push(String(e.reason)));
      Object.defineProperty(w.HTMLElement.prototype, 'scrollIntoView', { value() {} });
    },
  });
  const { window } = dom;
  await new Promise((r) => setTimeout(r, 400));
  return { window, doc: window.document, rejections };
}

const click = (el) =>
  el.dispatchEvent(new el.ownerDocument.defaultView.MouseEvent('click', { bubbles: true }));

test('the failure itself is reported in the transcript', async () => {
  const { doc } = await bootFailed();
  assert.match(doc.getElementById('status').textContent, /fail/i);
  assert.ok(doc.querySelector('.err'), 'the engine failure was never shown');
});

for (const [id, label] of [['settings', 'Settings'], ['logsBtn', 'Engine log'], ['search', 'Search']]) {
  test(`${label} explains itself instead of doing nothing`, async () => {
    const b = await bootFailed();
    click(b.doc.getElementById(id));
    await new Promise((r) => setTimeout(r, 80));
    assert.ok(b.doc.getElementById('overlay').classList.contains('open'),
      `${label} produced no visible response at all`);
    assert.match(b.doc.getElementById('panel').textContent, /engine/i,
      `${label} opened but said nothing about the engine`);
  });
}

test('Export does not fake a backup when the engine is unreachable', async () => {
  const writes = [];
  const dom = new JSDOM(HTML, {
    runScripts: 'dangerously', resources: 'usable', url: ORIGIN + '/',
    beforeParse(w) {
      w.__TAURI__ = { core: { invoke: async () => ({
        state: 'failed', reason: 'Engine crashed',
        detail: 'exited before it was ready', tail: 'traceback' }) },
        event: { listen: async () => () => {} } };
      w.fetch = async () => { throw new TypeError('fetch failed'); };
      w.requestAnimationFrame = (cb) => setTimeout(cb, 0);
      w.navigator.clipboard = { writeText: async (t) => { writes.push(t); } };
      w.confirm = () => true; w.prompt = () => 'x'; w.alert = () => {}; w.scrollTo = () => {};
      w.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
      Object.defineProperty(w.HTMLElement.prototype, 'scrollIntoView', { value() {} });
    },
  });
  const { window } = dom;
  await new Promise((r) => setTimeout(r, 400));

  await window.runAction({ action: 'export' });
  await new Promise((r) => setTimeout(r, 20));

  assert.deepEqual(writes, [],
    'the clipboard was written despite the export failing -- a stale paste would masquerade as a backup');
  assert.ok(window.document.getElementById('toast'),
    'the failed export said nothing');
  assert.match(window.document.getElementById('toast').textContent, /did not run|could not/i,
    'the failed export produced no error message');
});

test('no unhandled rejection escapes any of the three', async () => {
  const b = await bootFailed();
  for (const id of ['settings', 'logsBtn', 'search']) {
    click(b.doc.getElementById(id));
    await new Promise((r) => setTimeout(r, 60));
  }
  assert.deepEqual(b.rejections.length, 0,
    `unhandled: ${b.rejections.join(' | ')}`);
});
