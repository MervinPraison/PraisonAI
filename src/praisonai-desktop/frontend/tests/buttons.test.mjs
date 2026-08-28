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

const HTML = readFileSync(new URL('../../ui/index.html', import.meta.url), 'utf8');
import { createServer } from 'node:http';
import { extname } from 'node:path';
// jsdom will not resolve a relative ES module import from a file: URL, so the
// page is served for real. Without this the module script never executes and
// every control silently has no handler.
const SRV = createServer((req, res) => {
  const f = req.url === '/' ? '/index.html' : req.url.split('?')[0];
  try {
    const b = readFileSync(new URL('../../ui' + f, import.meta.url));
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
      // This webview has no JS dialog panel: prompt returns null and alert
      // shows nothing. Modelling the real platform is the point -- a stub that
      // returns 'x' hid that "Move to project" issued no request at all.
      w.prompt = () => null;
      w.alert = () => { throw new Error('no dialog panel here'); };
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

test('right-click on a chat moves it to a project via the in-app prompt', async () => {
  const { doc, window, calls } = await boot();
  await settle();
  const row = doc.querySelector('#chats .chat, #chats > div');
  assert.ok(row, 'no chat row rendered');
  // window.prompt returns null here, so if the handler used it this issues
  // nothing. The in-app askText panel must appear instead.
  row.dispatchEvent(new window.MouseEvent('contextmenu', { bubbles: true, cancelable: true }));
  await settle();
  const inp = doc.querySelector('.confirm-back .txt');
  assert.ok(inp, 'no in-app text prompt shown (window.prompt returned null)');
  inp.value = 'Research';
  click([...doc.querySelectorAll('.confirm-back .ok')].pop());
  await settle();
  assert.ok(calls.some((c) => c.startsWith('POST /project/')),
    'moving to a project issued no request');
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

// ---- message queue -------------------------------------------------------
// A turn is held open by a never-resolving stream so "while running" is a real
// state rather than a race the test hopes to win.
async function bootStreaming() {
  const calls = [];
  let releaseStream;
  const held = new Promise((r) => { releaseStream = r; });
  const dom = new JSDOM(HTML, {
    runScripts: 'dangerously', resources: 'usable', url: ORIGIN + '/',
    beforeParse(w) {
      w.__TAURI__ = { core: { invoke: async () => ({ state: 'ready', port: PORT }) } };
      w.fetch = async (url, opts = {}) => {
        calls.push(`${opts.method || 'GET'} ${String(url).replace(`http://127.0.0.1:${PORT}`, '')}`);
        if (String(url).includes('/chat')) {
          return { ok: true, body: { getReader: () => ({
            read: () => held.then(() => ({ done: true })), cancel: async () => {} }) } };
        }
        return { ok: true, json: async () => ({ chats: [], lines: [], hits: [],
          model: 'gpt-4o-mini', theme: 'system' }), text: async () => '' };
      };
      w.requestAnimationFrame = (cb) => setTimeout(cb, 0);
      w.navigator.clipboard = { writeText: async () => {} };
      w.confirm = () => true; w.alert = () => {};
      Object.defineProperty(w.HTMLElement.prototype, 'scrollIntoView', { value() {} });
    },
  });
  const { window } = dom;
  for (let i = 0; i < 60; i++) {
    await new Promise((r) => setTimeout(r, 25));
    if (!window.document.getElementById('p').disabled) break;
  }
  return { doc: window.document, window, calls, releaseStream };
}

const send = (doc, window, text) => {
  doc.getElementById('p').value = text;
  doc.getElementById('f').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
};

test('the composer stays usable while a turn is running', async () => {
  const { doc, window } = await bootStreaming();
  send(doc, window, 'first');
  await settle();
  assert.equal(doc.getElementById('p').disabled, false,
    'the composer was disabled mid-run, so a queued thought cannot be typed');
  assert.notEqual(doc.getElementById('stop').style.display, 'none', 'Stop not shown');
});

test('a message typed mid-run is queued, not sent', async () => {
  const { doc, window, calls } = await bootStreaming();
  send(doc, window, 'first');
  await settle();
  const chatCalls = calls.filter((c) => c.includes('/chat')).length;
  send(doc, window, 'second');
  await settle();
  assert.equal(calls.filter((c) => c.includes('/chat')).length, chatCalls,
    'the queued message was sent immediately instead of queued');
  const rows = doc.querySelectorAll('.qrow');
  assert.equal(rows.length, 1, 'the queue is not shown to the user');
  assert.match(rows[0].textContent, /second/);
});

test('the queue preserves order and shows its position', async () => {
  const { doc, window } = await bootStreaming();
  send(doc, window, 'first');
  await settle();
  send(doc, window, 'alpha'); await settle();
  send(doc, window, 'beta');  await settle();
  const rows = [...doc.querySelectorAll('.qrow')];
  assert.equal(rows.length, 2);
  assert.match(rows[0].textContent, /1 of 2/);
  assert.match(rows[0].textContent, /alpha/);
  assert.match(rows[1].textContent, /beta/);
});

test('a queued message can be removed before it runs', async () => {
  const { doc, window } = await bootStreaming();
  send(doc, window, 'first');
  await settle();
  send(doc, window, 'discard me'); await settle();
  click(doc.querySelector('.qrow .x'));
  await settle();
  assert.equal(doc.querySelectorAll('.qrow').length, 0, 'removing a queued message did nothing');
});

test('the queue drains when the turn finishes', async () => {
  const { doc, window, calls, releaseStream } = await bootStreaming();
  send(doc, window, 'first');
  await settle();
  send(doc, window, 'queued one'); await settle();
  const before = calls.filter((c) => c.includes('/chat')).length;
  releaseStream();
  await new Promise((r) => setTimeout(r, 400));
  assert.ok(calls.filter((c) => c.includes('/chat')).length > before,
    'the queued message never sent after the turn ended');
  assert.equal(doc.querySelectorAll('.qrow').length, 0, 'the queue row was not cleared');
});

test('Stop discards the queue rather than silently starting the next turn', async () => {
  const { doc, window } = await bootStreaming();
  send(doc, window, 'first');
  await settle();
  send(doc, window, 'should not run'); await settle();
  assert.equal(doc.querySelectorAll('.qrow').length, 1);
  click(doc.getElementById('stop'));
  await new Promise((r) => setTimeout(r, 300));
  assert.equal(doc.querySelectorAll('.qrow').length, 0,
    'stopping a turn left the queue armed, so the next prompt runs unasked');
});

// ---- deleting a conversation --------------------------------------------
// A DELETE the engine could not perform (read-only or synced data dir) must
// not blank the open transcript: doing so is how a conversation closed on
// screen and reappeared in the sidebar on the next refresh.
async function bootWithDelete(deleteOk) {
  const calls = [];
  const dom = new JSDOM(HTML, {
    runScripts: 'dangerously', resources: 'usable', url: ORIGIN + '/',
    beforeParse(w) {
      w.__TAURI__ = { core: { invoke: async () => ({ state: 'ready', port: PORT }) } };
      w.fetch = async (url, opts = {}) => {
        const method = opts.method || 'GET';
        calls.push(`${method} ${String(url).replace(`http://127.0.0.1:${PORT}`, '')}`);
        const u = String(url);
        if (method === 'DELETE') {
          return { ok: deleteOk, status: deleteOk ? 200 : 500,
                   json: async () => ({ ok: deleteOk }), text: async () => '' };
        }
        const body =
          u.includes('/chats/') ? { id: 'c1', title: 'Hi', messages: [
              { role: 'user', content: 'hi' },
              { role: 'assistant', content: '**hello**' }] }
          : u.includes('/chats')  ? { chats: [{ id: 'c1', title: 'Hi', updated: 1, count: 2, project: '' }] }
          : { ok: true, model: 'gpt-4o-mini', theme: 'system' };
        return { ok: true, status: 200, json: async () => body, text: async () => '' };
      };
      w.requestAnimationFrame = (cb) => setTimeout(cb, 0);
      w.navigator.clipboard = { writeText: async () => {} };
      w.confirm = () => true; w.prompt = () => ''; w.alert = () => {};
      Object.defineProperty(w.HTMLElement.prototype, 'scrollIntoView', { value() {} });
    },
  });
  const { window } = dom;
  for (let i = 0; i < 60; i++) {
    await new Promise((r) => setTimeout(r, 25));
    if (!window.document.getElementById('p').disabled) break;
  }
  // The confirm dialog is a custom overlay, not window.confirm; auto-accept it.
  window.askConfirm = async () => true;
  return { doc: window.document, window, calls };
}

test('a failed DELETE keeps the open transcript rather than blanking it', async () => {
  const { doc, window } = await bootWithDelete(false);
  await settle();
  // Open the conversation so the transcript has children and is the active id.
  click(doc.querySelector('#chats .chat'));
  await settle();
  assert.ok(doc.getElementById('turns').children.length > 0, 'transcript did not open');
  const before = doc.getElementById('turns').children.length;
  click(doc.querySelector('#chats .chat .x'));
  await settle();
  assert.equal(doc.getElementById('turns').children.length, before,
    'a delete the engine refused still blanked the open transcript');
});

test('a successful DELETE clears the open transcript', async () => {
  const { doc, window } = await bootWithDelete(true);
  await settle();
  click(doc.querySelector('#chats .chat'));
  await settle();
  assert.ok(doc.getElementById('turns').children.length > 0, 'transcript did not open');
  click(doc.querySelector('#chats .chat .x'));
  await settle();
  assert.equal(doc.getElementById('turns').children.length, 0,
    'a successful delete left the deleted conversation on screen');
});

// ---- Clear-all with a partial failure ------------------------------------
// The open transcript must follow storage, not the batch result: if the active
// conversation was deleted but another one failed, the transcript must still be
// blanked -- otherwise it lingers on screen while gone on disk.
async function bootWithClear(failIds) {
  const calls = [];
  const dom = new JSDOM(HTML, {
    runScripts: 'dangerously', resources: 'usable', url: ORIGIN + '/',
    beforeParse(w) {
      w.__TAURI__ = { core: { invoke: async () => ({ state: 'ready', port: PORT }) } };
      w.fetch = async (url, opts = {}) => {
        const method = opts.method || 'GET';
        const path = String(url).replace(`http://127.0.0.1:${PORT}`, '');
        calls.push(`${method} ${path}`);
        const u = String(url);
        if (method === 'DELETE') {
          const id = path.split('/').pop();
          const ok = !failIds.includes(id);
          return { ok, status: ok ? 200 : 500, json: async () => ({ ok }), text: async () => '' };
        }
        const body =
          u.includes('/chats/') ? { id: u.split('/').pop(), title: 'Hi', messages: [
              { role: 'user', content: 'hi' },
              { role: 'assistant', content: '**hello**' }] }
          : u.includes('/chats')  ? { chats: [
              { id: 'c1', title: 'One', updated: 2, count: 2, project: '' },
              { id: 'c2', title: 'Two', updated: 1, count: 2, project: '' }] }
          : { ok: true, model: 'gpt-4o-mini', theme: 'system' };
        return { ok: true, status: 200, json: async () => body, text: async () => '' };
      };
      w.requestAnimationFrame = (cb) => setTimeout(cb, 0);
      w.navigator.clipboard = { writeText: async () => {} };
      w.confirm = () => true; w.prompt = () => ''; w.alert = () => {};
      Object.defineProperty(w.HTMLElement.prototype, 'scrollIntoView', { value() {} });
    },
  });
  const { window } = dom;
  for (let i = 0; i < 60; i++) {
    await new Promise((r) => setTimeout(r, 25));
    if (!window.document.getElementById('p').disabled) break;
  }
  window.askConfirm = async () => true;
  return { doc: window.document, window, calls };
}

test('clear-all blanks the active transcript even when another delete fails', async () => {
  const { doc, window } = await bootWithClear(['c2']);
  await settle();
  // Open c1 so it is the active transcript; c2's delete will fail.
  click(doc.querySelector('#chats .chat'));
  await settle();
  assert.ok(doc.getElementById('turns').children.length > 0, 'transcript did not open');
  window.runAction({ action: 'clear' });
  await settle();
  assert.equal(doc.getElementById('turns').children.length, 0,
    'the active conversation was deleted from storage but its transcript stayed on screen');
});
