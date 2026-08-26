/**
 * The screen-reader announcement policy.
 *
 * Driven from real events through core's reducer, like every other test in this
 * layer, so the states being announced are ones the wire can actually produce.
 *
 * Every "must not announce X" below is paired with the test that fails an
 * implementation which announces nothing at all -- because "announce nothing"
 * satisfies every negative rule here and is the state the app is in today.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  ANNOUNCE_INTERVAL_MS,
  announce,
  initialAnnouncer,
  type AnnouncerState,
  type Announcement,
} from "./announce.ts";
import { en } from "../i18n/strings.ts";
import { apply, initialTurn, type TurnState } from "../../../core/src/run/transcript.ts";
import type { RunEvent } from "../../../protocol/src/events.ts";

const M = "m1";
const start: RunEvent = { type: "start", msgId: M, runId: "r1" };
const delta = (text: string): RunEvent => ({ type: "delta", msgId: M, text });
const end: RunEvent =
  { type: "end", msgId: M, userIndex: 0, assistantIndex: 1, versions: 1, active: 0 };

const run = (...events: readonly RunEvent[]): TurnState =>
  events.reduce<TurnState>(apply, initialTurn);

const tick = (state: AnnouncerState, turn: TurnState, nowMs: number) =>
  announce(state, { turn, strings: en, locale: "en", nowMs });

const texts = (list: readonly Announcement[]): readonly string[] => list.map((a) => a.text);
const joined = (list: readonly Announcement[]): string => texts(list).join(" | ");

test("a half-written sentence is NOT announced", () => {
  // THE BUG a naive aria-live region has: the region mutates several times a
  // second, so the reader says "The", "The file", "The file cont" -- restarting
  // forever and never reaching the end of a sentence.
  const turn = run(start, delta("The file cont"));
  const result = tick(initialAnnouncer, turn, 0);
  assert.deepEqual(result.announcements, []);
});

test("the sentence IS announced once it is finished", () => {
  // The pair. An implementation that announced nothing would pass the test
  // above and leave the app completely opaque to a blind user.
  const turn = run(start, delta("The file contains three lines. "));
  const result = tick(initialAnnouncer, turn, 0);
  assert.deepEqual(texts(result.announcements), ["The file contains three lines."]);
  assert.equal(result.announcements[0]?.politeness, "polite");
});

test("text already announced is never announced again", () => {
  // Re-reading the whole answer on every update is the second-most-common bug
  // in a live region, and it makes a long answer unlistenable.
  const first = tick(initialAnnouncer, run(start, delta("One. ")), 0);
  const second = tick(first.state, run(start, delta("One. Two. ")), ANNOUNCE_INTERVAL_MS);
  assert.deepEqual(texts(first.announcements), ["One."]);
  assert.deepEqual(texts(second.announcements), ["Two."], "the first sentence must not repeat");
});

test("announcements are rate-limited, so short sentences do not machine-gun", () => {
  // A model emitting one-clause sentences would otherwise produce a new
  // utterance every 300ms; the reader cannot speak that fast and the queue
  // grows without bound.
  const first = tick(initialAnnouncer, run(start, delta("One. ")), 0);
  const tooSoon = tick(first.state, run(start, delta("One. Two. ")), ANNOUNCE_INTERVAL_MS - 1);
  assert.deepEqual(tooSoon.announcements, []);

  const later = tick(tooSoon.state, run(start, delta("One. Two. ")), ANNOUNCE_INTERVAL_MS);
  assert.deepEqual(texts(later.announcements), ["Two."], "the held-back text must not be lost");
});

test("reasoning is NEVER announced", () => {
  // It is ancillary by construction and routinely longer than the answer.
  // Speaking it means the answer arrives minutes late, if at all -- while
  // staying perfectly visible and navigable on screen for everyone else.
  const turn = run(start, { type: "reasoning", msgId: M, text: "I should check the file first. " });
  const result = tick(initialAnnouncer, turn, 0);
  assert.equal(turn.reasoning.trim() !== "", true, "the fixture must actually have reasoning");
  assert.deepEqual(result.announcements, []);
});

test("the answer IS announced even when reasoning is present", () => {
  // The pair to the rule above: an implementation that skipped everything would
  // pass it by doing nothing.
  const turn = run(
    start,
    { type: "reasoning", msgId: M, text: "I should check the file first. " },
    delta("The file has three lines. "),
  );
  const result = tick(initialAnnouncer, turn, 0);
  assert.deepEqual(texts(result.announcements), ["The file has three lines."]);
  assert.equal(joined(result.announcements).includes("I should check"), false);
});

test("the trailing fragment is flushed when the turn ends", () => {
  // A model that finishes without terminal punctuation -- a bare list item, a
  // truncated answer, a code fence -- would otherwise have its last clause held
  // back forever, and the user would never hear the end of the response.
  const turn = run(start, delta("Here is the answer"), end);
  const result = tick(initialAnnouncer, turn, 0);
  assert.ok(texts(result.announcements).includes("Here is the answer"));
  assert.ok(texts(result.announcements).includes(en.announceTurnComplete));
});

test("the trailing fragment is NOT flushed mid-stream", () => {
  // The pair. Flushing on every tick is the stutter this policy exists to
  // remove: the fragment would be announced and then announced again, complete.
  const turn = run(start, delta("Here is the answer"));
  assert.deepEqual(tick(initialAnnouncer, turn, 10_000).announcements, []);
});

test("an approval request interrupts, ignores the rate limit, and is announced first", () => {
  // THE BUG. The run is BLOCKED: core/src/run/approvals.ts notes the engine
  // gives up after 300 seconds. A polite announcement queues behind however
  // much of the answer has streamed, so the user is asked after the prompt has
  // already timed out -- and the run stalls with nothing on screen to explain
  // it to anyone who cannot see the buttons appear.
  const streaming = run(start, delta("I need to remove the build directory. "));
  const first = tick(initialAnnouncer, streaming, 0);
  assert.equal(first.announcements.length, 1);

  const blocked = run(
    start,
    delta("I need to remove the build directory. "),
    { type: "tool_call", msgId: M, callId: "c1", name: "rm", args: { path: "build" } },
    { type: "approval_request", msgId: M, approvalId: "ap1", callId: "c1", name: "rm", args: {} },
  );
  // Well inside the rate limit: a policy that debounced this would be silent.
  const second = tick(first.state, blocked, 100);
  const approval = second.announcements[0];
  assert.ok(approval !== undefined);
  assert.equal(approval.reason, "approval");
  assert.equal(approval.politeness, "assertive");
  assert.ok(approval.text.includes("rm"));
});

test("an approval is announced once, not on every publish", () => {
  const blocked = run(
    start,
    { type: "tool_call", msgId: M, callId: "c1", name: "rm", args: {} },
    { type: "approval_request", msgId: M, approvalId: "ap1", callId: "c1", name: "rm", args: {} },
  );
  const first = tick(initialAnnouncer, blocked, 0);
  const again = tick(first.state, blocked, 10_000);
  assert.equal(first.announcements.filter((a) => a.reason === "approval").length, 1);
  assert.equal(again.announcements.filter((a) => a.reason === "approval").length, 0);
});

test("tool ARGUMENTS are never announced", () => {
  // `args` is an arbitrary bag from the wire and can be a whole file body. Read
  // aloud it is both useless and, for a command carrying a credential, harmful.
  const secret = "AKIA0123456789SECRET";
  const turn = run(start, { type: "tool_call", msgId: M, callId: "c1", name: "bash", args: { cmd: secret } });
  const result = tick(initialAnnouncer, turn, 0);
  assert.equal(joined(result.announcements).includes(secret), false);
});

test("the tool's name and status ARE announced", () => {
  // The pair. Silence about tools is why the app currently feels crashed: forty
  // seconds pass with no way to tell "working" from "hung".
  const started = run(start, { type: "tool_call", msgId: M, callId: "c1", name: "search", args: {} });
  const first = tick(initialAnnouncer, started, 0);
  assert.deepEqual(texts(first.announcements), ["Running search"]);

  const finished = apply(started,
    { type: "tool_result", msgId: M, callId: "c1", name: "search", ok: true, output: "x", seconds: 1 });
  const second = tick(first.state, finished, 10_000);
  assert.deepEqual(texts(second.announcements), ["Succeeded: search, 1.0s"]);

  // And once only.
  assert.deepEqual(tick(second.state, finished, 20_000).announcements, []);
});

test("a tool that never came back is announced differently from one that worked", () => {
  // settle() turns a call with no result into `unresolved`, and the announcement
  // must not let that pass as success -- silence is not success, in any medium.
  const abandoned = run(start, delta("Trying. "),
    { type: "tool_call", msgId: M, callId: "c1", name: "search", args: {} }, end);
  const spoken = joined(tick(initialAnnouncer, abandoned, 0).announcements);
  assert.ok(spoken.includes(en.toolStatus("unresolved")), spoken);
  assert.equal(spoken.includes(en.toolStatus("ok")), false);
});

test("an error is announced assertively and exactly once", () => {
  const failed = run(start, delta("Starting. "),
    { type: "error", msgId: M, kind: "transport", message: "socket closed" });
  const first = tick(initialAnnouncer, failed, 0);
  const error = first.announcements.find((a) => a.reason === "error");
  assert.ok(error !== undefined);
  assert.equal(error.politeness, "assertive");
  assert.ok(error.text.includes("socket closed"));
  assert.equal(first.announcements[0]?.reason, "error", "assertive must be emitted first");
  assert.deepEqual(tick(first.state, failed, 5000).announcements, []);
});

test("a cancelled turn says so, and its partial answer is still flushed", () => {
  // The user stopped it; what the model had already written is content they
  // asked for and must not be swallowed by the stop.
  const stopped = run(start, delta("I was about to"), { type: "cancelled", msgId: M, runId: "r1" });
  const spoken = texts(tick(initialAnnouncer, stopped, 0).announcements);
  assert.ok(spoken.includes("I was about to"));
  assert.ok(spoken.includes(en.announceStopped));
});

test("refused events are announced at the end, and NOT during the stream", () => {
  // transcript.ts keeps them because "an ignore with no record is
  // indistinguishable from a quiet success" -- just as true for a user who
  // cannot see the row. But interrupting the answer to report a decoder gap is
  // not worth it, so it waits.
  const midStream = run(start, delta("Working. "), { type: "delta", msgId: "other", text: "stray" });
  const first = tick(initialAnnouncer, midStream, 0);
  assert.equal(midStream.dropped.length, 1);
  assert.equal(first.announcements.some((a) => a.reason === "dropped"), false);

  const ended = apply(midStream, end);
  const second = tick(first.state, ended, 10_000);
  assert.equal(second.announcements.some((a) => a.reason === "dropped"), true);
});

test("a new turn starts the cursor over instead of skipping the answer", () => {
  // Without the turn key, the character cursor from the previous answer points
  // into the middle of the new one and its first sentences are silently lost --
  // for every reply after the first.
  const firstTurn = run(start, delta("A long first answer that ran on for a while. "), end);
  const after = tick(initialAnnouncer, firstTurn, 0);
  assert.ok(after.state.spokenChars > 10);

  const secondTurn = [
    { type: "start", msgId: "m2", runId: "r2" } as RunEvent,
    { type: "delta", msgId: "m2", text: "Short. " } as RunEvent,
  ].reduce<TurnState>(apply, initialTurn);
  const next = tick(after.state, secondTurn, 10_000);
  assert.deepEqual(texts(next.announcements), ["Short."]);
});

test("nothing to say returns the very same state object", () => {
  // A caller uses identity to decide whether to touch the live region at all.
  // A fresh object every tick means writing to the region on every publish,
  // which is the mutation storm this whole policy avoids.
  const turn = run(start, delta("half a sen"));
  // The first tick genuinely changes something: it records which turn is being
  // announced, which is what makes the next answer start over correctly.
  const first = tick(initialAnnouncer, turn, 0);
  assert.deepEqual(first.announcements, []);
  assert.notEqual(first.state.turnKey, null);

  const second = tick(first.state, turn, 10_000);
  assert.deepEqual(second.announcements, []);
  assert.equal(Object.is(second.state, first.state), true);
});

test("Japanese text is announced, so the policy is not silently ASCII-only", () => {
  // An ASCII-only sentence rule finds no boundary in Japanese at all, so the
  // whole answer is withheld until the turn ends -- a silent, locale-specific
  // regression to "announce nothing".
  const turn = run(start, delta("ファイルを読みます。次に"));
  const result = announce(initialAnnouncer, { turn, strings: en, locale: "ja", nowMs: 0 });
  assert.deepEqual(texts(result.announcements), ["ファイルを読みます。"]);
});
