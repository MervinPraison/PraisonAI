/**
 * What a machine with no Python sees.
 *
 * A shipped `.app` finds its bundled engine and then finds no interpreter to
 * run it with. That used to render "No usable Python" as a red error block --
 * true, and useless to someone who has never installed Python. It now offers
 * to build the environment and shows what it is doing, because the whole run
 * takes minutes and silence is indistinguishable from a hang.
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

/**
 * Boot with no interpreter. `provision` decides what the setup run does:
 * `'ok'` succeeds and the engine comes up, `'fail'` rejects.
 */
async function boot({ provision = 'ok', steps = [], savedView = null,
                      engineStatusDelay = 0 } = {}) {
  const invoked = [];
  let listener = null;
  let readyAfterProvision = provision === 'ok';
  const dom = new JSDOM(HTML, {
    runScripts: 'dangerously', resources: 'usable', url: ORIGIN + '/',
    beforeParse(w) {
      // Model a machine where the user last used the Train tab: the app
      // restores that view synchronously, before the async engine check runs.
      if (savedView) try { w.localStorage.setItem('view', savedView); } catch {}
      w.__TAURI__ = {
        core: {
          invoke: async (cmd) => {
            invoked.push(cmd);
            if (cmd === 'engine_status') {
              if (engineStatusDelay) {
                await new Promise((resolve) => setTimeout(resolve, engineStatusDelay));
              }
              return invoked.filter((c) => c === 'provision_engine').length && readyAfterProvision
                ? { state: 'ready', port: 65000, python: '/venv/bin/python3' }
                : { state: 'failed', reason: 'No usable Python',
                    detail: 'Tried: /nowhere/bin/python3', tail: '' };
            }
            if (cmd === 'provision_engine') {
              for (const s of steps) listener?.({ payload: s });
              if (provision === 'fail') throw new Error('Installing Python failed. no network');
              // 'hang' models a run still in progress, which is the only state
              // in which the step list is on screen to be read.
              if (provision === 'hang') await new Promise(() => {});
              return '/venv/bin/python3';
            }
            return null;
          },
        },
        event: { listen: async (_name, cb) => { listener = cb; return () => { listener = null; }; } },
      };
      w.fetch = async () => ({ ok: true, status: 200,
        json: async () => ({ chats: [], model: 'm', theme: 'system' }), text: async () => '' });
      w.requestAnimationFrame = (cb) => setTimeout(cb, 0);
      w.navigator.clipboard = { writeText: async () => {} };
      w.confirm = () => true; w.alert = () => {}; w.scrollTo = () => {};
      w.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
      Object.defineProperty(w.HTMLElement.prototype, 'scrollIntoView', { value() {} });
    },
  });
  const { window } = dom;
  await new Promise((r) => setTimeout(r, 400));
  return { window, doc: window.document, invoked };
}

const click = (el) =>
  el.dispatchEvent(new el.ownerDocument.defaultView.MouseEvent('click', { bubbles: true }));

test('no Python offers setup instead of an error block', async () => {
  const b = await boot();
  assert.ok(b.doc.querySelector('.setup'), 'no setup screen');
  assert.equal(b.doc.querySelector('.err'), null,
    'still shown as a failure the user cannot act on');
  assert.match(b.doc.getElementById('status').textContent, /setup/i);
});

test('a saved or clicked Train view cannot hide first-run setup', async () => {
  const b = await boot({ savedView: 'train' });
  assert.equal(b.doc.body.classList.contains('training'), false,
    'the saved Train view hid the setup screen');
  assert.ok(b.doc.querySelector('.setup'), 'no setup screen after restoring Train');
  assert.equal(b.window.localStorage.getItem('view'), 'train',
    'forcing Chat during setup overwrote the saved Train preference');

  click(b.doc.getElementById('viewTrain'));
  assert.equal(b.doc.body.classList.contains('training'), false,
    'Train can replace setup even though it has no engine');
  assert.ok(b.doc.querySelector('.setup'), 'clicking Train hid the setup screen');
  assert.equal(b.window.localStorage.getItem('view'), 'train',
    'clicking Train during setup discarded the requested view');
});

test('Train stays blocked while initial engine status is still pending', async () => {
  const b = await boot({ engineStatusDelay: 1000 });
  click(b.doc.getElementById('viewTrain'));
  assert.equal(b.doc.body.classList.contains('training'), false,
    'Train replaced setup before engine readiness was known');
  assert.equal(b.window.localStorage.getItem('view'), 'train',
    'clicking Train while readiness was pending discarded the requested view');
  await new Promise((resolve) => setTimeout(resolve, 700));
  assert.equal(b.doc.body.classList.contains('training'), false,
    'the stale startup view replaced setup after readiness resolved');
  assert.equal(b.window.localStorage.getItem('view'), 'train',
    'startup completion overwrote the view selected while readiness was pending');
  assert.ok(b.doc.querySelector('.setup'),
    'startup completion hid setup after a Train click during readiness detection');
});

test('the steps are listed before anything starts', async () => {
  // Listing them up front is what makes a three-minute run legible.
  const b = await boot();
  const labels = [...b.doc.querySelectorAll('.setup .steps li .lb')].map((n) => n.textContent);
  assert.deepEqual(labels,
    ['Fetching the installer', 'Installing Python', 'Creating the environment',
     'Installing PraisonAI']);
});

test('the copy explains where things go, without jargon', async () => {
  const b = await boot();
  const lede = b.doc.querySelector('.setup .lede').textContent;
  // Not /Library/: this suite runs on whatever CI the release uses, and the
  // copy is now per-platform. Pinning the macOS wording made a Linux runner
  // fail on correct behaviour -- and would have made anyone fixing the copy
  // "break CI" for doing the right thing. Assert that it names *a* place.
  assert.match(lede, /Library folder|app data folder|home directory/,
               `does not say where it installs: ${lede}`);
  assert.match(lede, /once/, 'does not say this is one-time');
  for (const jargon of ['venv', 'uv ', 'PATH']) {
    assert.equal(lede.includes(jargon), false, `jargon in first-run copy: ${jargon}`);
  }
});

test('progress events mark each step as it happens', async () => {
  const b = await boot({ provision: 'hang', steps: [
    { id: 'python', label: 'Installing Python', state: 'running' },
    { id: 'python', label: 'Installing Python', state: 'done' },
    { id: 'venv', label: 'Creating the environment', state: 'running' },
  ] });
  click(b.doc.querySelector('.setup .go'));
  await new Promise((r) => setTimeout(r, 200));
  const li = [...b.doc.querySelectorAll('.setup .steps li')];
  assert.equal(li[1].className, 'done', 'a finished step is not marked done');
  assert.equal(li[2].className, 'running', 'the current step is not marked running');
  assert.equal(li[3].className, '', 'a step that has not started is marked');
  assert.equal(b.doc.querySelector('.setup .go').disabled, true,
    'setup can be started twice');
});

test('a successful setup starts the engine and clears the screen', async () => {
  const b = await boot({ provision: 'ok' });
  click(b.doc.querySelector('.setup .go'));
  await new Promise((r) => setTimeout(r, 400));
  assert.ok(b.invoked.includes('provision_engine'), 'setup never ran');
  assert.equal(b.doc.querySelector('.setup'), null, 'the setup screen stayed up');
  assert.equal(b.doc.getElementById('p').disabled, false, 'the composer is still disabled');
});

test('a failed setup says why and offers another go', async () => {
  const b = await boot({ provision: 'fail', steps: [
    { id: 'python', label: 'Installing Python', state: 'failed', detail: 'no network' },
  ] });
  click(b.doc.querySelector('.setup .go'));
  await new Promise((r) => setTimeout(r, 300));
  const go = b.doc.querySelector('.setup .go');
  assert.equal(go.disabled, false, 'the button is stuck disabled after a failure');
  assert.equal(go.textContent, 'Try again');
  assert.match(b.doc.querySelector('.setup .why').textContent, /no network/,
    'the reason was swallowed');
  assert.ok(b.doc.querySelector('.setup li.failed'), 'the failing step is not marked');
});

// A restored Train view hides #thread, where the setup wizard renders. Left
// alone, that buries setup: the title bar says "setup needed" and nothing is on
// screen to act on -- the reported Windows dead end. The engine gate must win
// over the restored view while the engine is not ready.
test('a restored Train view does not hide the setup screen', async () => {
  const b = await boot({ savedView: 'train' });
  assert.ok(b.doc.querySelector('.setup'), 'no setup screen');
  assert.equal(b.doc.body.classList.contains('training'), false,
    'the Train view is still up, hiding the setup wizard');
});

// The forced switch must not clobber the deliberate choice: once the engine is
// up, the user's Train tab should return, so we must not have persisted 'chat'.
test('the forced Chat switch does not overwrite the saved Train choice', async () => {
  const b = await boot({ savedView: 'train' });
  assert.equal(b.window.localStorage.getItem('view'), 'train',
    'the saved view was overwritten by the engine gate');
});
