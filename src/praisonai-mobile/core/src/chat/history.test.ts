/**
 * The truncation rule, and the shape of the answer when it fires.
 *
 * `truncateHistory` is the only place in this package that decides what a
 * model is allowed to remember, so every clause of the rule in history.ts
 * gets a case here that fails if the clause is removed.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  HISTORY_CHAR_BUDGET,
  truncateHistory,
  type HistoryMessage,
} from "./history.ts";

const turn = (role: "user" | "assistant", content: string): HistoryMessage => ({ role, content });

test("a conversation inside the budget passes through unchanged, in order", async () => {
  const messages = [
    turn("user", "What is the capital of France?"),
    turn("assistant", "Paris."),
    turn("user", "And its population?"),
  ];

  const bounded = truncateHistory(messages, HISTORY_CHAR_BUDGET);

  assert.deepEqual(bounded.messages, messages);
  assert.equal(bounded.dropped, 0);
});

test("over the budget, the RECENT end is what survives", async () => {
  // The direction is the whole point: "and its population?" is answerable from
  // the last two turns and unanswerable from the first two.
  const bounded = truncateHistory(
    [turn("user", "aaaa"), turn("assistant", "bbbb"), turn("user", "cccc"), turn("assistant", "dddd")],
    8,
  );

  assert.deepEqual(bounded.messages.map((m) => m.content), ["cccc", "dddd"]);
  assert.equal(bounded.dropped, 2);
});

test("a history that would BEGIN with an assistant message drops that message", async () => {
  // 4 characters of room reaches only "dddd", an answer with no question above
  // it. Keeping it hands the model something it appears to have volunteered.
  const bounded = truncateHistory(
    [turn("user", "aaaa"), turn("assistant", "bbbb"), turn("user", "cccc"), turn("assistant", "dddd")],
    4,
  );

  assert.deepEqual(bounded.messages, []);
  assert.equal(bounded.dropped, 4);
});

test("a message too large to fit STOPS the walk rather than being skipped over", async () => {
  // Skipping the oversized message to fit older, smaller ones would reorder the
  // conversation around a hole: the model would read a follow-up whose subject
  // was removed.
  const bounded = truncateHistory(
    [turn("user", "short"), turn("assistant", "x".repeat(50)), turn("user", "tail")],
    10,
  );

  assert.deepEqual(bounded.messages.map((m) => m.content), ["tail"]);
});

test("a conversation that exactly fills the budget still fits", async () => {
  // `>` and not `>=`. An off-by-one here silently drops the oldest turn of
  // every conversation that lands on the boundary.
  const bounded = truncateHistory([turn("user", "12345"), turn("assistant", "67890")], 10);

  assert.equal(bounded.messages.length, 2);
  assert.equal(bounded.dropped, 0);
});

test("an empty conversation truncates to an empty conversation, not to a throw", async () => {
  const bounded = truncateHistory([], HISTORY_CHAR_BUDGET);

  assert.deepEqual(bounded.messages, []);
  assert.equal(bounded.dropped, 0);
});

test("the default budget is large enough for an ordinary conversation", async () => {
  // A budget accidentally set to a small number would truncate every chat and
  // look exactly like the bug this change removes. 200 turns of 100 characters
  // is a long conversation by phone standards and must survive whole.
  const messages: HistoryMessage[] = [];
  for (let i = 0; i < 200; i++) {
    messages.push(turn(i % 2 === 0 ? "user" : "assistant", "x".repeat(100)));
  }

  assert.equal(truncateHistory(messages).dropped, 0);
});
