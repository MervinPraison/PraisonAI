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

import { createSession, historyFor, persistenceFor, titleFrom } from "./session.ts";
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

// ---- the adapter where the two vocabularies meet ----------------------------

test("persistenceFor keeps the prompt and the answer the right way round", () => {
  // Swapping these two same-typed arguments survived the entire suite. Every
  // persisted conversation would have the user's message and the model's reply
  // transposed -- and a transposed transcript still renders, still round-trips,
  // and still reads as a working app until someone actually reads one back.
  const { session } = build();
  const persistence = persistenceFor(session);

  return persistence.record({ prompt: "what is 2+2?" }, "4").then(() => {
    const messages = session.current()?.messages ?? [];
    assert.equal(messages[0]?.role, "user");
    assert.equal(messages[0]?.content, "what is 2+2?", "the user's message must be the user's");
    assert.equal(messages[1]?.role, "assistant");
    assert.equal(messages[1]?.content, "4", "the answer must be the assistant's");
  });
});

test("persistenceFor reports the indices the session produced", () => {
  // The engine puts these into `end.userIndex`, which decides whether Fork and
  // Delete are offered at all. Returning a fabricated pair would offer actions
  // against messages that are not there.
  const { session } = build();
  return persistenceFor(session).record({ prompt: "hi" }, "hello").then((indices) => {
    assert.deepEqual(indices, { userIndex: 0, assistantIndex: 1, versions: 1, active: 0 });
  });
});

test("persistenceFor propagates a failed write as null", () => {
  // null is what withholds Fork and Delete. Swallowing the failure here would
  // report a turn as on disk when it is not.
  const { storage, session } = build();
  storage.failNext("disk full");
  return persistenceFor(session).record({ prompt: "hi" }, "hello").then((indices) => {
    assert.equal(indices, null);
  });
});

test("every turn advances the chat's updated time", () => {
  // `updated: at` -> `updated: base.updated` survived: the chat keeps the
  // timestamp of its FIRST message forever. A list ordered by `updated` then
  // sinks the conversation you are actively using to the bottom, while one you
  // have not touched in a month sits at the top.
  //
  // Nothing saw it because no test read back what was written across TWO
  // turns -- the same blind spot that let the persisted answer be duplicated.
  const { session } = build();

  return (async () => {
    await session.record("first question", "first answer");
    const afterOne = session.current();
    assert.ok(afterOne !== null);

    await session.record("second question", "second answer");
    const afterTwo = session.current();
    assert.ok(afterTwo !== null);

    assert.ok(
      afterTwo.updated > afterOne.updated,
      `updated did not advance: ${afterOne.updated} -> ${afterTwo.updated}`,
    );
    assert.equal(afterTwo.messages.length, 4, "and both turns are still there");
  })();
});

test("a title of exactly the maximum length is not truncated", () => {
  // `points.length <= 60` -> `< 60` survived: a title of exactly 60 graphemes
  // gets an ellipsis it does not need, and loses its last character to make
  // room for it.
  const { session } = build();
  const exactly60 = "a".repeat(60);
  return session.record(exactly60, "answer").then(() => {
    const title = session.current()?.title ?? "";
    assert.equal(title, exactly60, "a title at the limit must survive whole");
    assert.equal(title.includes("…"), false);
  });
});

test("a title one character over the maximum IS truncated", () => {
  // The pair, so a function that never truncates cannot pass the test above.
  const { session } = build();
  return session.record("b".repeat(61), "answer").then(() => {
    const title = session.current()?.title ?? "";
    assert.ok(title.endsWith("…"), `expected an ellipsis, got ${JSON.stringify(title)}`);
    assert.ok(title.length <= 60);
  });
});

test("a title is cut on a code POINT boundary, never mid-emoji", () => {
  // `[...line]` -> `line.split("")` survived. A long first message containing
  // an astral character gets sliced through a surrogate pair, and the chat
  // list row ends in a replacement character forever.
  const emoji = "👍".repeat(80); // 80 code points, 160 code units
  const title = titleFrom(emoji);

  assert.ok(title.endsWith("…"), "a long title is elided");
  assert.equal([...title].length, 60, "59 code points plus the ellipsis");
  assert.ok(!title.includes("�"), "no replacement character");
  assert.deepEqual(
    [...title.slice(0, -1)],
    [...emoji].slice(0, 59),
    "every kept code point must be whole",
  );
});

test("a title at exactly the limit is not elided -- the pair", () => {
  // Without this, a titleFrom that always elided would pass above.
  const sixty = "a".repeat(60);
  assert.equal(titleFrom(sixty), sixty);
});

// ---- the session as the engine's MEMORY ------------------------------------
//
// `persistenceFor` is how a turn gets written; `historyFor` is how it gets
// remembered. The second did not exist, so the model was shown none of a
// conversation the app was storing and rendering.

test("historyFor reports the completed turns of the open chat, oldest first", async () => {
  const { session } = build();
  await session.record("What is the capital of France?", "Paris.");
  await session.record("And its population?", "About 2.1 million.");

  assert.deepEqual(historyFor(session).messages(), [
    { role: "user", content: "What is the capital of France?" },
    { role: "assistant", content: "Paris." },
    { role: "user", content: "And its population?" },
    { role: "assistant", content: "About 2.1 million." },
  ]);
});

test("a REOPENED conversation reports its stored history, not an empty one", async () => {
  // The force-stop case, and the one a session-scoped in-memory history would
  // fail: the app is relaunched, the chat is opened from the list, and the
  // model must still know what was said. A `historyFor` reading anything other
  // than `current()` -- a buffer filled by `record`, say -- returns nothing
  // here while the transcript on screen is full.
  const storage = createFakeStorage();
  let clock = 1000;
  const first = createSession({
    storage,
    engineId: "scripted",
    now: () => ++clock,
    newChatId: () => "c1",
  });
  await first.record("What is the capital of France?", "Paris.");

  // A different Session over the same storage: a new process, same disk.
  const relaunched = createSession({
    storage,
    engineId: "scripted",
    now: () => ++clock,
    newChatId: () => "c-never-used",
  });
  assert.deepEqual(historyFor(relaunched).messages(), [], "nothing is open yet");

  assert.equal(await relaunched.open("c1"), true);
  assert.deepEqual(historyFor(relaunched).messages(), [
    { role: "user", content: "What is the capital of France?" },
    { role: "assistant", content: "Paris." },
  ]);
});

test("history is re-read on every call, so the turn just recorded is in the next one", async () => {
  // Captured once, this returns the empty array forever and every conversation
  // is one question long from the model's point of view.
  const { session } = build();
  const history = historyFor(session);
  assert.deepEqual(history.messages(), []);

  await session.record("one", "first answer");

  assert.equal(history.messages().length, 2);
});

test("a new chat has no history, and starting one clears what was there", async () => {
  // `reset()` is what New chat calls. A history that survived it would leak the
  // previous conversation into a chat the user believes is empty -- the same
  // class of defect as the transcript that used to survive New chat.
  const { session } = build();
  await session.record("secret question", "secret answer");
  assert.equal(historyFor(session).messages().length, 2);

  session.reset();

  assert.deepEqual(historyFor(session).messages(), []);
});

test("history carries roles, not just text", async () => {
  // A projection that dropped `role` would still produce the right sentences in
  // the right order and be useless: the model could not tell its own previous
  // answers from the user's questions.
  const { session } = build();
  await session.record("q", "a");

  assert.deepEqual(historyFor(session).messages().map((m) => m.role), ["user", "assistant"]);
});
