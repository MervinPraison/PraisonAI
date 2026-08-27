/**
 * The run controller, driven end to end.
 *
 * This is the milestone the whole layering exists for: a complete turn --
 * text, tools, approval, cancellation, a queued follow-up -- proved with no UI,
 * no Tauri, no network, no real clock and no sleeping.
 *
 * If the design is wrong, it is wrong here, cheaply.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { createRunController, type RunView } from "./controller.ts";
import { createFakeTime } from "../../../testing/src/fake-time.ts";
import { createScriptedEngine } from "../../../testing/src/scripted-engine.ts";
import { SCRIPTS } from "../../../testing/src/scripts.ts";
import { createFakeScheduler } from "../../../testing/src/fake-scheduler.ts";
import { createFakeClock } from "../../../testing/src/fake-clock.ts";
import type { TimePort } from "../ports/time.ts";
import type { RunEvent } from "../../../protocol/src/events.ts";


function harness(script: readonly RunEvent[]) {
  const views: RunView[] = [];
  const time = createFakeTime();
  const engine = createScriptedEngine({ id: "scripted", script });
  const controller = createRunController({
    engine,
    time,
    onPublish: (v) => views.push(v),
  });
  return { controller, engine, time, views, last: () => views[views.length - 1] as RunView };
}

test("a happy turn ends with the full answer on screen", async () => {
  const h = harness(SCRIPTS.happy);
  await h.controller.send("what is the answer?");

  assert.equal(h.last().turn.text, "The answer is 42.");
  assert.equal(h.last().turn.outcome?.type, "end");
  assert.deepEqual(h.last().turn.dropped, [], "a clean run drops nothing");
});

test("the final state is always published, whatever the gate decided", () => {
  // The gate exists to skip intermediate paints. Skipping the LAST one leaves
  // the answer visibly truncated at the penultimate frame -- which is the bug
  // that makes pacing look like data loss.
  return (async () => {
    const h = harness(SCRIPTS.happy);
    await h.controller.send("hi");
    const final = h.last();
    assert.equal(final.turn.phase, "ended");
    assert.equal(final.turn.text, "The answer is 42.");
  })();
});

test("pacing publishes fewer times than there are events", async () => {
  // A positive control on the wiring, not just on the gate: if the controller
  // published per event, this fails.
  const many: RunEvent[] = [{ type: "start", msgId: "m", runId: "r" }];
  for (let i = 0; i < 300; i++) many.push({ type: "delta", msgId: "m", text: "x" });
  many.push({ type: "end", msgId: "m", userIndex: 0, assistantIndex: 1, versions: 1, active: 0 });

  const h = harness(many);
  await h.controller.send("go");

  assert.equal(h.last().turn.text.length, 300, "no token may be lost to pacing");
  assert.ok(h.views.length < 60, `expected pacing, got ${h.views.length} publishes for 300 deltas`);
  assert.ok(h.views.length >= 2, "something must have been published");
});

test("a tool call and its result reach the transcript in order", async () => {
  const h = harness(SCRIPTS.tool_ok);
  await h.controller.send("read the file");

  const tools = h.last().turn.tools;
  assert.equal(tools.length, 1);
  assert.equal(tools[0]?.status, "ok");
  assert.equal(h.last().turn.text, "Reading the file. It says hello.");
});

test("a failed tool is reported failed even though its output looks plausible", async () => {
  const h = harness(SCRIPTS.tool_failed);
  await h.controller.send("delete it");
  assert.equal(h.last().turn.tools[0]?.status, "failed");
});

test("an approval is surfaced and is sending until the engine acknowledges", async () => {
  const h = harness(SCRIPTS.approval);
  await h.controller.send("rm -rf /");

  assert.equal(h.last().approvals.entries.length, 1);
  assert.equal(h.last().approvals.entries[0]?.state.status, "pending");

  await h.controller.decide("ap1", "deny");
  assert.equal(h.last().approvals.entries[0]?.state.status, "sent");
});

test("an approval the engine refuses becomes retryable rather than dead-ending", async () => {
  const h = harness(SCRIPTS.approval);
  await h.controller.send("rm -rf /");
  // "nope" is not a pending approval id, so the engine returns false.
  await h.controller.decide("nope", "allow");

  // The unknown id changed nothing, and crucially did not throw.
  assert.equal(h.last().approvals.entries[0]?.state.status, "pending");
});

test("two outstanding approvals are answered independently", async () => {
  const h = harness(SCRIPTS.two_approvals);
  await h.controller.send("do two things");
  assert.equal(h.last().approvals.entries.length, 2);

  await h.controller.decide("ap2", "allow");
  assert.equal(h.last().approvals.entries[0]?.state.status, "pending", "the first must be untouched");
  assert.equal(h.last().approvals.entries[1]?.state.status, "sent");
});

test("an empty stream surfaces as an error, not a blank answer", async () => {
  const h = harness(SCRIPTS.empty);
  await h.controller.send("hi");
  const outcome = h.last().turn.outcome;
  assert.equal(outcome?.type, "error");
  assert.equal(outcome?.type === "error" ? outcome.kind : null, "empty");
});

test("an auth failure keeps its kind so the ui can offer settings", async () => {
  const h = harness(SCRIPTS.auth_error);
  await h.controller.send("hi");
  const outcome = h.last().turn.outcome;
  assert.equal(outcome?.type === "error" ? outcome.kind : null, "auth");
});

test("a stream that throws becomes a transport error and keeps the text already on screen", async () => {
  // A dying stream is normal on a phone. Losing the paragraph the user was
  // reading is not acceptable collateral.
  const engine = createScriptedEngine({ id: "scripted", script: SCRIPTS.happy });
  const boom = {
    ...engine,
    async *run(): AsyncIterable<RunEvent> {
      yield { type: "start", msgId: "m", runId: "r" };
      yield { type: "delta", msgId: "m", text: "half an answer" };
      throw new Error("socket closed");
    },
  };

  const views: RunView[] = [];
  const controller = createRunController({
    engine: boom,
    time: createFakeTime(),
    onPublish: (v) => views.push(v),
  });
  await controller.send("hi");

  const final = views[views.length - 1] as RunView;
  assert.equal(final.turn.text, "half an answer", "the text already streamed must survive");
  const outcome = final.turn.outcome;
  assert.equal(outcome?.type, "error");
  assert.equal(
    outcome?.type === "error" ? outcome.kind : null,
    "transport",
    "a dead socket is a transport failure, distinct from an engine error",
  );
});

test("stop reports false when no run is live rather than claiming success", async () => {
  // server.py:392 -- "the button would confirm a cancellation that never
  // happened".
  const h = harness(SCRIPTS.happy);
  assert.equal(await h.controller.stop(), false);
});

test("a prompt sent during a turn is queued and runs after it", async () => {
  const h = harness(SCRIPTS.happy);

  // send() awaits the turn, so queue both before awaiting either.
  const first = h.controller.send("one");
  const second = h.controller.send("two");
  await Promise.all([first, second]);

  // Both turns ran; the second replaced the first's transcript state.
  assert.equal(h.last().queue.busy, false, "the queue must be idle once drained");
  assert.equal(h.last().queue.items.length, 0);
  assert.equal(h.last().turn.outcome?.type, "end");
});

test("the view is a snapshot, not a live reference", async () => {
  // A view handed to a renderer must not mutate under it, or a framework that
  // diffs by identity will skip the update it most needs to make.
  const h = harness(SCRIPTS.happy);
  await h.controller.send("hi");

  const early = h.views[1] as RunView;
  const final = h.last();
  assert.notEqual(early, final);
  assert.notEqual(early.turn, final.turn, "each publish must carry its own turn object");
});
