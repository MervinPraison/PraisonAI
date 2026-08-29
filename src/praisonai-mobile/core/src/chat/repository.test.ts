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

// ---- a bad file must not take the good ones with it -------------------------

test("one corrupt chat does not hide every chat listed after it", () => {
  // `if (!result.ok) continue` -> `break` survived. Half the user's library
  // vanishes with no error anywhere, and listUnreadable still reports only the
  // one bad file -- so the app is confidently wrong about how much is missing.
  const storage = createFakeStorage();
  const repo = createChatRepository(storage);

  const write = async (id: string, body: string): Promise<void> => {
    await storage.write({ namespace: "chats", id }, body);
  };

  return (async () => {
    await write("a", JSON.stringify({ version: 1, chat: { id: "a", title: "A", messages: [], updated: 1 } }));
    await write("b", "{ not json at all");
    await write("c", JSON.stringify({ version: 1, chat: { id: "c", title: "C", messages: [], updated: 2 } }));
    await write("d", JSON.stringify({ version: 1, chat: { id: "d", title: "D", messages: [], updated: 3 } }));

    const listed = await repo.list();
    assert.deepEqual(
      listed.map((s) => s.id).sort(),
      ["a", "c", "d"],
      "every readable chat must survive an unreadable neighbour",
    );
    assert.deepEqual(await repo.listUnreadable(), ["b"]);
  })();
});

test("a chat file with no id is reported unreadable, not loaded with an undefined id", () => {
  // Dropping `typeof chat.id !== "string"` survived. The file loads ok:true
  // with id undefined, shows in list() as a row addressed at nothing, and
  // DISAPPEARS from listUnreadable -- so the one rule the header states,
  // "a chat that fails to parse is reported, not skipped", breaks in the
  // direction nobody checks. Saving it then writes to the key "chats/undefined".
  const storage = createFakeStorage();
  const repo = createChatRepository(storage);

  return (async () => {
    await storage.write(
      { namespace: "chats", id: "x" },
      JSON.stringify({ version: 1, chat: { title: "no id here", messages: [], updated: 1 } }),
    );
    assert.deepEqual(await repo.list(), [], "a chat with no id must not be listed");
    assert.deepEqual(await repo.listUnreadable(), ["x"], "and must be reported as unreadable");
  })();
});

test("an id that vanishes between listing and reading is not called corrupt", () => {
  // Reporting `missing` as unreadable shows a permanent corruption warning for
  // a file that is simply gone -- deleted by another tab, or evicted.
  const storage = createFakeStorage();
  const ghosting = {
    ...storage,
    listIds: async () => ["ghost"],
    read: async () => null,
  };
  const repo = createChatRepository(ghosting);

  return (async () => {
    assert.deepEqual(await repo.list(), []);
    assert.deepEqual(await repo.listUnreadable(), [], "absent is not the same as corrupt");
  })();
});

// ---- a chat file the app did not write --------------------------------------
//
// `load` coerces every field because the file is on a user's disk and can be
// anything. Two of those coercions could be deleted with a green suite.

test("a chat whose messages field is not an array loads as empty, not as itself", async () => {
  // `Array.isArray(chat.messages) ? chat.messages : []` -> `chat.messages`
  // survived. With `messages: "hi"` the string is spread as two one-character
  // messages: the transcript shows junk, and the indices `end` reports point
  // past the real messages, so Fork and Delete then address the wrong ones.
  const storage = createFakeStorage();
  await storage.write(
    { namespace: "chats", id: "c1" },
    JSON.stringify({ schemaVersion: SCHEMA_VERSION, chat: { id: "c1", messages: "hi" } }),
  );

  const loaded = await createChatRepository(storage).load("c1");
  assert.equal(loaded.ok, true);
  assert.deepEqual(loaded.ok && loaded.chat.messages, [], "a non-array must not become messages");
});

test("a chat with no title shows as Untitled, not as nothing", async () => {
  // Dropping the string check survived: the chat list renders a blank,
  // unidentifiable row that the user cannot tell from any other blank row.
  const storage = createFakeStorage();
  await storage.write(
    { namespace: "chats", id: "c2" },
    JSON.stringify({ schemaVersion: SCHEMA_VERSION, chat: { id: "c2", messages: [] } }),
  );

  const loaded = await createChatRepository(storage).load("c2");
  assert.equal(loaded.ok && loaded.chat.title, "Untitled");
});

test("a well-formed chat keeps its own title and messages -- the pair", async () => {
  // Without this, coercing everything to a constant would pass both above.
  const storage = createFakeStorage();
  const chat: StoredChat = {
    id: "c3",
    title: "Deploying the thing",
    updated: 42,
    messages: [{ role: "user", content: "hi", at: 1 }],
    engineId: "remote-http",
  };
  await storage.write(
    { namespace: "chats", id: "c3" },
    JSON.stringify({ schemaVersion: SCHEMA_VERSION, chat }),
  );

  const loaded = await createChatRepository(storage).load("c3");
  assert.equal(loaded.ok && loaded.chat.title, "Deploying the thing");
  assert.equal(loaded.ok && loaded.chat.messages.length, 1);
  assert.equal(loaded.ok && loaded.chat.updated, 42);
});
