/**
 * Eleven settings were stored, persisted, and read by nothing. They rendered a
 * control, accepted a value, wrote it to settings.json, and changed no
 * behaviour whatsoever -- the purest form of a failure that looks like success.
 *
 * Every test here boots the real page with a *specific* config and asserts an
 * observable difference. Each setting is swept across at least two values, so
 * "it didn't change" cannot be mistaken for "it works": a test that only ever
 * saw the default would pass against the dead code it was written to catch.
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

/** Boot the page with `cfg` as what GET /settings returns. */
/** A ReadableStream reader that plays back canned SSE frames, then ends. */
function sseReader(frames) {
  const enc = new TextEncoder();
  let i = 0;
  return { read: async () => (i < frames.length
    ? { done: false, value: enc.encode(frames[i++]) }
    : { done: true, value: undefined }) };
}

async function boot(cfg = {}, { confirmAnswer = true, sse = [], prefersReducedMotion = false,
                                failSettingsWrite = false } = {}) {
  const calls = [];
  const bodies = [];
  const settings = {
    model: 'gpt-4o-mini', theme: 'system', temperature: 0.7,
    approval_mode: 'ask', approval_timeout: 300, ...cfg,
  };
  const fetchStub = async (url, opts = {}) => {
    const path = String(url).replace(`http://127.0.0.1:${PORT}`, '');
    calls.push(`${opts.method || 'GET'} ${path}`);
    if (opts.body) { try { bodies.push(JSON.parse(opts.body)); } catch {} }
    const u = String(url);
    // Simulate the engine rejecting a settings write -- the very case the UI
    // itself warns about across a base_url/api_key change that restarts it.
    if (failSettingsWrite && (opts.method || 'GET') === 'POST' && u.includes('/settings')) {
      return { ok: false, status: 500, json: async () => ({}), text: async () => '' };
    }
    // The real engine persists the write and echoes the stored settings back;
    // reconciliation reads that echo, so the stub must reflect what it was sent.
    if ((opts.method || 'GET') === 'POST' && u.includes('/settings') && opts.body) {
      try { Object.assign(settings, JSON.parse(opts.body)); } catch {}
    }
    const body =
      u.includes('/settings') ? settings
      : u.includes('/chats/') ? { id: 'c1', title: 'Hi', messages: [] }
      : u.includes('/chats')  ? { chats: [{ id: 'c1', title: 'Hi', updated: 1, count: 2, project: '' }] }
      : u.includes('/update') ? { current: '1.0.0', latest: '2.0.0', checked: true,
                                  update_available: true, message: 'newer' }
      : { ok: true };
    return { ok: true, status: 200, json: async () => body, text: async () => '',
             body: { getReader: () => sseReader(sse) } };
  };
  let confirms = 0;
  const dom = new JSDOM(HTML, {
    runScripts: 'dangerously', resources: 'usable', url: ORIGIN + '/',
    beforeParse(w) {
      w.__TAURI__ = { core: { invoke: async () => ({ state: 'ready', port: PORT, python: '/py' }) } };
      w.fetch = fetchStub;
      w.requestAnimationFrame = (cb) => setTimeout(cb, 0);
      w.navigator.clipboard = { writeText: async () => {} };
      // window.confirm is never called any more -- counting it would count
      // nothing. Left in place so an accidental regression to the native
      // dialog shows up as a confirm with no visible dialog.
      w.confirm = () => { confirms += 1; return confirmAnswer; };
      w.prompt = () => 'x';
      w.alert = () => {};
      w.scrollTo = () => {};
      w.matchMedia = (q) => ({
        matches: q.includes('prefers-reduced-motion') ? prefersReducedMotion : false,
        addEventListener() {}, removeEventListener() {},
      });
      Object.defineProperty(w.HTMLElement.prototype, 'scrollIntoView', { value() {} });
    },
  });
  const { window } = dom;
  for (let i = 0; i < 80; i++) {
    await new Promise((r) => setTimeout(r, 25));
    if (window.document.getElementById('p') && !window.document.getElementById('p').disabled) break;
  }
  await new Promise((r) => setTimeout(r, 120));
  return { window, doc: window.document, calls, bodies, confirms: () => confirms };
}

const click = (el) =>
  el.dispatchEvent(new el.ownerDocument.defaultView.MouseEvent('click', { bubbles: true }));

// --- appearance --------------------------------------------------------------

test('font_size changes the variable the message text is sized from', async () => {
  const small = await boot({ font_size: 12 });
  const large = await boot({ font_size: 20 });
  assert.equal(small.doc.documentElement.style.getPropertyValue('--fs'), '12px');
  assert.equal(large.doc.documentElement.style.getPropertyValue('--fs'), '20px');
});

test('rapid text-size steps accumulate instead of collapsing to one', async () => {
  // saveCfg only updates CFG once the write resolves. Two quick zoom-in presses
  // fired back-to-back would otherwise both read the same starting size and
  // land on the same next value; the pending-target bookkeeping must let them
  // walk 13 -> 14 -> 15 across the two writes.
  const b = await boot({ font_size: 13 });
  const zoom = () => b.doc.dispatchEvent(new b.window.KeyboardEvent('keydown',
    { key: '=', metaKey: true, bubbles: true, cancelable: true }));
  zoom();
  zoom();
  await new Promise((r) => setTimeout(r, 120));
  assert.equal(b.doc.documentElement.style.getPropertyValue('--fs'), '15px',
    'two quick steps collapsed to a single step');
  const sent = b.bodies.filter((x) => x && 'font_size' in x).map((x) => x.font_size);
  assert.deepEqual(sent, [14, 15], `expected 14 then 15 to be persisted, got ${sent}`);
});

test('code_font_size is its own setting, and scales with the interface', async () => {
  // It used to be an absolute px value, so at text size 18 the prose grew and
  // code blocks stayed put. It is now multiplied by the same scale -- which
  // means the raw number is no longer what lands in --fs-code.
  const big = await boot({ font_size: 20, code_font_size: 11 });
  assert.equal(big.doc.documentElement.style.getPropertyValue('--fs'), '20px');
  const scaled = parseFloat(big.doc.documentElement.style.getPropertyValue('--fs-code'));
  assert.ok(Math.abs(scaled - 11 * (20 / 15)) < 0.05,
    `--fs-code is ${scaled}; expected 11 scaled by 20/15`);

  // At the default scale it is exactly the setting.
  const base = await boot({ font_size: 15, code_font_size: 11 });
  assert.equal(base.doc.documentElement.style.getPropertyValue('--fs-code'), '11.00px');

  // And it is still independent: same text size, different code size.
  const other = await boot({ font_size: 15, code_font_size: 16 });
  assert.equal(other.doc.documentElement.style.getPropertyValue('--fs-code'), '16.00px');
});

test('reduce_motion uses the values the registry actually produces', async () => {
  // The first version of this test fed `true`/`false`. The control is
  // segmented -- "system" | "on" | "off" -- so neither value can ever reach
  // the page, and the test passed against a setting that was inert for every
  // real user. Read the options out of the registry so it cannot drift again.
  const { window } = await boot();
  const def = window.__REGISTRY__.SETTINGS.find((d) => d.key === 'reduce_motion');
  // Joined, not deepEqual: the array comes from the jsdom realm, so its
  // prototype differs and deepEqual compares unequal despite equal contents.
  const values = def.control.options.map((o) => o.value).join(',');
  assert.equal(values, 'system,on,off', 'registry options changed');

  const on = await boot({ reduce_motion: 'on' });
  const off = await boot({ reduce_motion: 'off' });
  assert.equal(on.doc.documentElement.classList.contains('no-motion'), true,
    '"on" did not reduce motion');
  assert.equal(off.doc.documentElement.classList.contains('no-motion'), false,
    '"off" reduced motion anyway');
});

test('reduce_motion="system" follows the OS preference', async () => {
  const quiet = await boot({ reduce_motion: 'system' }, { prefersReducedMotion: true });
  const normal = await boot({ reduce_motion: 'system' }, { prefersReducedMotion: false });
  assert.equal(quiet.doc.documentElement.classList.contains('no-motion'), true);
  assert.equal(normal.doc.documentElement.classList.contains('no-motion'), false);
});

test('the saved theme is applied at launch, not just when changed', async () => {
  // The CSS was verified; applying it was not. The startup fetch ran at
  // module-eval time with PORT still null and failed into an empty catch, so a
  // saved Light theme came back dark on every relaunch.
  const light = await boot({ theme: 'light' });
  const dark = await boot({ theme: 'dark' });
  assert.equal(light.doc.documentElement.getAttribute('data-theme'), 'light');
  assert.equal(dark.doc.documentElement.getAttribute('data-theme'), 'dark');
});

test('theme "system" leaves the attribute off so the OS decides', async () => {
  const b = await boot({ theme: 'system' });
  assert.equal(b.doc.documentElement.getAttribute('data-theme'), null);
});

// --- a settings write the engine rejects ------------------------------------

/** Open Settings and switch to the named section, waiting for it to render. */
async function openSettings(b, section) {
  click(b.doc.getElementById('settings'));
  for (let i = 0; i < 40; i++) {
    await new Promise((r) => setTimeout(r, 25));
    if (b.doc.getElementById('setbody')) break;
  }
  assert.ok(b.doc.querySelector('#setbody .srow'), 'settings never opened');
  const nav = [...b.doc.querySelectorAll('#setside button')]
    .find((x) => x.textContent.includes(section));
  assert.ok(nav, `the ${section} section is missing`);
  click(nav);
  await new Promise((r) => setTimeout(r, 40));
}

test('a rejected theme write applies nothing and tells the user', async () => {
  // saveCfg used to mutate first and never check r.ok, so a 500 left the button
  // un-highlighted, no data-theme, and no error -- a completely dead button.
  const b = await boot({ theme: 'system' }, { failSettingsWrite: true });
  await openSettings(b, 'Appearance');
  const light = [...b.doc.querySelectorAll('#setting-theme .seg button')]
    .find((x) => x.textContent === 'Light');
  assert.ok(light, 'the Light option is missing');
  click(light);
  await new Promise((r) => setTimeout(r, 80));
  assert.equal(b.doc.documentElement.getAttribute('data-theme'), null,
    'a failed write still applied the theme');
  const t = b.doc.getElementById('toast');
  assert.ok(t && t.classList.contains('show'), 'no error was surfaced');
});

test('a rejected toggle write leaves the switch where it was', async () => {
  // The toggle mutated cfg before the write, so a rejection left the switch and
  // the stored value disagreeing and the next click flipped the wrong one back.
  // The observable contract: a failed write must not move the switch, and the
  // engine must never see a value the user did not manage to persist.
  const b = await boot({ confirm_delete: true }, { failSettingsWrite: true });
  await openSettings(b, 'Safety');
  const sw = b.doc.querySelector('#setting-confirm_delete .sw');
  assert.ok(sw, 'the confirm_delete toggle is missing');
  assert.equal(sw.classList.contains('on'), true, 'toggle did not start on');
  b.bodies.length = 0;
  click(sw);
  await new Promise((r) => setTimeout(r, 80));
  const now = b.doc.querySelector('#setting-confirm_delete .sw');
  assert.equal(now.classList.contains('on'), true,
    'a failed write moved the switch to a state that was never persisted');
  assert.equal(b.bodies.some((x) => x && 'confirm_delete' in x && x.confirm_delete === false),
    true, 'the attempted write should still have been sent');
});

// --- safety ------------------------------------------------------------------

/** Answer the in-app confirmation, and fail loudly if none appeared. */
async function answerConfirm(b, accept) {
  await new Promise((r) => setTimeout(r, 60));
  const box = b.doc.querySelector('.confirm-back');
  assert.ok(box, 'no confirmation dialog appeared');
  click(box.querySelector(accept ? '.ok' : '.cx'));
  await new Promise((r) => setTimeout(r, 60));
}

test('confirm_delete=true asks before deleting a chat', async () => {
  const b = await boot({ confirm_delete: true });
  click(b.doc.querySelector('#chats .chat .x'));
  await new Promise((r) => setTimeout(r, 60));
  assert.ok(b.doc.querySelector('.confirm-back'), 'deleted without asking');
  assert.equal(b.calls.some((c) => c.startsWith('DELETE /chats/')), false,
    'deleted before the user answered');
  await answerConfirm(b, true);
  assert.ok(b.calls.some((c) => c.startsWith('DELETE /chats/')), 'confirmed but never deleted');
  assert.equal(b.confirms(), 0, 'fell back to the native dialog, which never shows');
});

test('confirm_delete=false deletes straight away', async () => {
  const b = await boot({ confirm_delete: false });
  click(b.doc.querySelector('#chats .chat .x'));
  await new Promise((r) => setTimeout(r, 60));
  assert.equal(b.doc.querySelector('.confirm-back'), null, 'asked despite the setting being off');
  assert.ok(b.calls.some((c) => c.startsWith('DELETE /chats/')), 'nothing was deleted');
});

test('declining the confirmation does not delete', async () => {
  const b = await boot({ confirm_delete: true });
  click(b.doc.querySelector('#chats .chat .x'));
  await answerConfirm(b, false);
  assert.equal(b.calls.some((c) => c.startsWith('DELETE /chats/')), false,
    'declined, and it deleted anyway');
  assert.equal(b.doc.querySelector('.confirm-back'), null, 'the dialog stayed on screen');
});

test('the whole sidebar row opens the chat, not just its title', async () => {
  // The handler used to sit on `.t` -- 59.7px of a 231px row -- so most of the
  // row, including the metadata line added beneath the title, did nothing.
  const b = await boot();
  const meta = b.doc.querySelector('#chats .chat .meta');
  assert.ok(meta, 'the row has no metadata line');
  click(meta);
  await new Promise((r) => setTimeout(r, 80));
  assert.ok(b.calls.some((c) => c.startsWith('GET /chats/c1')),
    'clicking the metadata line opened nothing');
});

test('the row opens from the keyboard', async () => {
  const b = await boot();
  const row = b.doc.querySelector('#chats .chat');
  assert.equal(row.getAttribute('role'), 'button');
  assert.equal(row.tabIndex, 0);
  row.dispatchEvent(new b.window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
  await new Promise((r) => setTimeout(r, 80));
  assert.ok(b.calls.some((c) => c.startsWith('GET /chats/c1')), 'Enter did nothing');
});

// --- general -----------------------------------------------------------------

test('check_updates=true asks the engine and surfaces the result', async () => {
  const b = await boot({ check_updates: true });
  assert.ok(b.calls.includes('GET /update'), 'no update check was made');
  assert.ok(b.doc.querySelector('.updbar'), 'an available update was never shown');
});

test('check_updates=false makes no update request at all', async () => {
  const b = await boot({ check_updates: false });
  assert.equal(b.calls.includes('GET /update'), false, 'checked despite being off');
  assert.equal(b.doc.querySelector('.updbar'), null);
});

// --- chat --------------------------------------------------------------------

test('condense_paste turns an oversized paste into an attachment', async () => {
  const b = await boot({ condense_paste: 100 });
  const box = b.doc.getElementById('p');
  const ev = new b.window.Event('paste', { bubbles: true, cancelable: true });
  ev.clipboardData = { getData: () => 'y'.repeat(500) };
  box.dispatchEvent(ev);
  await new Promise((r) => setTimeout(r, 40));
  assert.equal(ev.defaultPrevented, true, 'the paste still went into the composer');
  assert.ok(b.doc.querySelector('#chips .chip'), 'no attachment chip was created');
});

test('a paste under the limit is left alone', async () => {
  const b = await boot({ condense_paste: 100 });
  const ev = new b.window.Event('paste', { bubbles: true, cancelable: true });
  ev.clipboardData = { getData: () => 'y'.repeat(50) };
  b.doc.getElementById('p').dispatchEvent(ev);
  await new Promise((r) => setTimeout(r, 40));
  assert.equal(ev.defaultPrevented, false, 'a short paste was hijacked');
  assert.equal(b.doc.querySelector('#chips .chip'), null);
});

test('condense_paste=0 disables condensing entirely', async () => {
  const b = await boot({ condense_paste: 0 });
  const ev = new b.window.Event('paste', { bubbles: true, cancelable: true });
  ev.clipboardData = { getData: () => 'y'.repeat(9000) };
  b.doc.getElementById('p').dispatchEvent(ev);
  await new Promise((r) => setTimeout(r, 40));
  assert.equal(ev.defaultPrevented, false, 'condensed while switched off');
});

// --- tools -------------------------------------------------------------------

test('the Tools button state is sent to the engine, not just styled', async () => {
  const b = await boot();
  const btn = b.doc.getElementById('toolsBtn');
  b.doc.getElementById('p').value = 'hello';
  click(b.doc.getElementById('send'));
  await new Promise((r) => setTimeout(r, 80));
  const on = b.bodies.find((x) => x && 'prompt' in x);
  assert.equal(on.tools, true, 'tools state absent from the request');

  click(btn);
  b.doc.getElementById('p').value = 'again';
  click(b.doc.getElementById('send'));
  await new Promise((r) => setTimeout(r, 80));
  const off = b.bodies.filter((x) => x && 'prompt' in x).pop();
  assert.equal(off.tools, false, 'turning tools off changed nothing the engine sees');
});

// --- reasoning ---------------------------------------------------------------

const REASONING = [
  'event: start\ndata: {"run_id":"r1"}\n\n',
  'event: reasoning\ndata: {"text":"weighing it up"}\n\n',
  'event: delta\ndata: {"text":"done"}\n\n',
  'event: end\ndata: {}\n\n',
];

async function streamOnce(cfg) {
  const b = await boot(cfg, { sse: REASONING });
  b.doc.getElementById('p').value = 'think about it';
  click(b.doc.getElementById('send'));
  await new Promise((r) => setTimeout(r, 200));
  return b.doc.querySelector('.think');
}

test('collapse_reasoning=false leaves the reasoning block open', async () => {
  const el = await streamOnce({ collapse_reasoning: false });
  assert.ok(el, 'no reasoning block was rendered at all');
  assert.equal(el.classList.contains('open'), true, 'reasoning arrived collapsed');
});

test('collapse_reasoning=true starts it collapsed', async () => {
  const el = await streamOnce({ collapse_reasoning: true });
  assert.ok(el, 'no reasoning block was rendered at all');
  assert.equal(el.classList.contains('open'), false, 'the setting did nothing');
});
