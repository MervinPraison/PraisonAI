/**
 * The Training view, driven through the real page.
 *
 * Nothing here asserts that a handler exists; every test presses something and
 * checks what changed, or drives a server event and checks what rendered. The
 * contract with the engine -- especially the shape of `dataset`, which the
 * trainer reads as a list of sources and not a string -- is asserted on the
 * body actually sent, because a mismatch there fails an hour into a run.
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

/** A fake EventSource the test drives, since jsdom ships none. */
function installEventSource(w, streams) {
  w.EventSource = class {
    constructor(url) {
      this.url = url;
      this.listeners = {};
      this.closed = false;
      streams.push(this);
    }
    addEventListener(kind, fn) { (this.listeners[kind] ||= []).push(fn); }
    close() { this.closed = true; }
    /** Deliver a server event exactly as the engine would frame it. */
    emit(kind, data) {
      (this.listeners[kind] || []).forEach((fn) => fn({ data: JSON.stringify(data) }));
    }
  };
}

async function boot({ status = { run: null, metrics: [] }, start, runs = { runs: [] } } = {}) {
  const calls = [];
  const streams = [];
  const dom = new JSDOM(HTML, {
    runScripts: 'dangerously', resources: 'usable', url: ORIGIN + '/',
    beforeParse(w) {
      w.__TAURI__ = { core: { invoke: async () => ({ state: 'ready', port: PORT, python: '/py' }) } };
      installEventSource(w, streams);
      w.fetch = async (url, opts = {}) => {
        const path = String(url).replace(`http://127.0.0.1:${PORT}`, '');
        calls.push({ method: opts.method || 'GET', path, body: opts.body ? JSON.parse(opts.body) : null });
        const u = String(url);
        if (u.includes('/train/start')) {
          const reply = start || { ok: true, run: { id: 'run-1', state: 'pending', step: 0, total: 0, elapsed: 0 } };
          return { ok: reply.ok !== false, status: reply.status || 200, json: async () => reply };
        }
        if (u.includes('/train/stop')) return { ok: true, status: 200, json: async () => ({ ok: true }) };
        if (u.includes('/train/status')) return { ok: true, status: 200, json: async () => status };
        if (u.includes('/train/runs')) return { ok: true, status: 200, json: async () => runs };
        const body =
          u.includes('/settings') ? { model: 'gpt-4o-mini', theme: 'system', temperature: 0.7,
                                      approval_mode: 'ask', approval_timeout: 300 }
          : u.includes('/chats') ? { chats: [] }
          : u.includes('/update') ? { current: '0.1.0', checked: false, message: 'not configured' }
          : { ok: true };
        return { ok: true, status: 200, json: async () => body, text: async () => '' };
      };
      w.requestAnimationFrame = (cb) => setTimeout(cb, 0);
      w.navigator.clipboard = { writeText: async () => {} };
      w.confirm = () => true; w.alert = () => {}; w.scrollTo = () => {};
      Object.defineProperty(w.HTMLElement.prototype, 'scrollIntoView', { value() {} });
      // jsdom has no canvas backend; the loss chart must degrade, not throw.
      Object.defineProperty(w.HTMLCanvasElement.prototype, 'getContext', {
        value: () => ({ setTransform() {}, clearRect() {}, beginPath() {}, moveTo() {},
                        lineTo() {}, stroke() {}, arc() {}, fill() {}, }),
      });
    },
  });
  const { window } = dom;
  for (let i = 0; i < 80; i++) {
    await new Promise((r) => setTimeout(r, 25));
    if (!window.document.getElementById('p').disabled) break;
  }
  return { window, doc: window.document, calls, streams };
}

const click = (el) => el.dispatchEvent(new el.ownerDocument.defaultView.MouseEvent('click', { bubbles: true }));
const settle = () => new Promise((r) => setTimeout(r, 140));
const posted = (calls, path) => calls.filter((c) => c.method === 'POST' && c.path.startsWith(path));

test('the Train tab exists and switches the view', async () => {
  const { doc } = await boot();
  const tab = doc.getElementById('viewTrain');
  assert.ok(tab, 'no Train tab in the sidebar');
  click(tab);
  await settle();
  assert.ok(doc.body.classList.contains('training'), 'body did not enter the training view');
  assert.ok(doc.getElementById('train').classList.contains('on'), '#train stayed hidden');
  assert.equal(tab.getAttribute('aria-selected'), 'true');
  assert.equal(doc.getElementById('viewChat').getAttribute('aria-selected'), 'false');
});

test('switching back to Chat restores the composer', async () => {
  const { doc } = await boot();
  click(doc.getElementById('viewTrain'));
  await settle();
  click(doc.getElementById('viewChat'));
  await settle();
  assert.equal(doc.body.classList.contains('training'), false);
  assert.equal(doc.getElementById('train').classList.contains('on'), false);
  assert.equal(doc.getElementById('viewChat').getAttribute('aria-selected'), 'true');
});

test('one tab is selected on first launch', async () => {
  const { doc } = await boot();
  assert.ok(doc.getElementById('viewChat').classList.contains('active'),
            'neither tab looks selected before anything is clicked');
});

test('starting a run sends dataset as a list of sources, not a string', async () => {
  const { doc, calls } = await boot();
  click(doc.getElementById('viewTrain'));
  await settle();
  doc.getElementById('tModel').value = 'unsloth/tiny';
  doc.getElementById('tDataset').value = 'my/data';
  doc.getElementById('trainForm').dispatchEvent(new doc.defaultView.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  const [start] = posted(calls, '/train/start');
  assert.ok(start, 'submitting the form posted nothing');
  const cfg = start.body.config;
  assert.ok(Array.isArray(cfg.dataset), `dataset must be a list, got ${JSON.stringify(cfg.dataset)}`);
  assert.equal(cfg.dataset[0].name, 'my/data');
  assert.equal(cfg.dataset[0].split_type, 'train');
  assert.equal(cfg.model_name, 'unsloth/tiny');
  assert.equal(cfg.method, 'sft');
});

test('max steps of zero is omitted rather than sent as a zero cap', async () => {
  const { doc, calls } = await boot();
  click(doc.getElementById('viewTrain'));
  await settle();
  doc.getElementById('tSteps').value = '0';
  doc.getElementById('trainForm').dispatchEvent(new doc.defaultView.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  const [start] = posted(calls, '/train/start');
  assert.equal('max_steps' in start.body.config, false,
               'max_steps: 0 would cap the run at no steps at all');
});

test('an empty model is refused in the page and posts nothing', async () => {
  const { doc, calls } = await boot();
  click(doc.getElementById('viewTrain'));
  await settle();
  doc.getElementById('tModel').value = '';
  doc.getElementById('trainForm').dispatchEvent(new doc.defaultView.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  assert.equal(posted(calls, '/train/start').length, 0, 'posted an incomplete config');
  assert.match(doc.getElementById('tError').textContent, /required/i);
});

test("a conflict shows the engine's own message and re-enables Start", async () => {
  const { doc } = await boot({
    start: { ok: false, status: 409, error: 'run run-earlier is running. Stop it before starting another; one GPU runs one job.' },
  });
  click(doc.getElementById('viewTrain'));
  await settle();
  doc.getElementById('trainForm').dispatchEvent(new doc.defaultView.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  assert.match(doc.getElementById('tError').textContent, /run-earlier/,
               'the blocking run was not named');
  assert.equal(doc.getElementById('tStart').disabled, false, 'Start left disabled after a refusal');
});

test('a rejected config re-enables Start without a status refresh to rescue it', async () => {
  // The 409 path calls refreshTraining, which resets the button as a side
  // effect. A 400 does not, so this is the case that proves the reset is
  // actually done here rather than inherited from the refresh.
  const { doc } = await boot({
    start: { ok: false, status: 400, error: 'config needs at least model_name and dataset' },
  });
  click(doc.getElementById('viewTrain'));
  await settle();
  doc.getElementById('trainForm').dispatchEvent(new doc.defaultView.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  assert.match(doc.getElementById('tError').textContent, /model_name/);
  assert.equal(doc.getElementById('tStart').disabled, false,
               'Start stayed disabled, so the form is unusable after one bad submit');
});

test('live events move the progress bar, the step and the loss', async () => {
  const { doc, streams } = await boot();
  click(doc.getElementById('viewTrain'));
  await settle();
  doc.getElementById('trainForm').dispatchEvent(new doc.defaultView.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  const stream = streams[streams.length - 1];
  assert.ok(stream, 'no progress stream was opened');
  stream.emit('state', { cursor: 1, state: 'running' });
  stream.emit('progress', { cursor: 2, step: 30, total: 60 });
  stream.emit('metric', { cursor: 3, loss: 0.4321, learning_rate: 2e-4, epoch: 0.5, step: 30 });
  stream.emit('log', { cursor: 4, line: 'loading checkpoint shards' });
  await settle();
  assert.equal(doc.getElementById('tStep').textContent, '30 / 60');
  assert.equal(doc.getElementById('tLoss').textContent, '0.4321');
  // The value, not its formatting: the style engine normalises "50.0%" to
  // "50%", and an assertion on the string tests the CSS parser, not the bar.
  assert.equal(parseFloat(doc.getElementById('tBar').style.width), 50);
  assert.match(doc.getElementById('tlog').textContent, /checkpoint shards/);
  assert.equal(doc.getElementById('tState').textContent, 'running');
  assert.equal(doc.getElementById('tStop').hidden, false, 'Stop is not offered mid-run');
});

test('a failed ending shows the reason and offers Start again', async () => {
  const { doc, streams } = await boot();
  click(doc.getElementById('viewTrain'));
  await settle();
  doc.getElementById('trainForm').dispatchEvent(new doc.defaultView.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  const stream = streams[streams.length - 1];
  stream.emit('end', { cursor: 9, state: 'failed', error: 'CUDA out of memory', elapsed: 42, step: 3, total: 60 });
  await settle();
  assert.match(doc.getElementById('tError').textContent, /out of memory/);
  assert.equal(doc.getElementById('tState').textContent, 'failed');
  assert.equal(doc.getElementById('tStart').disabled, false);
  assert.equal(doc.getElementById('tStop').hidden, true, 'Stop still offered after the run ended');
  assert.ok(stream.closed, 'the stream was left open after the run ended');
});

test('a dropped-history resync is said out loud, not spliced over', async () => {
  const { doc, streams } = await boot();
  click(doc.getElementById('viewTrain'));
  await settle();
  doc.getElementById('trainForm').dispatchEvent(new doc.defaultView.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  streams[streams.length - 1].emit('resync', {});
  await settle();
  assert.match(doc.getElementById('tlog').textContent, /earlier output dropped/i);
});

test('Stop asks the engine to stop', async () => {
  const { doc, calls, streams } = await boot();
  click(doc.getElementById('viewTrain'));
  await settle();
  doc.getElementById('trainForm').dispatchEvent(new doc.defaultView.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  streams[streams.length - 1].emit('state', { cursor: 1, state: 'running' });
  await settle();
  click(doc.getElementById('tStop'));
  await settle();
  const [stop] = posted(calls, '/train/stop');
  assert.ok(stop, 'Stop sent nothing');
  // The run id, not a bare /train/stop.
  //
  // The engine refuses to stop a run other than the one asked for, so that a
  // tab left open on a finished run cannot cancel whatever someone started
  // after it. That guard reads the id from the path -- and the button never
  // sent one, so it could never fire, and the stale tab won. Three server
  // tests covered a request the product did not make.
  assert.notEqual(stop.path, '/train/stop',
                  'Stop did not name its run, so the stale-tab guard cannot fire');
  assert.match(stop.path, /^\/train\/stop\/[^/]+$/,
               `unexpected stop path: ${stop.path}`);
});

test('Stop names the run the view is actually watching', async () => {
  // Not just "some id": the id has to be the one this tab is following, or
  // the guard passes for the wrong reason.
  const { doc, calls, streams } = await boot({
    start: { ok: true, run: { id: 'run-being-watched', state: 'pending' } },
  });
  click(doc.getElementById('viewTrain'));
  await settle();
  doc.getElementById('trainForm').dispatchEvent(
    new doc.defaultView.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  streams[streams.length - 1].emit('state', { cursor: 1, state: 'running' });
  await settle();
  click(doc.getElementById('tStop'));
  await settle();
  const [stop] = posted(calls, '/train/stop');
  assert.ok(stop, 'Stop sent nothing');
  assert.equal(stop.path, '/train/stop/run-being-watched');
});

test('a run already in flight is picked up when the view opens', async () => {
  const { doc, streams } = await boot({
    status: { run: { id: 'run-earlier', state: 'running', step: 12, total: 100, elapsed: 610, error: null },
              metrics: [{ loss: 1.1, step: 6 }, { loss: 0.9, step: 12 }] },
    runs: { runs: [{ id: 'run-earlier', state: 'running', elapsed: 610, last_loss: 0.9, error: null }] },
  });
  click(doc.getElementById('viewTrain'));
  await settle();
  assert.equal(doc.getElementById('tState').textContent, 'running',
               'a run started in an earlier session was not adopted');
  assert.equal(doc.getElementById('tStep').textContent, '12 / 100');
  assert.equal(doc.getElementById('tLoss').textContent, '0.9000');
  assert.equal(doc.getElementById('tElapsed').textContent, '10m 10s');
  assert.ok(streams.length > 0, 'no stream was opened for the run in flight');
});

test('previous runs are listed with their outcome', async () => {
  const { doc } = await boot({
    runs: { runs: [
      { id: 'run-a', state: 'done', elapsed: 3720, last_loss: 0.21, error: null },
      { id: 'run-b', state: 'failed', elapsed: 12, last_loss: null, error: 'CUDA out of memory' }] },
  });
  click(doc.getElementById('viewTrain'));
  await settle();
  const rows = doc.getElementById('tHistory').children;
  assert.equal(rows.length, 2, 'the run history did not render');
  assert.match(rows[0].textContent, /run-a/);
  assert.match(rows[0].textContent, /1h 2m/);
  assert.match(rows[1].textContent, /failed/);
  assert.equal(rows[1].title, 'CUDA out of memory', 'the failure reason is unreachable');
});

test('the method hint changes with the method', async () => {
  const { doc } = await boot();
  click(doc.getElementById('viewTrain'));
  await settle();
  const select = doc.getElementById('tMethod');
  const before = doc.getElementById('tMethodHint').textContent;
  select.value = 'dpo';
  select.dispatchEvent(new doc.defaultView.Event('change', { bubbles: true }));
  await settle();
  const after = doc.getElementById('tMethodHint').textContent;
  assert.notEqual(after, before, 'the hint is inert');
  assert.match(after, /chosen/i);
});

test('a local run posts no remote block', async () => {
  const { doc, calls } = await boot();
  click(doc.getElementById('viewTrain'));
  await settle();
  doc.getElementById('trainForm').dispatchEvent(
    new doc.defaultView.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  const [start] = posted(calls, '/train/start');
  assert.ok(start, 'submitting posted nothing');
  assert.equal(start.body.config.remote, undefined,
               'a local run asked for a remote host');
});

test('choosing a remote server posts the block the CLI and YAML use', async () => {
  // The same shape as `remote:` in a config file and --remote-host on the
  // CLI. The engine passes the config through untouched, so this is what
  // decides where the run happens.
  const { doc, calls } = await boot();
  click(doc.getElementById('viewTrain'));
  await settle();
  const runOn = doc.getElementById('tRunOn');
  runOn.value = 'remote';
  runOn.dispatchEvent(new doc.defaultView.Event('change', { bubbles: true }));
  await settle();
  doc.getElementById('tRemoteHost').value = 'gpubox';
  doc.getElementById('tRemotePython').value = '/opt/conda/bin/python';
  doc.getElementById('trainForm').dispatchEvent(
    new doc.defaultView.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  const [start] = posted(calls, '/train/start');
  assert.ok(start, 'submitting posted nothing');
  assert.deepEqual(start.body.config.remote, {
    host: 'gpubox',
    python: '/opt/conda/bin/python',
    workdir: '~/.praisonai-train',
  });
});

test('the remote fields are hidden until they apply', async () => {
  const { doc } = await boot();
  click(doc.getElementById('viewTrain'));
  await settle();
  const host = doc.getElementById('tRemoteHost');
  assert.equal(doc.defaultView.getComputedStyle(host.closest('.tf')).display, 'none',
               'the SSH host field is shown for a local run');
  const runOn = doc.getElementById('tRunOn');
  runOn.value = 'remote';
  runOn.dispatchEvent(new doc.defaultView.Event('change', { bubbles: true }));
  await settle();
  assert.notEqual(doc.defaultView.getComputedStyle(host.closest('.tf')).display, 'none',
                  'choosing a remote server did not reveal the host field');
});

/** Fill the remote fields, then submit, and return what was posted. */
async function submitRemote(doc, calls, { host, python, workdir, runOn = 'remote' }) {
  const select = doc.getElementById('tRunOn');
  select.value = runOn;
  select.dispatchEvent(new doc.defaultView.Event('change', { bubbles: true }));
  await settle();
  if (host !== undefined) doc.getElementById('tRemoteHost').value = host;
  if (python !== undefined) doc.getElementById('tRemotePython').value = python;
  if (workdir !== undefined) doc.getElementById('tRemoteWorkdir').value = workdir;
  // `required` on the host field blocks a real submit, which silently made an
  // earlier version of these tests assert nothing at all. Drive the handler.
  doc.getElementById('tRemoteHost').required = false;
  doc.getElementById('trainForm').dispatchEvent(
    new doc.defaultView.Event('submit', { bubbles: true, cancelable: true }));
  await settle();
  return posted(calls, '/train/start')[0];
}

test('a whitespace-only host is not a host', async () => {
  const { doc, calls } = await boot();
  click(doc.getElementById('viewTrain'));
  await settle();
  const start = await submitRemote(doc, calls, { host: '   ' });
  assert.ok(start, 'nothing was posted, so this test proved nothing');
  assert.equal(start.body.config.remote, undefined,
               'posted a remote block whose host is blank');
});

test('switching back to this computer drops a host already typed', async () => {
  // The block is built from the choice, not left behind by it.
  const { doc, calls } = await boot();
  click(doc.getElementById('viewTrain'));
  await settle();
  const start = await submitRemote(doc, calls, { host: 'gpubox', runOn: 'local' });
  assert.ok(start, 'nothing was posted');
  assert.equal(start.body.config.remote, undefined,
               'a local run carried the remote host that had been typed');
});

test('an emptied remote directory falls back to the default', async () => {
  const { doc, calls } = await boot();
  click(doc.getElementById('viewTrain'));
  await settle();
  const start = await submitRemote(doc, calls, { host: 'gpubox', workdir: '' });
  assert.ok(start, 'nothing was posted');
  assert.equal(start.body.config.remote.workdir, '~/.praisonai-train',
               'clearing the field sent an empty working directory');
});

test('an emptied remote python falls back to the default', async () => {
  const { doc, calls } = await boot();
  click(doc.getElementById('viewTrain'));
  await settle();
  const start = await submitRemote(doc, calls, { host: 'gpubox', python: '' });
  assert.ok(start, 'nothing was posted');
  assert.equal(start.body.config.remote.python, 'python3');
});

test('every method the engine accepts is offered', async () => {
  const { doc } = await boot();
  const offered = [...doc.getElementById('tMethod').options].map((o) => o.value).sort();
  assert.deepEqual(offered, ['cpo', 'cpt', 'dpo', 'grpo', 'kto', 'orpo', 'reward', 'sft'],
                   'the picker and the trainer registry disagree');
});
