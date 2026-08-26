/**
 * The session — where a turn actually lands on disk.
 *
 * Before this existed, ChatRepository was fully tested and called by nothing:
 * every conversation evaporated. So the cases that matter here are about what
 * gets written, what deliberately does NOT, and the indices reported back —
 * because a wrong index silently addresses the wrong message.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { createSession, titleFrom } from "./session.ts";
import { createFakeStorage } from "../../../testing/src/fake-storage.ts";

const build = (over: Partial<Parameters<typeof createSession>[0]> = {}) => {
  const storage = createFakeStorage();
  let ids = 0;
  let clock = 1000;
  const session = createSession({
    storage,
    engineId: "scripted",
    now: () => ++clock,
    newChatId: () => `c${++ids}`,
    ...over,
  });
  return { storage, session };
};

test("a completed turn is written with BOTH sides of the conversation", () => {
  // The hole this file closed: the transcript is assistant-only, so without a
  // deliberate join the user's own message is never stored anywhere.
  const { session } = build();
  return session.record("what is 2+2?", "4").then(async (indices) => {
    assert.notEqual(indices, null);
    const chat = session.current();
    assert.equal(chat?.messages.length, 2);
    assert.deepEqual(chat?.messages.map((m) => m.role), ["user", "assistant"]);
    assert.equal(chat?.messages[0]?.content, "what is 2+2?");
    assert.equal(chat?.messages[1]?.content, "4");
  });
});

test("the indices point at the messages they claim to", () => {
  // These travel to the UI as end.userIndex, and Fork and Delete address them.
  // Off by one here deletes the wrong message.
  const { session } = build();
  return session.record("first", "reply").then(async (a) => {
    assert.deepEqual(a, { userIndex: 0, assistantIndex: 1, versions: 1, active: 0 });
    const b = await session.record("second", "reply2");
    assert.deepEqual(b, { userIndex: 2, assistantIndex: 3, versions: 1, active: 0 });

    const messages = session.current()?.messages ?? [];
    assert.equal(messages[b!.userIndex]?.content, "second");
    assert.equal(messages[b!.assistantIndex]?.content, "reply2");
  });
});

test("a second turn appends rather than replacing the chat", async () => {
  const { session } = build();
  await session.record("one", "1");
  await session.record("two", "2");
  assert.equal(session.current()?.messages.length, 4);
});

test("a failed write reports null rather than a fabricated index", async () => {
  // null means "not on disk", which is what withholds Fork and Delete. A
  // number here would offer actions against a message that does not exist.
  const { storage, session } = build();
  storage.failNext("disk full");
  assert.equal(await session.record("hello", "hi"), null);
});

test("a failed write does not advance the in-memory chat either", async () => {
  // Otherwise the next turn's indices are computed against messages that were
  // never stored, and every index after it is wrong.
  const { storage, session } = build();
  await session.record("one", "1");
  storage.failNext("disk full");
  await session.record("two", "2");

  assert.equal(session.current()?.messages.length, 2, "the failed turn must not be kept");
  const next = await session.record("three", "3");
  assert.equal(next?.userIndex, 2, "indices continue from what is actually stored");
});

test("a chat survives a reload", async () => {
  const { storage, session } = build();
  await session.record("remember me", "ok");
  const id = session.current()!.id;

  const reopened = createSession({ storage, engineId: "scripted", now: () => 1, newChatId: () => "x" });
  assert.equal(await reopened.open(id), true);
  assert.equal(reopened.current()?.messages[0]?.content, "remember me");
});

test("opening a chat that is not there fails without throwing", async () => {
  const { session } = build();
  assert.equal(await session.open("nope"), false);
  assert.equal(session.current(), null);
});

test("reset starts a new chat rather than appending to the last one", async () => {
  // Otherwise "New chat" silently continues the previous conversation, and the
  // model sees history the user believes they cleared.
  const { session } = build();
  await session.record("first chat", "a");
  const first = session.current()!.id;

  session.reset();
  await session.record("second chat", "b");
  assert.notEqual(session.current()!.id, first);
  assert.equal(session.current()!.messages.length, 2);
  assert.equal((await session.list()).length, 2);
});

test("the chat is titled from the first message, and keeps that title", async () => {
  // A list of rows all called "Untitled" cannot be scanned.
  const { session } = build();
  await session.record("Explain monads", "...");
  assert.equal(session.current()?.title, "Explain monads");
  await session.record("and then?", "...");
  assert.equal(session.current()?.title, "Explain monads", "the title must not follow the latest message");
});

test("removing the open chat clears it", async () => {
  const { session } = build();
  await session.record("doomed", "x");
  const id = session.current()!.id;
  await session.remove(id);
  assert.equal(session.current(), null);
  assert.deepEqual(await session.list(), []);
});

test("removing a different chat leaves the open one alone", async () => {
  // The pair for the test above.
  const { session } = build();
  await session.record("keep", "x");
  const keep = session.current()!.id;
  await session.remove("some-other-chat");
  assert.equal(session.current()?.id, keep);
});

test("the chat records which engine produced it", async () => {
  const { session } = build({ engineId: "praisonai-ts" });
  await session.record("hi", "hello");
  assert.equal(session.current()?.engineId, "praisonai-ts");
});

// ---- titleFrom -------------------------------------------------------------

test("a title uses the first non-empty line", () => {
  assert.equal(titleFrom("\n\n  Real question  \nmore"), "Real question");
});

test("a blank prompt is Untitled rather than an empty row", () => {
  assert.equal(titleFrom("   \n  "), "Untitled");
});

test("a long title is cut on a code point, never mid-emoji", () => {
  // Slicing by code unit splits a surrogate pair and renders a replacement
  // character in the chat list.
  const title = titleFrom("👨‍👩‍👧‍👦".repeat(40));
  assert.ok(!title.includes("�"), "no replacement character");
  assert.ok([...title].length <= 60);
});

test("a short title is not truncated", () => {
  assert.equal(titleFrom("short"), "short");
});
