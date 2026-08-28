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
import { createDropSink } from "./drop-sink.ts";
import { PROTOCOL_VERSION } from "../../../protocol/src/version.ts";
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

// ---- the coalescer's time bound --------------------------------------------

test("a short answer paints while it streams, not in one lump at the end", async () => {
  // The defect: the coalescer flushed only at maxBytes (256) or on a
  // structured event, because nothing ever called tick(). So an answer shorter
  // than 256 characters produced ZERO intermediate paints and appeared all at
  // once when the run ended -- time-to-first-visible-token was the whole
  // answer's latency, in an app whose stated first priority is streaming.
  const deltas: RunEvent[] = Array.from({ length: 20 }, () => ({
    type: "delta", msgId: "m1", text: "short ",
  }));
  const h = harness([
    { type: "start", msgId: "m1", runId: "r1" },
    ...deltas,
    { type: "end", msgId: "m1", userIndex: 0, assistantIndex: 1, versions: 1, active: 0 },
  ]);

  const sent = h.controller.send("hi");
  for (let i = 0; i < 40; i++) {
    h.time.advance(20);
    h.time.tick();
    await Promise.resolve();
  }
  await sent;

  // PARTIAL text is the signal, not "more than one paint". Without a tick the
  // text goes straight from "" to the whole answer -- the `end` event flushes
  // and publishes regardless, so a weaker assertion passes against the very
  // defect this test exists for. That mistake was made here first.
  const full = h.views.at(-1)?.turn.text ?? "";
  const partial = h.views.filter((v) => v.turn.text !== "" && v.turn.text !== full);
  assert.ok(partial.length > 0, `text never appeared partially: only ever "" or the whole ${full.length} chars`);
});

test("the tick stops when the turn ends", async () => {
  // A tick firing after the turn settled would paint a frame into a finished
  // transcript -- and worse, keep a timer alive for the app's lifetime.
  const h = harness([
    { type: "start", msgId: "m1", runId: "r1" },
    { type: "delta", msgId: "m1", text: "hi" },
    { type: "end", msgId: "m1", userIndex: 0, assistantIndex: 1, versions: 1, active: 0 },
  ]);
  await h.controller.send("go");

  const before = h.views.length;
  h.time.advance(1000);
  h.time.tick();
  assert.equal(h.views.length, before, "a tick after the turn must publish nothing");
});

// ---- an approval the engine refuses -----------------------------------------

test("an approval the engine refuses is shown as failed, never as sent", async () => {
  // `ok ? acknowledge : reject` collapsing to always-acknowledge survived the
  // whole suite. The engine says "I did not accept that decision" -- because it
  // restarted, or the approval expired -- and the row still renders resolved.
  // The user sees their Deny confirmed against a command the engine never
  // denied, which is the one failure this table exists to make visible.
  const views: RunView[] = [];
  const engine = createScriptedEngine({
    id: "scripted",
    script: [
      { type: "start", msgId: "m", runId: "r" },
      { type: "approval_request", msgId: "m", approvalId: "a1", callId: "c1", name: "rm", args: { path: "/" } },
    ],
    approvals: [], // the engine does not recognise a1
  });
  const controller = createRunController({
    engine,
    time: createFakeTime(),
    onPublish: (v) => views.push(v),
  });

  await controller.send("do the thing");
  await controller.decide("a1", "deny");

  const entry = views[views.length - 1]?.approvals.entries.find((e) => e.approvalId === "a1");
  assert.ok(entry, "the approval should still be on screen");
  assert.equal(entry.state.status, "failed", "a refused decision must not read as sent");
  assert.equal(
    entry.state.status === "failed" ? entry.state.choice : null,
    "deny",
    "the choice the user made is still what failed",
  );
});

test("an approval the engine accepts is shown as sent", async () => {
  // The other half. Without it the test above passes against a controller that
  // rejects every decision, which is just as broken in the opposite direction.
  const views: RunView[] = [];
  const engine = createScriptedEngine({
    id: "scripted",
    script: [
      { type: "start", msgId: "m", runId: "r" },
      { type: "approval_request", msgId: "m", approvalId: "a1", callId: "c1", name: "ls", args: {} },
    ],
  });
  const controller = createRunController({
    engine,
    time: createFakeTime(),
    onPublish: (v) => views.push(v),
  });

  await controller.send("do the thing");
  await controller.decide("a1", "allow");

  const entry = views[views.length - 1]?.approvals.entries.find((e) => e.approvalId === "a1");
  assert.equal(entry?.state.status, "sent");
});

test("the flush tick is armed at maxDelayMs, not at some other period", async () => {
  // The fake's `every` discarded its period, so arming the coalescer's flush
  // at 60_000 instead of maxDelayMs left the entire suite green -- while
  // restoring the one-lump answer the streaming test above exists to prevent.
  // A period nothing observes is a period nothing has to get right.
  const time = createFakeTime();
  const controller = createRunController({
    engine: createScriptedEngine({ id: "scripted", script: SCRIPTS.happy }),
    time,
    maxDelayMs: 16,
    onPublish: () => {},
  });

  const sent = controller.send("hi");
  assert.deepEqual(time.intervalMs, [16], "the tick must be armed at maxDelayMs");
  await sent;
});

// ---- a frame the decoder refused --------------------------------------------

test("a frame the engine's decoder refused becomes a dropped row on the turn", async () => {
  // remote-http did `if (isDecoded(outcome)) yield` and discarded the rest --
  // and it is the ONLY production caller of decodeEvent. So a malformed
  // `tool_result` frame made its tool vanish and the turn rendered as a clean
  // answer, while the reducer's Dropped type, the view model's dropped row and
  // seven user-facing strings all sat unreachable.
  const views: RunView[] = [];
  const sink = createDropSink();
  const engine = createScriptedEngine({ id: "scripted", script: SCRIPTS.happy });

  const controller = createRunController({
    engine: {
      ...engine,
      async *run(req, signal) {
        for await (const event of engine.run(req, signal)) {
          // The engine refuses a frame partway through, as a real decoder does.
          if (event.type === "delta") sink.note("missing_msg_id", "tool_result");
          yield event;
        }
      },
    },
    time: createFakeTime(),
    dropSink: sink,
    onPublish: (v) => views.push(v),
  });

  await controller.send("hi");

  const dropped = views.at(-1)?.turn.dropped ?? [];
  assert.ok(dropped.length > 0, "the refused frame left no trace on the transcript");
  assert.equal(dropped[0]?.reason, "missing_msg_id");
  assert.equal(dropped[0]?.detail, "tool_result");
});

test("a refusal on the very last frame is still shown", async () => {
  // The loop ends after the terminal event, so a refusal arriving beside it
  // would never be drained by the per-event path alone.
  const views: RunView[] = [];
  const sink = createDropSink();
  const engine = createScriptedEngine({ id: "scripted", script: SCRIPTS.happy });

  const controller = createRunController({
    engine: {
      ...engine,
      async *run(req, signal) {
        for await (const event of engine.run(req, signal)) yield event;
        sink.note("unknown_event", "trailing");
      },
    },
    time: createFakeTime(),
    dropSink: sink,
    onPublish: (v) => views.push(v),
  });

  await controller.send("hi");
  assert.deepEqual(views.at(-1)?.turn.dropped.at(-1), {
    reason: "unknown_event",
    detail: "trailing",
  });
});

test("a clean run still drops nothing", async () => {
  // The pair. A controller that invented a dropped row per event would satisfy
  // both tests above and mark every healthy turn as damaged.
  const h = harness(SCRIPTS.happy);
  await h.controller.send("hi");
  assert.deepEqual(h.last().turn.dropped, []);
});

test("a drop on one turn does not cross onto the next clean turn", async () => {
  // The controller keeps ONE turn across sends, so a refusal on turn 1 that
  // was carried across `start` painted turn 2's clean answer as damaged --
  // a success made to look like a defect. The fresh turn must start clean.
  const views: RunView[] = [];
  const sink = createDropSink();
  const engine = createScriptedEngine({ id: "scripted", script: SCRIPTS.happy });
  let run = 0;

  const controller = createRunController({
    engine: {
      ...engine,
      async *run(req, signal) {
        run += 1;
        const dropOnThisRun = run === 1;
        for await (const event of engine.run(req, signal)) {
          if (dropOnThisRun && event.type === "delta") sink.note("missing_msg_id", "tool_result");
          yield event;
        }
      },
    },
    time: createFakeTime(),
    dropSink: sink,
    onPublish: (v) => views.push(v),
  });

  await controller.send("first");
  const afterFirst = views.at(-1)?.turn.dropped ?? [];
  assert.ok(afterFirst.length > 0, "the first turn must show its own drop");

  await controller.send("second");
  assert.deepEqual(
    views.at(-1)?.turn.dropped,
    [],
    "the second, clean turn must not inherit the first turn's dropped row",
  );
});

// ---- the approval table belongs to the turn, not to the app ------------------

test("a reused approvalId on a later turn is NOT shadowed by the answered one", async () => {
  // `approvals` was initialised once with the controller and only appended to.
  // An approvalId only has to be unique WITHIN a run for the protocol to hold,
  // so an engine that numbers them per run had its new request shadowed by the
  // previous turn's answered entry -- `addApproval` treats a duplicate id as
  // "the engine repeating itself", correct inside a turn and wrong across two.
  //
  // Measured before this: turn 1's prompt rendered `sent/allow` with dead
  // buttons, carrying TURN 0's args. A user could be shown `rm -rf /` as
  // already-allowed because an earlier `ls` reused the id, and the run then
  // blocks until the engine times out while the UI reads as answered. The
  // wrong-command-authorised failure the approvalId design exists to prevent,
  // arriving through the table's lifetime rather than through index pairing.
  const views: RunView[] = [];
  let turn = 0;
  const scriptFor = (cmd: string): RunEvent[] => [
    { type: "start", msgId: "m", runId: "r" },
    { type: "tool_call", msgId: "m", callId: "c1", name: "sh", args: { cmd } },
    { type: "approval_request", msgId: "m", approvalId: "ap1", callId: "c1", name: "sh", args: { cmd } },
    { type: "end", msgId: "m", userIndex: 0, assistantIndex: 1, versions: 1, active: 0 },
  ];
  const inner = createScriptedEngine({ id: "s", script: scriptFor("x"), approvals: ["ap1"] });
  const engine = {
    ...inner,
    async *run(_req: unknown, signal: AbortSignal) {
      for (const e of scriptFor(`turn ${turn} command`)) {
        if (signal.aborted) return;
        yield e;
      }
    },
    async decide() {
      return true;
    },
  } as typeof inner;

  const controller = createRunController({
    engine,
    time: createFakeTime(),
    onPublish: (v) => views.push(v),
  });

  await controller.send("first");
  await controller.decide("ap1", "allow");
  turn = 1;
  await controller.send("second");

  const entry = views.at(-1)?.approvals.entries.find((e) => e.approvalId === "ap1");
  assert.ok(entry, "the new turn's approval should be in the table");
  assert.deepEqual(entry.args, { cmd: "turn 1 command" }, "it must carry THIS turn's command");
  assert.equal(entry.state.status, "pending", "a fresh request must not read as already decided");
});

test("a duplicate approvalId WITHIN one turn is still the engine repeating itself", async () => {
  // The pair. Clearing per turn must not weaken the within-turn rule: the same
  // id twice in one run is a retransmission, not a second command, and adding
  // it twice would show the user two prompts for one decision.
  const views: RunView[] = [];
  const h = createRunController({
    engine: createScriptedEngine({
      id: "s",
      script: [
        { type: "start", msgId: "m", runId: "r" },
        { type: "approval_request", msgId: "m", approvalId: "ap1", callId: "c1", name: "sh", args: {} },
        { type: "approval_request", msgId: "m", approvalId: "ap1", callId: "c1", name: "sh", args: {} },
        { type: "end", msgId: "m", userIndex: 0, assistantIndex: 1, versions: 1, active: 0 },
      ],
      approvals: ["ap1"],
    }),
    time: createFakeTime(),
    onPublish: (v) => views.push(v),
  });

  await h.send("go");
  assert.equal(views.at(-1)?.approvals.entries.length, 1, "one id is one prompt");
});

test("switching chats clears the approvals of the one being left", async () => {
  const views: RunView[] = [];
  const controller = createRunController({
    engine: createScriptedEngine({ id: "s", script: SCRIPTS.approval, approvals: ["ap1"] }),
    time: createFakeTime(),
    onPublish: (v) => views.push(v),
  });
  await controller.send("go");
  assert.ok((views.at(-1)?.approvals.entries.length ?? 0) > 0, "the turn should have left one");

  controller.setChat("another-chat");
  assert.deepEqual(
    controller.view().approvals.entries,
    [],
    "a different conversation must not inherit the last one's prompts",
  );
});

test("refusals reach the screen while they arrive, not all at once at the end", async () => {
  // When EVERY frame is refused -- a proxy answering a stream with HTML --
  // nothing is ever yielded, so the event loop body never runs and the only
  // drain left was the one in `finally`. Measured: 60 refused frames/s for a
  // minute arrived as ONE synchronous burst of 3,600 appends, ~440ms of
  // blocked main thread on a phone, at the moment the app is trying to paint
  // the failure. Draining on the tick spreads it: worst single publish gap
  // fell from ~110ms to ~2ms for the same 3,600.
  const sink = createDropSink();
  const time = createFakeTime();
  const seen: number[] = [];

  const engine = {
    id: "s",
    protocolVersion: PROTOCOL_VERSION,
    capabilities: {
      streaming: true, reasoning: false, tools: true,
      approvals: false, cancellation: true, attachments: false,
    },
    async *run() {
      for (let i = 0; i < 20; i++) {
        sink.note("unparseable_json", `<html>502 #${i}</html>`);
        time.advance(20);
        time.tick();
        await Promise.resolve();
      }
    },
    async decide() { return false; },
    async cancel() { return false; },
    async dispose() {},
  } as unknown as Parameters<typeof createRunController>[0]["engine"];

  const controller = createRunController({
    engine, time, dropSink: sink,
    onPublish: (v) => seen.push(v.turn.dropped.length),
  });

  await controller.send("hi");

  // The signal is PARTIAL progress: a publish that carried some but not all.
  const final = seen.at(-1) ?? 0;
  assert.equal(final, 20, "all refusals must still arrive");
  assert.ok(
    seen.some((n) => n > 0 && n < final),
    `refusals only appeared in one lump: ${JSON.stringify(seen)}`,
  );
});

// ---- Stop, raced against a turn that is settling ----------------------------

/** An engine whose `cancel` takes a while, as a real network call does. */
function slowCancelEngine(cancelled: string[], ticks: number) {
  return {
    id: "s",
    protocolVersion: PROTOCOL_VERSION,
    capabilities: {
      streaming: true, reasoning: false, tools: true,
      approvals: false, cancellation: true, attachments: false,
    },
    async *run(req: { runId: string }) {
      yield { type: "start", msgId: "m", runId: req.runId };
      yield { type: "delta", msgId: "m", text: "hi" };
      yield { type: "end", msgId: "m", userIndex: 0, assistantIndex: 1, versions: 1, active: 0 };
    },
    async decide() { return false; },
    async cancel(runId: string) {
      cancelled.push(runId);
      for (let i = 0; i < ticks; i++) await Promise.resolve();
      return true;
    },
    async dispose() {},
  } as unknown as Parameters<typeof createRunController>[0]["engine"];
}

test("stopping as the turn settles does not throw", async () => {
  // `live.abort.abort()` re-read the closure variable AFTER awaiting the
  // engine, and cancel is a real network call for remote-http, so the turn can
  // settle inside that window. With the queue empty `live` is null by then and
  // this threw a TypeError. Both callers reach stop() through a floating
  // `void`, so the crash handler turned the whole app into the crash screen:
  // tapping Stop at the wrong instant blanked the page.
  const cancelled: string[] = [];
  const controller = createRunController({
    engine: slowCancelEngine(cancelled, 6),
    time: createFakeTime(),
    onPublish: () => {},
  });

  const sent = controller.send("one");
  await assert.doesNotReject(() => controller.stop());
  await sent;
});

test("stopping cancels the run that was live WHEN STOP WAS PRESSED", async () => {
  // The other half of the same race, and it has to be built deliberately:
  // `engine.cancel` is a real network call, so the first turn can SETTLE and
  // the queued follow-up can START while stop() is awaiting it. `abort()` then
  // re-read `live` and killed the NEW turn -- the user's follow-up died with
  // "the engine produced no output" and a Retry button, while stop() returned
  // true and the UI announced success. Cancelling "whatever is live" rather
  // than by id is exactly what runId exists to prevent.
  //
  // The race is forced here: cancel() releases the first turn and then waits
  // until the second has actually started.
  const cancelled: string[] = [];
  const views: RunView[] = [];
  let releaseFirst: () => void = () => {};
  const firstHeld = new Promise<void>((r) => { releaseFirst = r; });
  let secondStarted = false;
  let runs = 0;

  const engine = {
    id: "s",
    protocolVersion: PROTOCOL_VERSION,
    capabilities: {
      streaming: true, reasoning: false, tools: true,
      approvals: false, cancellation: true, attachments: false,
    },
    async *run(req: { runId: string }, signal: AbortSignal) {
      const mine = ++runs;
      yield { type: "start", msgId: `m${mine}`, runId: req.runId };
      if (mine === 1) {
        await firstHeld; // held open until cancel() lets it finish
      } else {
        secondStarted = true;
      }
      if (signal.aborted) return;
      yield { type: "delta", msgId: `m${mine}`, text: `answer ${mine}` };
      yield { type: "end", msgId: `m${mine}`, userIndex: 0, assistantIndex: 1, versions: 1, active: 0 };
    },
    async decide() { return false; },
    async cancel(runId: string) {
      cancelled.push(runId);
      releaseFirst();
      // Wait until the queued follow-up is genuinely the live run.
      for (let i = 0; i < 200 && !secondStarted; i++) await Promise.resolve();
      return true;
    },
    async dispose() {},
  } as unknown as Parameters<typeof createRunController>[0]["engine"];

  const controller = createRunController({
    engine,
    time: createFakeTime(),
    onPublish: (v) => views.push(v),
  });

  const first = controller.send("one");
  const second = controller.send("two"); // queued behind it
  await controller.stop();
  await Promise.all([first, second]);

  assert.equal(secondStarted, true, "the follow-up must have started, or the race was not reproduced");
  assert.deepEqual(cancelled.length, 1, "exactly one run should have been cancelled");
  assert.equal(
    views.at(-1)?.turn.text,
    "answer 2",
    "the queued follow-up must survive the previous turn's Stop",
  );
  assert.equal(views.at(-1)?.turn.outcome?.type, "end");
});

test("a second Stop reports success, not a refusal", async () => {
  // stop() had no idempotence: `live` is still set until the abort propagates,
  // so a second tap re-issued cancel for a run the engine had already
  // cancelled -- and every honest engine answers false for that. stopNotice
  // then announced "the engine did not accept the stop" for a stop that DID
  // happen, inverting the defect that notice was added for. The documented
  // background -> dispose path calls stop() twice by design.
  const cancelled: string[] = [];
  const controller = createRunController({
    engine: slowCancelEngine(cancelled, 0),
    time: createFakeTime(),
    onPublish: () => {},
  });

  const sent = controller.send("one");
  assert.equal(await controller.stop(), true);
  assert.equal(await controller.stop(), true, "a second tap must not read as a refusal");
  assert.equal(cancelled.length, 1, "and must not ask the engine twice");
  await sent;
});

test("stop with nothing running still reports false", async () => {
  // The pair: idempotence must not turn 'there was nothing to stop' into true.
  const controller = createRunController({
    engine: slowCancelEngine([], 0),
    time: createFakeTime(),
    onPublish: () => {},
  });
  assert.equal(await controller.stop(), false);
});

test("two OVERLAPPING stops share one cancel and both report success", async () => {
  // The `aborted` guard is sequential: it only catches a second tap AFTER the
  // first completed. Two stops that overlap -- the background -> dispose path
  // and the user's Stop button -- both pass it before either `engine.cancel`
  // (a real network call) resolves. Without coalescing, each issues its own
  // cancel; an honest engine answers false for the duplicate of an
  // already-cancelled run, so the second stop reported the real cancellation as
  // refused and stopNotice announced "the engine did not accept the stop". The
  // sequential idempotence test could not see this because it awaited the first
  // stop before the second, letting the abort propagate in between.
  const cancels: string[] = [];
  const engine = {
    id: "s",
    protocolVersion: PROTOCOL_VERSION,
    capabilities: {
      streaming: true, reasoning: false, tools: true,
      approvals: false, cancellation: true, attachments: false,
    },
    async *run(req: { runId: string }) {
      yield { type: "start", msgId: "m", runId: req.runId };
      for (let i = 0; i < 50; i++) await Promise.resolve();
      yield { type: "end", msgId: "m", userIndex: 0, assistantIndex: 1, versions: 1, active: 0 };
    },
    async decide() { return false; },
    async cancel(runId: string) {
      cancels.push(runId);
      for (let i = 0; i < 6; i++) await Promise.resolve();
      // Honest engine: the FIRST cancel of a run succeeds, a duplicate for the
      // same already-cancelled run is refused.
      return cancels.filter((id) => id === runId).length === 1;
    },
    async dispose() {},
  } as unknown as Parameters<typeof createRunController>[0]["engine"];

  const controller = createRunController({
    engine,
    time: createFakeTime(),
    onPublish: () => {},
  });

  const sent = controller.send("one");
  const [a, b] = await Promise.all([controller.stop(), controller.stop()]);
  assert.equal(a, true, "the first overlapping stop must report success");
  assert.equal(b, true, "the second overlapping stop must not read as a refusal");
  assert.equal(cancels.length, 1, "overlapping stops must ask the engine only once");
  await sent;
});

test("more than one refusal in a single drain all reach the transcript", async () => {
  // `drainDrops` accumulates: `next = noteDropped(next, ...)`. Restarting from
  // `state` each iteration keeps only the LAST refusal of a batch, and every
  // existing test drained exactly one at a time, so it could not tell. The
  // whole point of this channel is to make "this stream is 40% unparseable"
  // visible; keeping one of every N silently divides that by N.
  const sink = createDropSink();
  const engine = createScriptedEngine({ id: "s", script: SCRIPTS.happy });
  const views: RunView[] = [];

  const controller = createRunController({
    engine: {
      ...engine,
      async *run(req, signal) {
        let injected = false;
        for await (const event of engine.run(req, signal)) {
          if (event.type === "delta" && !injected) {
            injected = true;
            // THREE refusals between two decoded events -- one drain, three
            // notes. Every earlier test drained exactly one at a time.
            sink.note("unparseable_json", "one");
            sink.note("not_an_object", "two");
            sink.note("unknown_event", "three");
          }
          yield event;
        }
      },
    },
    time: createFakeTime(),
    dropSink: sink,
    onPublish: (v) => views.push(v),
  });

  await controller.send("hi");
  const dropped = views.at(-1)?.turn.dropped ?? [];
  assert.equal(dropped.length, 3, `only ${dropped.length} of 3 refusals survived the drain`);
  assert.deepEqual(dropped.map((d) => d.detail), ["one", "two", "three"], "and in order");
});

test("the engine's refusal to cancel is propagated, not rounded up to success", async () => {
  // `return stopped` -> `return true` survived. stopNotice in main.ts IS
  // tested, but nothing tested that the controller hands it the engine's real
  // answer -- so the entire "the engine did not accept the stop" announcement
  // was unreachable in practice, which is the defect that notice exists for.
  const controller = createRunController({
    engine: {
      ...createScriptedEngine({ id: "s", script: SCRIPTS.happy }),
      async cancel() {
        return false; // the engine refuses
      },
    },
    time: createFakeTime(),
    onPublish: () => {},
  });

  const sent = controller.send("one");
  assert.equal(await controller.stop(), false, "a refused cancel must not read as success");
  await sent;
});

test("an approval whose decide THROWS is shown as failed, not as accepted", async () => {
  // The `ok === false` path is tested; the throw path was not. Replacing the
  // catch's `reject` with `acknowledge` survived -- so a decision that blew up
  // in transit rendered as sent and accepted, against a command the engine
  // never received. Same shape as the refused-cancel defect, one layer over.
  const views: RunView[] = [];
  const engine = createScriptedEngine({
    id: "s",
    script: [
      { type: "start", msgId: "m", runId: "r" },
      { type: "approval_request", msgId: "m", approvalId: "ap1", callId: "c1", name: "rm", args: {} },
    ],
    approvals: ["ap1"],
  });

  const controller = createRunController({
    engine: {
      ...engine,
      async decide() {
        throw new Error("socket closed");
      },
    },
    time: createFakeTime(),
    onPublish: (v) => views.push(v),
  });

  await controller.send("go");
  await controller.decide("ap1", "deny");

  const entry = views.at(-1)?.approvals.entries.find((e) => e.approvalId === "ap1");
  assert.equal(entry?.state.status, "failed", "a decision that threw must not read as sent");
  assert.equal(
    entry?.state.status === "failed" ? entry.state.reason : null,
    "socket closed",
    "and must carry why, so the row can say so",
  );
});

test("the coalescer is built with maxBytes and maxDelayMs THE RIGHT WAY ROUND", async () => {
  // `createCoalescer(maxBytes, maxDelayMs)` takes two numbers, so transposing
  // them typechecks and survived the suite: frames would flush at 16 BYTES and
  // the delay bound would become 256ms. Both constants the coalescer's whole
  // module comment is about become arbitrary. Same-typed adjacent arguments
  // are the shape that has already produced one defect in this package.
  //
  // Observed rather than inspected: with a 256-byte cap and a 16ms budget, a
  // 40-character answer painted in one go must NOT be split into three frames.
  const deltas: RunEvent[] = Array.from({ length: 8 }, () => ({
    type: "delta", msgId: "m1", text: "12345",
  }));
  const views: RunView[] = [];
  const controller = createRunController({
    engine: createScriptedEngine({
      id: "s",
      script: [
        { type: "start", msgId: "m1", runId: "r1" },
        ...deltas,
        { type: "end", msgId: "m1", userIndex: 0, assistantIndex: 1, versions: 1, active: 0 },
      ],
    }),
    time: createFakeTime(),
    maxBytes: 256,
    maxDelayMs: 16,
    onPublish: (v) => views.push(v),
  });

  await controller.send("hi");

  // 40 characters is far below a 256-byte cap and no clock time passes, so the
  // only paint should be the terminal flush. Transposed, the cap is 16 bytes
  // and the answer breaks into several.
  const painted = views.filter((v) => v.turn.text !== "");
  assert.ok(
    painted.length <= 2,
    `40 chars under a 256-byte cap should not paint ${painted.length} times`,
  );
  assert.equal(views.at(-1)?.turn.text, "1234512345123451234512345123451234512345");
});

/** An engine whose turn stays open until `release()` is called, so a test can
 *  be sure a run is genuinely live when it presses Stop. Without this the
 *  scripted engine can finish first and `stop()` returns false for the boring
 *  reason, which passes a refusal test for entirely the wrong reason. */
function heldEngine(cancel: (runId: string) => Promise<boolean>) {
  let release: () => void = () => {};
  const held = new Promise<void>((r) => { release = r; });
  const engine = {
    id: "s",
    protocolVersion: PROTOCOL_VERSION,
    capabilities: {
      streaming: true, reasoning: false, tools: true,
      approvals: false, cancellation: true, attachments: false,
    },
    async *run(req: { runId: string }, signal: AbortSignal) {
      yield { type: "start", msgId: "m", runId: req.runId };
      await held;
      if (signal.aborted) return;
      yield { type: "end", msgId: "m", userIndex: 0, assistantIndex: 1, versions: 1, active: 0 };
    },
    async decide() { return false; },
    cancel,
    async dispose() {},
  } as unknown as Parameters<typeof createRunController>[0]["engine"];
  return { engine, release: () => release() };
}

test("a REFUSED stop can be retried, and does not report success on the retry", async () => {
  // The idempotence guard added two commits ago aborted the reader even when
  // the engine answered FALSE. That set `aborted`, so the next tap hit the
  // guard and returned true without asking the engine again -- and it detached
  // the reader from a run the engine said it had NOT cancelled, leaving it
  // generating and billing into a socket nobody drains.
  //
  // The user is told the stop was refused, taps the only affordance offered,
  // and is told nothing at all -- which stopNotice defines as success. The
  // defect that notice exists for, inverted, one layer down.
  const cancels: string[] = [];
  let refuse = true;
  const { engine, release } = heldEngine(async (runId) => {
    cancels.push(runId);
    if (refuse) { refuse = false; return false; }
    return true;
  });
  const controller = createRunController({ engine, time: createFakeTime(), onPublish: () => {} });

  const sent = controller.send("go");
  for (let i = 0; i < 5; i++) await Promise.resolve();

  assert.equal(await controller.stop(), false, "the engine refused this one");
  assert.equal(await controller.stop(), true, "the retry must actually reach the engine");
  assert.equal(cancels.length, 2, "a refused stop must not swallow the retry");

  release();
  await sent;
});

test("an ACCEPTED stop is still idempotent", async () => {
  // The pair, and the reason the guard exists: the documented background ->
  // dispose path calls stop() twice, and the second must not re-issue a cancel
  // the engine would rightly refuse.
  const cancels: string[] = [];
  const { engine, release } = heldEngine(async (runId) => {
    cancels.push(runId);
    return true;
  });
  const controller = createRunController({ engine, time: createFakeTime(), onPublish: () => {} });

  const sent = controller.send("go");
  for (let i = 0; i < 5; i++) await Promise.resolve();

  assert.equal(await controller.stop(), true);
  assert.equal(await controller.stop(), true);
  assert.equal(cancels.length, 1, "an accepted stop must not be asked twice");

  release();
  await sent;
});

// ---- the turn belongs to the turn, not to the app ---------------------------

/** An engine whose first run answers and whose later runs fail BEFORE `start`
 *  -- which is every pre-first-token failure: 401, 403, offline, a refused
 *  connection, a wrong baseUrl. */
function answerThenFail(kind: "auth" | "transport", message: string) {
  let n = 0;
  return {
    id: "s",
    protocolVersion: PROTOCOL_VERSION,
    capabilities: {
      streaming: true, reasoning: false, tools: true,
      approvals: true, cancellation: true, attachments: false,
    },
    async *run(req: { runId: string }) {
      n += 1;
      if (n === 1) {
        yield { type: "start", msgId: "m1", runId: req.runId };
        yield { type: "delta", msgId: "m1", text: "first answer" };
        yield { type: "end", msgId: "m1", userIndex: 0, assistantIndex: 1, versions: 1, active: 0 };
        return;
      }
      yield { type: "error", msgId: `m${n}`, kind, message };
    },
    async decide() { return false; },
    async cancel() { return false; },
    async dispose() {},
  } as unknown as Parameters<typeof createRunController>[0]["engine"];
}

test("a failure on the SECOND turn is reported, not silently swallowed", async () => {
  // `turn` was only ever reset by a `start` event, so a turn producing no
  // start met a state left `ended` by its predecessor: the error was dropped
  // as stale and `finish()` returned the PREVIOUS turn untouched.
  //
  // The user types a second question, taps Send, the composer clears -- and
  // nothing happens. The old answer stays on screen. No error, no retry, no
  // auth prompt, not even a hint a run was attempted. The default baseUrl is
  // 127.0.0.1:8765, so "engine unreachable" is the common case here.
  const views: RunView[] = [];
  const controller = createRunController({
    engine: answerThenFail("auth", "engine responded 401"),
    time: createFakeTime(),
    onPublish: (v) => views.push(v),
  });

  await controller.send("one");
  assert.equal(views.at(-1)?.turn.text, "first answer");

  await controller.send("two");
  const second = views.at(-1);
  assert.equal(second?.turn.text, "", "the previous answer must not still be on screen");
  assert.equal(second?.turn.outcome?.type, "error", "the failure must be reported");
  assert.equal(
    second?.turn.outcome?.type === "error" ? second.turn.outcome.kind : null,
    "auth",
    "and with its real kind, so the UI can offer credentials rather than retry",
  );
  assert.deepEqual(second?.turn.dropped, [], "a real failure is not an unreadable frame");
});

test("a clean turn after a failed one inherits nothing from it", async () => {
  // The other direction of the same reset, and the amplifier: the dropped
  // error landed in `carry`, so the next SUCCESSFUL turn rendered a "1 event
  // could not be read" row blaming itself for its predecessor.
  const views: RunView[] = [];
  let n = 0;
  const engine = {
    id: "s",
    protocolVersion: PROTOCOL_VERSION,
    capabilities: {
      streaming: true, reasoning: false, tools: true,
      approvals: true, cancellation: true, attachments: false,
    },
    async *run(req: { runId: string }) {
      n += 1;
      if (n === 1) {
        yield { type: "error", msgId: "m1", kind: "transport", message: "network down" };
        return;
      }
      yield { type: "start", msgId: `m${n}`, runId: req.runId };
      yield { type: "delta", msgId: `m${n}`, text: "second answer" };
      yield { type: "end", msgId: `m${n}`, userIndex: 0, assistantIndex: 1, versions: 1, active: 0 };
    },
    async decide() { return false; },
    async cancel() { return false; },
    async dispose() {},
  } as unknown as Parameters<typeof createRunController>[0]["engine"];

  const controller = createRunController({ engine, time: createFakeTime(), onPublish: (v) => views.push(v) });
  await controller.send("one");
  await controller.send("two");

  const second = views.at(-1);
  assert.equal(second?.turn.text, "second answer");
  assert.equal(second?.turn.outcome?.type, "end");
  assert.deepEqual(second?.turn.dropped, [], "a clean turn must not inherit the last one's failure");
});

test("switching chats clears the transcript, so nothing resurrects on the next send", async () => {
  // `send()` publishes before `runTurn` starts, so a stale turn was painted
  // into what the user believed was a new conversation. With a PENDING
  // APPROVAL in it, the previous chat's prompt reappeared with live buttons --
  // `setChat` had already cleared the approvals table, so the row found no
  // entry and rendered itself actionable, and Allow posted to the engine.
  //
  // The scenario is a user abandoning a chat BECAUSE it asked to run something
  // dangerous, and being asked again under an unrelated question.
  const views: RunView[] = [];
  const controller = createRunController({
    engine: createScriptedEngine({
      id: "s",
      script: [
        { type: "start", msgId: "m1", runId: "r1" },
        { type: "tool_call", msgId: "m1", callId: "c1", name: "bash", args: { command: "rm -rf /" } },
        { type: "approval_request", msgId: "m1", approvalId: "a1", callId: "c1", name: "bash", args: { command: "rm -rf /" } },
      ],
      approvals: ["a1"],
    }),
    time: createFakeTime(),
    onPublish: (v) => views.push(v),
  });

  await controller.send("do something");
  assert.ok((views.at(-1)?.turn.approvals.length ?? 0) > 0, "the approval should be outstanding");

  controller.setChat("a-different-chat");
  const afterSwitch = controller.view();
  assert.deepEqual(afterSwitch.turn.approvals, [], "a new chat must not inherit a pending approval");
  assert.equal(afterSwitch.turn.text, "", "nor the previous conversation's text");
});

test("a turn the USER stopped reads as cancelled, not as a connection failure", async () => {
  // The catch mapped every thrown iterator to `transport` without asking
  // whether the abort was ours. Stop cancels the engine, aborts the reader,
  // and a real fetch then errors the body stream -- so the deliberately
  // stopped turn rendered as a red "Connection lost" WITH A RETRY BUTTON, and
  // announced "Connection lost" to a screen reader.
  //
  // The `cancelled` outcome was reachable only if the engine's goodbye frame
  // won a race against our own abort, which it usually loses.
  const views: RunView[] = [];
  let release: () => void = () => {};

  const engine = {
    id: "s",
    protocolVersion: PROTOCOL_VERSION,
    capabilities: {
      streaming: true, reasoning: false, tools: true,
      approvals: false, cancellation: true, attachments: false,
    },
    async *run(req: { runId: string }, signal: AbortSignal) {
      yield { type: "start", msgId: "m1", runId: req.runId };
      yield { type: "delta", msgId: "m1", text: "the answer so far" };
      // Wait for OUR abort specifically, so the test is not racing it. A real
      // fetch behaves this way: the body stream errors when the reader is
      // aborted mid-response.
      await new Promise<void>((resolve) => {
        if (signal.aborted) return resolve();
        signal.addEventListener("abort", () => resolve(), { once: true });
      });
      throw new Error("aborted");
    },
    async decide() { return false; },
    async cancel() { release(); return true; },
    async dispose() {},
  } as unknown as Parameters<typeof createRunController>[0]["engine"];

  const controller = createRunController({ engine, time: createFakeTime(), onPublish: (v) => views.push(v) });
  const sent = controller.send("go");
  for (let i = 0; i < 5; i++) await Promise.resolve();
  await controller.stop();
  await sent;

  const final = views.at(-1);
  assert.equal(final?.turn.text, "the answer so far", "the text so far must survive a stop");
  assert.equal(
    final?.turn.outcome?.type,
    "cancelled",
    "a stop the user asked for must not render as a transport error with Retry",
  );
});

test("a stream that dies on its OWN is still a transport error", async () => {
  // The pair. Treating every throw as cancelled would hide real network
  // failures behind a calm "Stopped" and remove the retry the user needs.
  const views: RunView[] = [];
  const engine = {
    id: "s",
    protocolVersion: PROTOCOL_VERSION,
    capabilities: {
      streaming: true, reasoning: false, tools: true,
      approvals: false, cancellation: true, attachments: false,
    },
    async *run(req: { runId: string }) {
      yield { type: "start", msgId: "m1", runId: req.runId };
      yield { type: "delta", msgId: "m1", text: "partial" };
      throw new Error("socket reset by peer");
    },
    async decide() { return false; },
    async cancel() { return false; },
    async dispose() {},
  } as unknown as Parameters<typeof createRunController>[0]["engine"];

  const controller = createRunController({ engine, time: createFakeTime(), onPublish: (v) => views.push(v) });
  await controller.send("go");

  const final = views.at(-1);
  assert.equal(final?.turn.text, "partial");
  assert.equal(final?.turn.outcome?.type, "error");
  assert.equal(
    final?.turn.outcome?.type === "error" ? final.turn.outcome.kind : null,
    "transport",
    "a genuine network failure must still offer retry",
  );
});

test("an accepted stop DETACHES the reader, so nothing more paints", async () => {
  // `run.abort.abort()` deleted after a successful cancel survived. Stop
  // reports success, the reader is never detached, and the stream keeps
  // arriving and painting into a turn the user stopped -- so the answer goes
  // on growing after the button said it had stopped.
  const views: RunView[] = [];
  let releaseNext: () => void = () => {};
  const engine = {
    id: "s",
    protocolVersion: PROTOCOL_VERSION,
    capabilities: {
      streaming: true, reasoning: false, tools: true,
      approvals: false, cancellation: true, attachments: false,
    },
    async *run(req: { runId: string }, signal: AbortSignal) {
      yield { type: "start", msgId: "m1", runId: req.runId };
      yield { type: "delta", msgId: "m1", text: "before stop" };
      await new Promise<void>((resolve) => { releaseNext = resolve; });
      // A well-behaved engine checks; the point of the abort is that a
      // less careful one is stopped anyway by the reader detaching.
      if (signal.aborted) return;
      yield { type: "delta", msgId: "m1", text: " AFTER STOP" };
    },
    async decide() { return false; },
    async cancel() { return true; },
    async dispose() {},
  } as unknown as Parameters<typeof createRunController>[0]["engine"];

  const controller = createRunController({ engine, time: createFakeTime(), onPublish: (v) => views.push(v) });
  const sent = controller.send("go");
  for (let i = 0; i < 5; i++) await Promise.resolve();

  assert.equal(await controller.stop(), true);
  releaseNext();
  await sent;

  assert.equal(
    views.at(-1)?.turn.text.includes("AFTER STOP"),
    false,
    "text arrived after the user stopped the run",
  );
});
