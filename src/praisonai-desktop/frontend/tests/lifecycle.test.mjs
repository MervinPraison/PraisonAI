/**
 * Conversation lifecycle, against the real engine.
 *
 * These exercise the paths a user actually walks -- send, appear in the
 * sidebar, reopen, rename by first message, fork, assign a project, delete --
 * because each one has a way to look fine while doing nothing.
 */
import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

/**
 * Find the engine through the lockfile it writes -- the same file, in the same
 * format, that src-tauri/src/lockfile.rs parses.
 *
 * Two earlier attempts were both wrong in the same direction: they reported
 * "no engine" when an engine was running, so all eleven tests below skipped and
 * the suite still exited 0. `pgrep -f 'engine/server.py'` matched the shell
 * running the pgrep; `lsof` returns nothing at all under a sandbox. The
 * lockfile needs neither, and the /health probe confirms the port is really
 * ours rather than a stale entry.
 */
async function enginePort() {
  const home = process.env.PRAISONAI_DESKTOP_HOME
    || `${process.env.HOME}/Library/Application Support/PraisonAI`;
  let text;
  try { text = readFileSync(`${home}/engine.lock`, 'utf8'); } catch { return null; }
  const port = Object.fromEntries(
    text.split('\n').filter(Boolean).map((l) => l.split('='))).port;
  if (!port) return null;
  try {
    const h = await (await fetch(`http://127.0.0.1:${port}/health`,
                                 { signal: AbortSignal.timeout(1500) })).json();
    return h && h.ok === true && h.version === 2 ? port : null;   // stale lock
  } catch { return null; }
}

const PORT = await enginePort();
const B = `http://127.0.0.1:${PORT}`;

// A suite that skips everything still exits 0. Set this in CI so an engine that
// failed to start is a failure, not eleven quiet dashes.
if (!PORT && process.env.PRAISONAI_TEST_REQUIRE_ENGINE === '1') {
  throw new Error('no live engine found via the lockfile, and PRAISONAI_TEST_REQUIRE_ENGINE=1');
}
const skip = { skip: PORT ? false : 'engine not running (start engine/server.py)' };
const api = async (path, opts) => (await fetch(B + path, opts)).json();
const post = (path, body) => api(path, {
  method: 'POST', headers: { 'content-type': 'application/json' },
  body: JSON.stringify(body ?? {}) });
// /chat answers with an SSE stream, not JSON. Draining it to completion is
// what makes the turn finish and persist, so every lifecycle assertion below
// depends on awaiting this rather than the JSON helper.
const chat = async (prompt, id, run, extra) => {
  const res = await fetch(B + '/chat', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ prompt, chat_id: id, run_id: run ?? id, ...extra }) });
  return res.text();
};

const chatId = () => 'lc' + Math.random().toString(36).slice(2, 8);

test('a new conversation appears in the sidebar list after one turn', skip, async () => {
  const id = chatId();
  await chat('Say hi.', id, id);
  const { chats } = await api('/chats');
  const row = chats.find((c) => c.id === id);
  assert.ok(row, 'the conversation is not in /chats, so the sidebar cannot show it');
  assert.equal(row.count, 2, 'both the prompt and the reply must be stored');
});

test('the title is taken from the first message, not left as "New chat"', skip, async () => {
  const id = chatId();
  await chat('What is the capital of France?', id, id);
  const { chats } = await api('/chats');
  const row = chats.find((c) => c.id === id);
  assert.notEqual(row.title, 'New chat', 'title never generated');
  assert.match(row.title, /capital/i);
});

test('reopening returns the full transcript', skip, async () => {
  const id = chatId();
  await chat('Say hi.', id, id);
  const convo = await api('/chats/' + id);
  assert.equal(convo.messages.length, 2);
  assert.equal(convo.messages[0].role, 'user');
  assert.equal(convo.messages[1].role, 'assistant');
  assert.ok(convo.messages[1].content.length > 0, 'the reply was not persisted');
});

test('a second turn appends rather than replacing', skip, async () => {
  const id = chatId();
  await chat('Say one.', id, id + 'a');
  await chat('Say two.', id, id + 'b');
  const convo = await api('/chats/' + id);
  assert.equal(convo.messages.length, 4, 'the second turn overwrote the first');
});

test('deleting a conversation removes it from the list', skip, async () => {
  const id = chatId();
  await chat('Say hi.', id, id);
  await fetch(`${B}/chats/${id}`, { method: 'DELETE' });
  const { chats } = await api('/chats');
  assert.ok(!chats.some((c) => c.id === id), 'deleted conversation still listed');
});

test('deleting one exchange removes exactly two messages', skip, async () => {
  const id = chatId();
  await chat('Say one.', id, id + 'a');
  await chat('Say two.', id, id + 'b');
  const before = (await api('/chats/' + id)).messages.length;
  await post(`/messages/${id}/0`);
  const after = await api('/chats/' + id);
  assert.equal(after.messages.length, before - 2, 'wrong number of messages removed');
  assert.match(after.messages[0].content, /two/i, 'the wrong exchange was deleted');
});

test('forking copies the prefix and leaves the original intact', skip, async () => {
  const id = chatId();
  await chat('Say one.', id, id + 'a');
  await chat('Say two.', id, id + 'b');
  const r = await post(`/fork/${id}/1`);
  assert.ok(r.ok && r.id, 'fork failed');
  const forked = await api('/chats/' + r.id);
  const original = await api('/chats/' + id);
  assert.equal(forked.messages.length, 2, 'fork did not stop at the chosen message');
  assert.equal(original.messages.length, 4, 'forking mutated the original');
  const { chats } = await api('/chats');
  assert.ok(chats.some((c) => c.id === r.id), 'the fork is not in the sidebar list');
});

test('a project assignment shows on the conversation and in the project list', skip, async () => {
  const id = chatId();
  await chat('Say hi.', id, id);
  await post(`/project/${id}`, { project: 'Zed-Test-Project' });
  const { chats } = await api('/chats');
  assert.equal(chats.find((c) => c.id === id).project, 'Zed-Test-Project');
  const { projects } = await api('/projects');
  assert.ok(projects.includes('Zed-Test-Project'));
  await fetch(`${B}/chats/${id}`, { method: 'DELETE' });
});

test('search finds a conversation by its body, not just its title', skip, async () => {
  const id = chatId();
  const needle = 'zebra' + Math.random().toString(36).slice(2, 6);
  await chat(`Reply with exactly: ${needle}`, id, id);
  const { hits } = await api('/search?q=' + needle);
  assert.ok(hits.some((h) => h.id === id), 'search missed a conversation containing the term');
  await fetch(`${B}/chats/${id}`, { method: 'DELETE' });
});

test('settings round-trip and are actually read back', skip, async () => {
  const before = await api('/settings');
  await post('/settings', { temperature: 0.42, auto_title: false });
  const after = await api('/settings');
  assert.equal(after.temperature, 0.42);
  assert.equal(after.auto_title, false);
  await post('/settings', { temperature: before.temperature, auto_title: before.auto_title });
});

test('an unknown cancel and an unknown approval both refuse', skip, async () => {
  const c = await fetch(`${B}/cancel/nope`, { method: 'POST' });
  assert.equal(c.status, 404, 'cancel claimed success for a run it never knew');
  const a = await fetch(`${B}/approve/nope`, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ choice: 'allow' }) });
  assert.equal(a.status, 404, 'approve claimed success for an unknown request');
});

// --- answer versions ---------------------------------------------------------

test('regenerating keeps the previous answer instead of overwriting it', skip, async () => {
  const id = 'ver-' + Date.now();
  await chat('Say only: alpha', id, id, { tools: false });
  await chat('Say only: beta', id, id + '-r', { tools: false, regenerate_of: 0 });

  const stored = await api(`/chats/${id}`);
  assert.equal(stored.messages.length, 2,
    'regenerating appended a second copy of the question instead of a version');
  assert.equal(stored.messages[1].version_count, 2, 'the earlier answer was discarded');
  assert.equal(stored.messages[1].version_active, 1, 'the newest answer is not the live one');

  // Switching back must change what the chat reads as.
  const newest = stored.messages[1].content;
  const back = await post(`/version/${id}/0/0`);
  assert.equal(back.ok, true);
  const after = await api(`/chats/${id}`);
  assert.notEqual(after.messages[1].content, newest, 'switching version changed nothing');
  assert.equal(after.messages[1].version_active, 0);

  await api(`/chats/${id}`, { method: 'DELETE' });
});

test('an unknown version and an unknown chat both refuse', skip, async () => {
  const id = 'ver2-' + Date.now();
  await chat('Say only: one', id, id, { tools: false });
  const tooHigh = await post(`/version/${id}/0/9`);
  assert.equal(tooHigh.ok, false, 'accepted a version that does not exist');
  const noChat = await post('/version/definitely-not-a-chat/0/0');
  assert.equal(noChat.ok, false);
  await api(`/chats/${id}`, { method: 'DELETE' });
});
