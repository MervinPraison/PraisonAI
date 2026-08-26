/**
 * Chat persistence, against the fake storage.
 *
 * The interesting cases are all failure cases. A repository that round-trips a
 * chat correctly and mishandles a corrupt file loses conversations silently,
 * which is the worst outcome available for a chat app.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { createChatRepository, SCHEMA_VERSION, type StoredChat } from "./repository.ts";
import { createFakeStorage } from "../../../testing/src/fake-storage.ts";

const chat = (over: Partial<StoredChat> = {}): StoredChat => ({
  id: "c1",
  title: "First chat",
  updated: 1000,
  messages: [{ role: "user", content: "hi", at: 1 }],
  engineId: "remote-http",
  ...over,
});

test("a saved chat round-trips", async () => {
  const storage = createFakeStorage();
  const repo = createChatRepository(storage);
  await repo.save(chat());

  const loaded = await repo.load("c1");
  assert.equal(loaded.ok, true);
  assert.deepEqual(loaded.ok === true ? loaded.chat : null, chat());
});

test("a missing chat is missing, not an error", async () => {
  // Absence is an ordinary outcome -- opening a deleted chat from a stale link
  // should say "not found", not "storage failed".
  const repo = createChatRepository(createFakeStorage());
  const loaded = await repo.load("nope");
  assert.equal(loaded.ok, false);
  assert.equal(loaded.ok === false && loaded.reason, "missing");
});

test("a chat written by a newer client is refused, not silently truncated", async () => {
  // The rule that prevents version skew becoming data loss. If we read what we
  // recognise and write it back, every field the newer client added is gone.
  const storage = createFakeStorage();
  await storage.write(
    { namespace: "chats", id: "future" },
    JSON.stringify({ schemaVersion: SCHEMA_VERSION + 1, chat: chat({ id: "future" }) }),
  );

  const loaded = await createChatRepository(storage).load("future");
  assert.equal(loaded.ok, false);
  assert.equal(loaded.ok === false && loaded.reason, "too_new");
});

test("a chat at the current schema version is accepted", async () => {
  // The pair, so "always refuse" cannot pass the test above.
  const storage = createFakeStorage();
  await storage.write(
    { namespace: "chats", id: "c1" },
    JSON.stringify({ schemaVersion: SCHEMA_VERSION, chat: chat() }),
  );
  const loaded = await createChatRepository(storage).load("c1");
  assert.equal(loaded.ok, true);
});

test("a corrupt file is reported rather than making the chat vanish", async () => {
  const storage = createFakeStorage();
  await storage.write({ namespace: "chats", id: "broken" }, "{ not json");
  const repo = createChatRepository(storage);

  const loaded = await repo.load("broken");
  assert.equal(loaded.ok, false);
  assert.equal(loaded.ok === false && loaded.reason, "unreadable");

  // And it must be discoverable without loading every chat by hand.
  assert.deepEqual(await repo.listUnreadable(), ["broken"]);
});

test("one corrupt file does not hide the chats that are fine", async () => {
  const storage = createFakeStorage();
  const repo = createChatRepository(storage);
  await repo.save(chat({ id: "good", updated: 5 }));
  await storage.write({ namespace: "chats", id: "broken" }, "}}}");

  const list = await repo.list();
  assert.deepEqual(list.map((c) => c.id), ["good"]);
  assert.deepEqual(await repo.listUnreadable(), ["broken"]);
});

test("the list is most-recent-first", async () => {
  const repo = createChatRepository(createFakeStorage());
  await repo.save(chat({ id: "old", updated: 10 }));
  await repo.save(chat({ id: "new", updated: 99 }));
  await repo.save(chat({ id: "mid", updated: 50 }));

  assert.deepEqual((await repo.list()).map((c) => c.id), ["new", "mid", "old"]);
});

test("a storage failure is reported as unreadable rather than thrown at the caller", async () => {
  // A chat list that throws takes the whole screen down. One unreadable row
  // should cost one row.
  const storage = createFakeStorage();
  const repo = createChatRepository(storage);
  await repo.save(chat());
  storage.failNext("disk gone");

  const loaded = await repo.load("c1");
  assert.equal(loaded.ok, false);
  assert.equal(loaded.ok === false && loaded.reason, "unreadable");
});

test("removing a chat that is not there succeeds", async () => {
  const repo = createChatRepository(createFakeStorage());
  await assert.doesNotReject(() => repo.remove("never-existed"));
});

test("a chat records which engine produced it", async () => {
  // So a transcript opened after an engine swap can say so, rather than
  // silently mixing two conventions in one conversation.
  const repo = createChatRepository(createFakeStorage());
  await repo.save(chat({ engineId: "praisonai-ts" }));
  const loaded = await repo.load("c1");
  assert.equal(loaded.ok === true ? loaded.chat.engineId : null, "praisonai-ts");
});

test("a chat file with no engineId reads as unknown rather than failing", async () => {
  // Forward and backward compatibility: a field added later must not make
  // every existing transcript unreadable.
  const storage = createFakeStorage();
  const { engineId: _omitted, ...withoutEngine } = chat();
  await storage.write(
    { namespace: "chats", id: "c1" },
    JSON.stringify({ schemaVersion: SCHEMA_VERSION, chat: withoutEngine }),
  );
  const loaded = await createChatRepository(storage).load("c1");
  assert.equal(loaded.ok, true);
  assert.equal(loaded.ok === true ? loaded.chat.engineId : null, "unknown");
});
