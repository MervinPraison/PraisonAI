/**
 * Loads the real index.html in a DOM, stubs only the two things a webview
 * provides (Tauri's invoke and the network), and then *clicks* every control,
 * asserting on what changed.
 *
 * The page is not modified for the test. If a handler is missing, a selector
 * drifts, or a click throws, this fails -- which is the whole point: every
 * previous audit checked that a handler string existed in the source, not that
 * pressing the thing does anything.
 */
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';
import assert from 'node:assert/strict';
import test from 'node:test';

const HTML = readFileSync(new URL('../ui/index.html', import.meta.url), 'utf8');
import { createServer } from 'node:http';
import { extname } from 'node:path';
// jsdom will not resolve a relative ES module import from a file: URL, so the
// page is served for real. Without this the module script never executes and
// every control silently has no handler.
const SRV = createServer((req, res) => {
  const f = req.url === '/' ? '/index.html' : req.url.split('?')[0];
  try {
    const b = readFileSync(new URL('../ui' + f, import.meta.url));
    res.writeHead(200, { 'content-type': extname(f) === '.js' ? 'text/javascript' : 'text/html' });
    res.end(b);
  } catch { res.writeHead(404); res.end(); }
});
await new Promise(r => SRV.listen(0, r));
SRV.unref();
const ORIGIN = 'http://127.0.0.1:' + SRV.address().port;
process.on('exit', () => SRV.close());
const PORT = 65000;

function makeFetch(calls) {
  return async (url, opts = {}) => {
    calls.push(`${opts.method || 'GET'} ${String(url).replace(`http://127.0.0.1:${PORT}`, '')}`);
    const u = String(url);
    const body =
      u.includes('/settings') ? { model: 'gpt-4o-mini', theme: 'system', temperature: 0.7,
                                  approval_mode: 'ask', approval_timeout: 300 }
      : u.includes('/chats/') ? { id: 'c1', title: 'Hi', messages: [
          { role: 'user', content: 'hi' }, { role: 'assistant', content: '**hello**' }] }
      : u.includes('/chats')  ? { chats: [{ id: 'c1', title: 'Hi', updated: 1, count: 2, project: '' }] }
      : u.includes('/logs')   ? { lines: ['12:00:00  turn start'] }
      : u.includes('/search') ? { hits: [{ id: 'c1', title: 'Hi', snippet: 'hi' }] }
      : u.includes('/mcp')    ? { servers: [{ name: 'fs', command: 'npx x', enabled: false }] }
      : u.includes('/update') ? { current: '0.1.0', checked: false, message: 'not configured' }
      : u.includes('/fork')   ? { ok: true, id: 'c1-f1' }
      : { ok: true };
    return { ok: true, json: async () => body, text: async () => '' };
  };
}

async function boot() {
  const calls = [];
  const dom = new JSDOM(HTML, {
    runScripts: 'dangerously', resources: 'usable', url: ORIGIN + '/',
    beforeParse(w) {
      w.__TAURI__ = { core: { invoke: async () => ({ state: 'ready', port: PORT, python: '/py' }) } };
      w.fetch = makeFetch(calls);
      w.requestAnimationFrame = (cb) => setTimeout(cb, 0);
      w.navigator.clipboard = { writeText: async () => {} };
      w.confirm = () => true;
      w.prompt = () => 'Research';
      w.alert = () => {};
      w.scrollTo = () => {};
      Object.defineProperty(w.HTMLElement.prototype, 'scrollIntoView', { value() {} });
    },
  });
  const { window } = dom;
  // wait for the module script's top-level await (engine_status) to settle
  for (let i = 0; i < 60 && !window.document.getElementById('p')?.disabled === false; i++) {
    await new Promise((r) => setTimeout(r, 25));
    if (!window.document.getElementById('p').disabled) break;
  }
  return { window, doc: window.document, calls };
}

const click = (el) => el.dispatchEvent(new el.ownerDocument.defaultView.MouseEvent('click', { bubbles: true }));
const settle = () => new Promise((r) => setTimeout(r, 120));

test('the composer enables once the engine reports ready', async () => {
  const { doc } = await boot();
  assert.equal(doc.getElementById('p').disabled, false, 'textarea still disabled');
  assert.equal(doc.getElementById('send').disabled, false, 'send still disabled');
  assert.match(doc.getElementById('status').textContent, /engine/);
});

test('New chat clears the transcript and shows the hero', async () => {
  const { doc } = await boot();
  await settle();
  click(doc.getElementById('newchat'));
  await settle();
  assert.equal(doc.getElementById('turns').children.length, 0);
  assert.ok(doc.getElementById('thread').classList.contains('empty'), 'hero not shown');
});

test('Sidebar toggle hides and restores the sidebar', async () => {
  const { doc } = await boot();
  const side = doc.getElementById('side');
  const before = side.classList.contains('hidden');
  click(doc.getElementById('toggle'));
  assert.notEqual(side.classList.contains('hidden'), before, 'toggle did nothing');
  click(doc.getElementById('toggle'));
  assert.equal(side.classList.contains('hidden'), before, 'toggle not reversible');
});

test('Tools button toggles its own state', async () => {
  const { doc } = await boot();
  const b = doc.getElementById('toolsBtn');
  const on = b.classList.contains('on');
  click(b);
  assert.notEqual(b.classList.contains('on'), on, 'tools button inert');
});

test('Settings opens and renders rows from the registry', async () => {
  const { doc } = await boot();
  click(doc.getElementById('settings'));
  await settle();
  assert.ok(doc.getElementById('overlay').classList.contains('open'), 'overlay closed');
  const rows = doc.querySelectorAll('.srow');
  assert.ok(rows.length > 0, 'no settings rows rendered');
  assert.ok(doc.getElementById('setq'), 'no search box');
});

test('Settings section buttons switch the visible rows', async () => {
  const { doc } = await boot();
  click(doc.getElementById('settings'));
  await settle();
  const first = doc.querySelector('.srow')?.id;
  const navs = [...doc.querySelectorAll('#setside button')];
  assert.ok(navs.length >= 5, `only ${navs.length} sections`);
  click(navs.find((b) => b.textContent.includes('Safety')));
  await settle();
  assert.notEqual(doc.querySelector('.srow')?.id, first, 'section switch changed nothing');
  assert.ok(doc.getElementById('setting-approval_mode'), 'safety rows missing');
});

test('Settings search filters to matching rows', async () => {
  const { doc, window } = await boot();
  click(doc.getElementById('settings'));
  await settle();
  const q = doc.getElementById('setq');
  q.value = 'temperature';
  q.dispatchEvent(new window.Event('input', { bubbles: true }));
  await settle();
  const ids = [...doc.querySelectorAll('.srow')].map((r) => r.id);
  assert.deepEqual(ids, ['setting-temperature'], `got ${ids}`);
});

test('a toggle row writes to the engine when clicked', async () => {
  const { doc, calls } = await boot();
  click(doc.getElementById('settings'));
  await settle();
  click([...doc.querySelectorAll('#setside button')].find((b) => b.textContent.includes('Chat')));
  await settle();
  const before = calls.filter((c) => c.startsWith('POST /settings')).length;
  click(doc.querySelector('#setting-auto_title .sw'));
  await settle();
  assert.ok(calls.filter((c) => c.startsWith('POST /settings')).length > before,
    'toggle did not save');
});

test('Search opens and a result opens that conversation', async () => {
  const { doc, window, calls } = await boot();
  click(doc.getElementById('search'));
  await settle();
  const q = doc.getElementById('q');
  q.value = 'hi';
  q.dispatchEvent(new window.Event('input', { bubbles: true }));
  await new Promise((r) => setTimeout(r, 300));
  const res = doc.querySelector('.res');
  assert.ok(res, 'no search result rendered');
  click(res);
  await settle();
  assert.ok(calls.some((c) => c.includes('/chats/c1')), 'result did not open the chat');
});

test('Engine log opens and shows lines', async () => {
  const { doc } = await boot();
  click(doc.getElementById('logsBtn'));
  await settle();
  assert.match(doc.getElementById('panel').textContent, /turn start/);
});

test('every shell button produces its own observable effect', async () => {
  const { doc, calls } = await boot();
  await settle();
  const overlay = doc.getElementById('overlay');
  // A blanket "the DOM changed" assertion passes for the wrong reasons and
  // fails for good ones -- New chat on an empty transcript legitimately
  // changes no markup. Each button asserts the effect it actually owns.
  const cases = [
    ['newchat',  async () => { const n = calls.length; click(doc.getElementById('newchat'));
                  await settle(); return calls.length > n; }],
    ['search',   async () => { click(doc.getElementById('search')); await settle();
                  const ok = !!doc.getElementById('q'); overlay.classList.remove('open'); return ok; }],
    ['settings', async () => { click(doc.getElementById('settings')); await settle();
                  const ok = doc.querySelectorAll('.srow').length > 0;
                  overlay.classList.remove('open'); return ok; }],
    ['logsBtn',  async () => { click(doc.getElementById('logsBtn')); await settle();
                  const ok = /turn start/.test(doc.getElementById('panel').textContent);
                  overlay.classList.remove('open'); return ok; }],
    ['toggle',   async () => { const b = doc.getElementById('side').classList.contains('hidden');
                  click(doc.getElementById('toggle'));
                  const ok = doc.getElementById('side').classList.contains('hidden') !== b;
                  click(doc.getElementById('toggle')); return ok; }],
    ['toolsBtn', async () => { const b = doc.getElementById('toolsBtn').classList.contains('on');
                  click(doc.getElementById('toolsBtn'));
                  return doc.getElementById('toolsBtn').classList.contains('on') !== b; }],
    ['attach',   async () => { let opened = false;
                  doc.getElementById('filein').click = () => { opened = true; };
                  click(doc.getElementById('attach')); await settle(); return opened; }],
    ['modelpill',async () => { click(doc.getElementById('modelpill')); await settle();
                  const ok = doc.querySelectorAll('.srow').length > 0;
                  overlay.classList.remove('open'); return ok; }],
  ];
  for (const [id, run] of cases) {
    assert.ok(doc.getElementById(id), `#${id} missing from the DOM`);
    assert.ok(await run(), `#${id} produced no observable effect`);
  }
});
