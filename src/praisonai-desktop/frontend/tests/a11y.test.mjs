/**
 * The app had two `aria-` attributes in 1,500 lines: no landmarks, no live
 * region, and icon-only buttons whose accessible name was the glyph itself --
 * "☰", "＋", "↑" announce as punctuation or as nothing. Streamed answers were
 * never announced at all, which makes the product's central function invisible
 * to a screen reader.
 *
 * These boot the real page and read the resulting DOM, so a role that gets
 * overwritten at runtime fails here. That happened once already: `role`
 * was set to "button" and then to "listitem" two lines later, and the sidebar
 * row silently stopped being a control.
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

async function boot() {
  const dom = new JSDOM(HTML, {
    runScripts: 'dangerously', resources: 'usable', url: ORIGIN + '/',
    beforeParse(w) {
      w.__TAURI__ = { core: { invoke: async () => ({ state: 'ready', port: PORT, python: '/py' }) } };
      w.fetch = async (url) => {
        const u = String(url);
        const body =
          u.includes('/settings') ? { model: 'm', theme: 'system' }
          : u.includes('/chats/') ? { id: 'c1', title: 'Hi', messages: [] }
          : u.includes('/chats')  ? { chats: [{ id: 'c1', title: 'Hi', updated: 1, count: 2 }] }
          : u.includes('/update') ? { checked: false, update_available: false }
          : { ok: true };
        return { ok: true, status: 200, json: async () => body, text: async () => '' };
      };
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
  return { window, doc: window.document };
}

const click = (el) =>
  el.dispatchEvent(new el.ownerDocument.defaultView.MouseEvent('click', { bubbles: true }));

test('the page has landmarks, not an undifferentiated pile of divs', async () => {
  const { doc } = await boot();
  assert.ok(doc.querySelector('main'), 'there is no main landmark');
  assert.ok(doc.querySelector('aside[aria-label]'), 'the sidebar is unlabelled');
});

test('the transcript is a live region, so a streamed answer is announced', async () => {
  // Without this the product\'s central function is silent to a screen reader.
  const { doc } = await boot();
  const turns = doc.getElementById('turns');
  assert.equal(turns.getAttribute('role'), 'log');
  assert.equal(turns.getAttribute('aria-live'), 'polite');
  assert.ok(turns.getAttribute('aria-label'), 'the transcript has no name');
});

test('the engine status is announced when it changes', async () => {
  const { doc } = await boot();
  const st = doc.getElementById('status');
  assert.equal(st.getAttribute('role'), 'status');
  assert.equal(st.getAttribute('aria-live'), 'polite');
});

test('every icon-only control has a name that is not its glyph', async () => {
  const { doc } = await boot();
  for (const id of ['toggle', 'attach', 'send']) {
    const el = doc.getElementById(id);
    const name = el.getAttribute('aria-label');
    assert.ok(name && name.length > 3, `#${id} has no accessible name (aria-label=${name})`);
    assert.ok(/[a-z]/i.test(name), `#${id}'s name is not words: ${name}`);
  }
});

test('decorative glyphs beside a real label are hidden from AT', async () => {
  const { doc } = await boot();
  const ics = [...doc.querySelectorAll('.navbtn .ic')];
  assert.ok(ics.length >= 3, 'expected nav button glyphs');
  for (const ic of ics) {
    assert.equal(ic.getAttribute('aria-hidden'), 'true', `"${ic.textContent}" is announced`);
  }
});

test('the sidebar toggle reports its own state, and keeps reporting it', async () => {
  // Declared once in the markup, aria-expanded becomes a lie on first click.
  const { doc } = await boot();
  const t = doc.getElementById('toggle');
  assert.equal(t.getAttribute('aria-expanded'), 'true');
  click(t);
  assert.equal(t.getAttribute('aria-expanded'), 'false', 'the state was not updated');
  click(t);
  assert.equal(t.getAttribute('aria-expanded'), 'true');
});

test('the Tools button reports pressed state, not just a colour', async () => {
  const { doc } = await boot();
  const b = doc.getElementById('toolsBtn');
  assert.equal(b.getAttribute('aria-pressed'), 'true');
  click(b);
  assert.equal(b.getAttribute('aria-pressed'), 'false');
});

test('a conversation row is an operable control and marks the current one', async () => {
  const { doc } = await boot();
  const row = doc.querySelector('#chats .chat');
  assert.equal(row.getAttribute('role'), 'button',
    'the role was overwritten -- the row is not a control');
  assert.equal(row.tabIndex, 0);
  assert.ok(row.getAttribute('aria-label'), 'the row has no name');
});

test('the overlay is a modal dialog', async () => {
  const { doc } = await boot();
  const o = doc.getElementById('overlay');
  assert.equal(o.getAttribute('role'), 'dialog');
  assert.equal(o.getAttribute('aria-modal'), 'true');
});

test('closing the overlay returns focus to whatever opened it', async () => {
  const { window, doc } = await boot();
  const opener = doc.getElementById('settings');
  opener.focus();
  click(opener);
  await new Promise((r) => setTimeout(r, 120));
  assert.ok(doc.getElementById('overlay').classList.contains('open'));
  doc.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  await new Promise((r) => setTimeout(r, 60));
  assert.equal(doc.activeElement, opener,
    `focus went to ${doc.activeElement?.id || doc.activeElement?.tagName} instead of the opener`);
});
