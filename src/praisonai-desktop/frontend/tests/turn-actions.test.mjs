/**
 * Fork and Delete used to compute a message index from DOM position: the Nth
 * user turn on screen was assumed to be message 2N on disk. That assumption
 * breaks the moment a turn is not persisted -- a cancelled or errored turn
 * stays on screen and is never written -- and from then on every Fork and
 * Delete points one exchange too far. The 404 was ignored and the turn was
 * removed from the screen anyway, so it looked deleted and came back on reopen.
 *
 * These tests drive the real page with canned SSE and assert on the index the
 * page actually sends.
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
const PORT = 65000;

const frame = (ev, data) => `event: ${ev}\ndata: ${JSON.stringify(data)}\n\n`;

/** One turn that fails without persisting: the shape that caused the desync. */
const FAILED_TURN = [frame('start', { run_id: 'r1' }), frame('error', { message: 'boom' })];
/** A turn that persists at a given index. */
const okAt = (n) => [frame('start', { run_id: 'r' + n }), frame('delta', { text: 'ok' }),
                     frame('end', { user_index: n, assistant_index: n + 1 })];
const OK_AT_0 = okAt(0);

async function boot({ chats = [], forkOk = true, deleteStatus = 200 } = {}) {
  const calls = [];
  const bodies = [];
  let queue = [];
  const fetchStub = async (url, opts = {}) => {
    const path = String(url).replace(`http://127.0.0.1:${PORT}`, '');
    calls.push(`${opts.method || 'GET'} ${path}`);
    if (opts.body) { try { bodies.push(JSON.parse(opts.body)); } catch {} }
    const u = String(url);
    if (u.includes('/chat') && opts.method === 'POST' && !u.includes('/chats')) {
      const frames = queue.shift() || [];
      let i = 0;
      const enc = new TextEncoder();
      return { ok: true, status: 200,
        body: { getReader: () => ({ read: async () => (i < frames.length
          ? { done: false, value: enc.encode(frames[i++]) } : { done: true }) }) } };
    }
    if (u.includes('/version/')) return { ok: true, status: 200,
      json: async () => ({ ok: true, active: 0, count: 2, content: 'earlier answer' }) };
    if (u.includes('/messages/')) return { ok: deleteStatus === 200, status: deleteStatus,
                                           json: async () => ({ ok: deleteStatus === 200 }) };
    if (u.includes('/fork/')) return { ok: forkOk, status: forkOk ? 200 : 404,
                                       json: async () => ({ ok: forkOk, id: 'forked' }) };
    const body =
      u.includes('/settings') ? { model: 'm', theme: 'system', confirm_delete: false }
      : u.includes('/chats/') ? { id: 'c1', title: 'Hi', messages: chats }
      : u.includes('/chats')  ? { chats: [] }
      : u.includes('/update') ? { checked: false, update_available: false }
      : { ok: true };
    return { ok: true, status: 200, json: async () => body,
             body: { getReader: () => ({ read: async () => ({ done: true }) }) } };
  };
  const dom = new JSDOM(HTML, {
    runScripts: 'dangerously', resources: 'usable', url: ORIGIN + '/',
    beforeParse(w) {
      w.__TAURI__ = { core: { invoke: async () => ({ state: 'ready', port: PORT, python: '/py' }) } };
      w.fetch = fetchStub;
      w.requestAnimationFrame = (cb) => setTimeout(cb, 0);
      w.navigator.clipboard = { writeText: async () => {} };
      w.confirm = () => true; w.prompt = () => 'x'; w.alert = () => {}; w.scrollTo = () => {};
      w.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
      Object.defineProperty(w.HTMLElement.prototype, 'scrollIntoView', { value() {} });
    },
  });
  const { window } = dom;
  for (let i = 0; i < 80; i++) {
    await new Promise((r) => setTimeout(r, 25));
    if (window.document.getElementById('p') && !window.document.getElementById('p').disabled) break;
  }
  await new Promise((r) => setTimeout(r, 120));
  return { window, doc: window.document, calls, bodies,
           enqueue: (...turns) => { queue = turns; } };
}

const click = (el) =>
  el.dispatchEvent(new el.ownerDocument.defaultView.MouseEvent('click', { bubbles: true }));

async function send(b, text) {
  b.doc.getElementById('p').value = text;
  click(b.doc.getElementById('send'));
  await new Promise((r) => setTimeout(r, 250));
}

const actionOf = (turnEl, label) =>
  [...turnEl.querySelectorAll('.act')].find((x) => x.textContent === label);

test('a turn that never persisted offers no Fork or Delete', async () => {
  const b = await boot();
  b.enqueue(FAILED_TURN);
  await send(b, 'this one fails');
  const turn = [...b.doc.querySelectorAll('.turn.a')].pop();
  assert.equal(actionOf(turn, 'Delete'), undefined,
    'offered Delete for a turn that was never stored');
  assert.equal(actionOf(turn, 'Fork'), undefined);
  assert.ok(actionOf(turn, 'Copy'), 'Copy should still be offered');
});

test('after an unpersisted turn, Delete still targets the right message', async () => {
  // The regression. Turn 1 errors (not stored); turn 2 succeeds as message 0.
  // DOM position says "second turn" -> index 2. The engine says 0.
  const b = await boot();
  b.enqueue(FAILED_TURN, OK_AT_0);
  await send(b, 'this one fails');
  await send(b, 'this one works');
  const turn = [...b.doc.querySelectorAll('.turn.a')].pop();
  click(actionOf(turn, 'Delete'));
  await new Promise((r) => setTimeout(r, 80));
  // A new session generates its own chat id, so assert on the index only --
  // that is the number the bug got wrong.
  const del = b.calls.filter((c) => c.includes('/messages/')).pop();
  assert.equal(del.split('/').pop(), '0', `sent ${del}, which points at the wrong exchange`);
});

test('Fork uses the assistant index, one past the user message', async () => {
  const b = await boot();
  b.enqueue(FAILED_TURN, OK_AT_0);
  await send(b, 'fails');
  await send(b, 'works');
  const turn = [...b.doc.querySelectorAll('.turn.a')].pop();
  click(actionOf(turn, 'Fork'));
  await new Promise((r) => setTimeout(r, 80));
  const fork = b.calls.filter((c) => c.includes('/fork/')).pop();
  assert.equal(fork.split('/').pop(), '1', `sent ${fork}`);
});

test('a refused delete leaves the turn on screen and says so', async () => {
  const b = await boot({ deleteStatus: 404 });
  b.enqueue(OK_AT_0);
  await send(b, 'works');
  const before = b.doc.querySelectorAll('.turn').length;
  click(actionOf([...b.doc.querySelectorAll('.turn.a')].pop(), 'Delete'));
  await new Promise((r) => setTimeout(r, 80));
  assert.equal(b.doc.querySelectorAll('.turn').length, before + 1,
    'the turn was removed despite the engine refusing (only an error block should be added)');
  assert.ok(b.doc.querySelector('.err'), 'the failure was silent');
});

test('a refused fork is reported rather than swallowed', async () => {
  const b = await boot({ forkOk: false });
  b.enqueue(OK_AT_0);
  await send(b, 'works');
  click(actionOf([...b.doc.querySelectorAll('.turn.a')].pop(), 'Fork'));
  await new Promise((r) => setTimeout(r, 80));
  assert.ok(b.doc.querySelector('.err'), 'a failed fork produced no feedback at all');
});

test('history turns get their index from stored position', async () => {
  const b = await boot({ chats: [
    { role: 'user', content: 'one' }, { role: 'assistant', content: 'first' },
    { role: 'user', content: 'two' }, { role: 'assistant', content: 'second' },
  ] });
  b.doc.getElementById('newchat') && null;
  b.window.openChat?.('c1');
  await new Promise((r) => setTimeout(r, 200));
  const turns = [...b.doc.querySelectorAll('.turn.a')];
  assert.equal(turns.length, 2, 'history did not render');
  click(actionOf(turns[1], 'Delete'));
  await new Promise((r) => setTimeout(r, 80));
  const del = b.calls.filter((c) => c.includes('/messages/')).pop();
  assert.equal(del.split('/').pop(), '2', `sent ${del}`);
});

test('the index comes from the engine, not from counting turns', async () => {
  // Deliberately a case where the right answer is NOT zero: turn 1 stores at 0,
  // turn 2 fails and stores nothing, turn 3 stores at 2. DOM position would say
  // 4. An earlier version of this file only ever expected 0, so hardcoding
  // `userIndex = 0` passed it -- the mutation survived and the test proved
  // nothing.
  const b = await boot();
  b.enqueue(okAt(0), FAILED_TURN, okAt(2));
  await send(b, 'first');
  await send(b, 'fails');
  await send(b, 'third');
  const turn = [...b.doc.querySelectorAll('.turn.a')].pop();
  click(actionOf(turn, 'Delete'));
  await new Promise((r) => setTimeout(r, 80));
  const del = b.calls.filter((c) => c.includes('/messages/')).pop();
  assert.equal(del.split('/').pop(), '2', `sent ${del}; DOM position would have said 4`);
});

test('Fork on that same turn asks for the assistant message', async () => {
  const b = await boot();
  b.enqueue(okAt(0), FAILED_TURN, okAt(2));
  await send(b, 'first'); await send(b, 'fails'); await send(b, 'third');
  click(actionOf([...b.doc.querySelectorAll('.turn.a')].pop(), 'Fork'));
  await new Promise((r) => setTimeout(r, 80));
  const fork = b.calls.filter((c) => c.includes('/fork/')).pop();
  assert.equal(fork.split('/').pop(), '3', `sent ${fork}`);
});

// --- DOM clobbering via an unescaped quote in a link -------------------------

/** A turn whose answer is a markdown link with a quote that closes the href. */
const CLOBBER = [frame('start', { run_id: 'rc' }),
                 frame('delta', { text: '[x](https://ok.example"id="f)' }),
                 frame('end', { user_index: 0, assistant_index: 1 })];

test('a quote in a model link cannot clobber getElementById("f")', async () => {
  // esc() must escape " so the URL stays inside the href and never injects
  // id="f", which would make document.getElementById('f') return the <a> instead
  // of the composer <form> and break Enter-to-send.
  const b = await boot();
  b.enqueue(CLOBBER);
  await send(b, 'read me a page');
  const f = b.doc.getElementById('f');
  assert.equal(f.tagName, 'FORM', 'a rendered <a> clobbered the composer form');

  b.enqueue(OK_AT_0);
  b.doc.getElementById('p').value = 'still works?';
  b.doc.getElementById('p').dispatchEvent(
    new b.window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
  await new Promise((r) => setTimeout(r, 250));
  assert.ok(b.calls.some((c) => c === 'POST /chat'),
    'Enter-to-send threw because requestSubmit was not on a form');
});

// --- versions ----------------------------------------------------------------

/** A turn that persisted at 0 and reports `n` stored answers. */
const withVersions = (n, active) => [
  frame('start', { run_id: 'rv' }), frame('delta', { text: 'answer' }),
  frame('end', { user_index: 0, assistant_index: 1, versions: n, active }),
];

test('one answer shows no version picker', async () => {
  const b = await boot();
  b.enqueue(withVersions(1, 0));
  await send(b, 'once');
  assert.equal(b.doc.querySelector('.vnav'), null,
    'a picker appeared with nothing to pick between');
});

test('a regenerated answer shows the picker at the newest version', async () => {
  const b = await boot();
  b.enqueue(withVersions(2, 1));
  await send(b, 'again');
  const nav = b.doc.querySelector('.vnav');
  assert.ok(nav, 'no version picker');
  assert.equal(nav.querySelector('.vn').textContent, '2/2');
  const [prev, next] = nav.querySelectorAll('.vb');
  assert.equal(prev.disabled, false, 'cannot reach the earlier answer');
  assert.equal(next.disabled, true, 'offers a version past the last one');
});

test('stepping back asks the engine and repaints the answer', async () => {
  const b = await boot();
  b.enqueue(withVersions(2, 1));
  await send(b, 'again');
  click(b.doc.querySelector('.vnav .vb'));
  await new Promise((r) => setTimeout(r, 80));
  const call = b.calls.filter((c) => c.includes('/version/')).pop();
  assert.ok(call, 'the picker changed nothing on the engine');
  assert.equal(call.split('/').slice(-2).join('/'), '0/0',
    `asked for ${call}; expected message 0, version 0`);
  assert.equal(b.doc.querySelector('.vnav .vn').textContent, '1/2');
});

test('Regenerate names the turn it is replacing', async () => {
  // Without this the engine appends a second copy of the question instead of
  // filing the answer as another version of the first.
  const b = await boot();
  b.enqueue(withVersions(1, 0), withVersions(2, 1));
  await send(b, 'first');
  const turn = [...b.doc.querySelectorAll('.turn.a')].pop();
  click(actionOf(turn, 'Regenerate'));
  await new Promise((r) => setTimeout(r, 250));
  const body = b.bodies.filter((x) => x && 'prompt' in x).pop();
  assert.equal(body.regenerate_of, 0, `sent regenerate_of=${body.regenerate_of}`);
});

test('an ordinary send does not claim to be a regeneration', async () => {
  const b = await boot();
  b.enqueue(withVersions(1, 0), withVersions(1, 0));
  await send(b, 'first');
  click(actionOf([...b.doc.querySelectorAll('.turn.a')].pop(), 'Regenerate'));
  await new Promise((r) => setTimeout(r, 250));
  await send(b, 'a completely new question');
  const body = b.bodies.filter((x) => x && 'prompt' in x).pop();
  assert.equal(body.regenerate_of, null,
    'the regenerate flag leaked into the next turn and overwrote an answer');
});
