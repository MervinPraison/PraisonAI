/**
 * The page ships to macOS, Windows and Linux from one file.
 *
 * The webview is a different engine on each -- WKWebView, WebView2, WebKitGTK
 * -- so the page has to read the platform rather than assume one. Each test
 * boots the real page with a different user agent and asserts what changed,
 * because every one of these defects is silent: dead space where the traffic
 * lights are not, a keyboard hint naming a key the keyboard does not have, and
 * a "where your files are" path that does not exist on the machine reading it.
 */
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';
import assert from 'node:assert/strict';
import test from 'node:test';
import { createServer } from 'node:http';
import { extname } from 'node:path';

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

/** What each real webview reports: WKWebView, WebView2, WebKitGTK. */
const AGENTS = {
  mac: {
    platform: 'MacIntel',
    ua: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
  },
  win: {
    platform: 'Win32',
    ua: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36 Edg/120.0',
  },
  linux: {
    platform: 'Linux x86_64',
    ua: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
  },
};

async function boot(os, { engineState = 'ready' } = {}) {
  const copied = [];
  const dom = new JSDOM(HTML, {
    runScripts: 'dangerously', resources: 'usable', url: ORIGIN + '/',
    beforeParse(w) {
      // Defined on the navigator rather than passed as jsdom's `userAgent`
      // option: that option was silently ignored here, so every case ran
      // against jsdom's own "(darwin)" agent and all three tests were really
      // testing the same platform.
      for (const [key, value] of [['platform', AGENTS[os].platform],
                                  ['userAgent', AGENTS[os].ua]]) {
        Object.defineProperty(w.navigator, key, { value, configurable: true });
      }
      w.__TAURI__ = { core: { invoke: async () =>
        (engineState === 'ready'
          ? { state: 'ready', port: PORT, python: '/py' }
          : { state: 'failed', reason: 'No usable Python' }) } };
      w.fetch = async (url) => {
        const u = String(url);
        const body = u.includes('/settings')
          ? { model: 'gpt-4o-mini', theme: 'system', temperature: 0.7,
              approval_mode: 'ask', approval_timeout: 300 }
          : u.includes('/chats') ? { chats: [] }
          : u.includes('/update') ? { current: '0.1.0', checked: false, message: 'x' }
          : { ok: true, runs: [] };
        return { ok: true, status: 200, json: async () => body, text: async () => '' };
      };
      w.requestAnimationFrame = (cb) => setTimeout(cb, 0);
      w.navigator.clipboard = { writeText: async (t) => { copied.push(t); } };
      w.confirm = () => true; w.alert = () => {}; w.scrollTo = () => {};
      w.EventSource = class { addEventListener() {} close() {} };
      Object.defineProperty(w.HTMLElement.prototype, 'scrollIntoView', { value() {} });
      Object.defineProperty(w.HTMLCanvasElement.prototype, 'getContext', {
        value: () => ({ setTransform() {}, clearRect() {}, beginPath() {}, moveTo() {},
                        lineTo() {}, stroke() {}, arc() {}, fill() {} }),
      });
    },
  });
  const { window } = dom;
  for (let i = 0; i < 80; i++) {
    await new Promise((r) => setTimeout(r, 25));
    if (!window.document.getElementById('p').disabled) break;
  }
  return { window, doc: window.document, copied };
}

const settle = () => new Promise((r) => setTimeout(r, 120));

test('the page records which platform it is running on', async () => {
  for (const [os, expected] of [['mac', 'mac'], ['win', 'win'], ['linux', 'linux']]) {
    const { doc } = await boot(os);
    assert.equal(doc.documentElement.dataset.os, expected, `misread ${os}`);
  }
});

test('only macOS reserves room for the traffic lights', async () => {
  // 5.2rem of dead space on the left, on a platform whose window controls are
  // top-right -- and where they would then sit on top of the toolbar buttons.
  const mac = await boot('mac');
  const win = await boot('win');
  const pad = (d) => d.defaultView.getComputedStyle(d.querySelector('.titlebar')).paddingLeft;
  assert.notEqual(pad(win.doc), pad(mac.doc),
                  'Windows reserves the same gutter as macOS traffic lights');
});

test('the shortcut hints name a key the keyboard actually has', async () => {
  const mac = await boot('mac');
  await settle();
  assert.match(mac.doc.getElementById('newchat').textContent, /⌘/, 'macOS lost its ⌘');

  for (const os of ['win', 'linux']) {
    const { doc } = await boot(os);
    await settle();
    const hints = [...doc.querySelectorAll('.navbtn .k')].map((k) => k.textContent).join(' ');
    assert.ok(hints.length, `${os}: no shortcut hints rendered at all`);
    assert.ok(!hints.includes('⌘'), `${os} shows ⌘ for a key it does not have: ${hints}`);
    assert.match(hints, /Ctrl/, `${os}: ${hints}`);
  }
});

test('Ctrl works as the shortcut key everywhere', async () => {
  // The label changing is cosmetic; the handler must accept it too.
  for (const os of ['mac', 'win', 'linux']) {
    const { doc, window } = await boot(os);
    await settle();
    const before = doc.getElementById('turns').children.length;
    window.document.dispatchEvent(new window.KeyboardEvent('keydown',
      { key: 'n', ctrlKey: true, bubbles: true, cancelable: true }));
    await settle();
    assert.equal(doc.getElementById('turns').children.length, before, os);
  }
});

/** The text a person can actually see -- not the inline script's source.
 *
 *  The script tag lives inside <body>, so `body.textContent` includes every
 *  string literal in the page's own JavaScript. The first version of this
 *  test read that and "found" macOS copy on Windows, in the source of the
 *  very branch that avoids it. */
function visibleText(doc) {
  const clone = doc.body.cloneNode(true);
  clone.querySelectorAll('script, style, template').forEach((n) => n.remove());
  return clone.textContent;
}

test('the first-run copy names a folder that exists on the machine reading it', async () => {
  // The copy only appears on the setup screen, which only appears when the
  // engine is not ready -- booting "ready" and reading the page found nothing
  // and would have passed for any wording at all.
  const lede = {};
  for (const os of ['mac', 'win', 'linux']) {
    const { doc } = await boot(os, { engineState: 'failed' });
    await settle();
    const el = doc.querySelector('.setup .lede');
    assert.ok(el, `${os}: the setup screen never rendered`);
    lede[os] = el.textContent;
  }
  assert.match(lede.mac, /Library/, 'macOS should still say Library');
  assert.ok(!/Library/.test(lede.win), `Windows told to look in a Library folder: ${lede.win}`);
  assert.ok(!/Library/.test(lede.linux), `Linux told to look in a Library folder: ${lede.linux}`);
  for (const os of ['mac', 'win', 'linux']) {
    assert.match(lede[os], /once/, `${os} no longer says this is one-time`);
  }
});

test('copying the data folder copies this platform\'s path', async () => {
  // %APPDATA% rather than an expanded path on Windows: it is what a person
  // can paste straight into Explorer or Run, which is the point of offering
  // to copy it at all.
  const expectations = {
    mac: /Library\/Application Support/,
    win: /%APPDATA%/i,
    linux: /\.local\/share/,
  };
  for (const [os, pattern] of Object.entries(expectations)) {
    const { doc, copied, window } = await boot(os);
    await settle();
    const fn = window.dataFolderPath;
    assert.equal(typeof fn, 'function', 'the page cannot name its own data folder');
    assert.match(fn(), pattern, `${os} copies the wrong path: ${fn()}`);
    if (os !== 'mac') {
      assert.ok(!/Library/.test(fn()), `${os} copies a macOS path: ${fn()}`);
    }
  }
});
