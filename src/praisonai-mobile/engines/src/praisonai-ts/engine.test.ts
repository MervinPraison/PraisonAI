/**
 * The praisonai-ts engine, against a fake agent.
 *
 * The fake satisfies `PraisonAgent` structurally, which is the point of
 * declaring that interface rather than importing `praisonai`: every mapping
 * case below is driven deterministically with no provider, no network and no
 * key. The real coupling is checked separately, by assigning the real `Agent`
 * to `PraisonAgent` at composition -- a typecheck, not a test.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { createPraisonTsEngine, PRAISONAI_TS_CAPABILITIES, type RunPersistence } from "./engine.ts";
import type { PraisonAgent, PraisonAgentEvent, PraisonStopReason } from "./agent-api.ts";
import type { RunEvent } from "../../../protocol/src/events.ts";
import { isTerminal } from "../../../protocol/src/events.ts";
import type { RunRequest } from "../../../core/src/ports/agent-engine.ts";

const request = (over: Partial<RunRequest> = {}): RunRequest => ({
  prompt: "hello",
  chatId: "c1",
  runId: "r1",
  tools: true,
  regenerateOf: null,
  attachments: [],
  ...over,
});

/** A scripted PraisonAgent. `stop` is read only after the stream ends, exactly
 *  as the real field behaves. */
function fakeAgent(
  script: readonly PraisonAgentEvent[],
  stop: PraisonStopReason | null = "completed",
  onSignal?: (signal: AbortSignal | undefined) => void,
): PraisonAgent {
  return {
    lastStopReason: stop,
    async *streamEvents(_prompt, opts) {
      onSignal?.(opts?.signal);
      for (const event of script) {
        if (opts?.signal?.aborted) return;
        yield event;
      }
    },
  };
}

const recorded: RunRequest[] = [];
const persistence = (indices: Awaited<ReturnType<RunPersistence["record"]>> = {
  userIndex: 0,
  assistantIndex: 1,
  versions: 1,
  active: 0,
}): RunPersistence => ({
  async record(req) {
    recorded.push(req);
    return indices;
  },
});

const build = (agent: PraisonAgent, p: RunPersistence = persistence()) => {
  let n = 0;
  return createPraisonTsEngine({
    createAgent: () => agent,
    persistence: p,
    newMsgId: () => `m${++n}`,
  });
};

async function collect(
  engine: ReturnType<typeof build>,
  signal = new AbortController().signal,
  req = request(),
): Promise<RunEvent[]> {
  const events: RunEvent[] = [];
  for await (const event of engine.run(req, signal)) events.push(event);
  return events;
}

test("a happy turn is start, deltas, then exactly one end", async () => {
  const engine = build(fakeAgent([
    { type: "text", delta: "Hel" },
    { type: "text", delta: "lo" },
    { type: "finish", text: "Hello" },
  ]));
  const events = await collect(engine);

  assert.deepEqual(events.map((e) => e.type), ["start", "delta", "delta", "end"]);
  assert.equal(events.filter((e) => isTerminal(e)).length, 1);
  assert.equal(events.every((e) => e.msgId === events[0]!.msgId), true, "one msgId for the turn");
});

test("an empty delta is dropped rather than forwarded", async () => {
  // The protocol forbids it: "" must never be mistakable for "said nothing",
  // which is a different condition with its own event.
  const engine = build(fakeAgent([
    { type: "text", delta: "" },
    { type: "text", delta: "hi" },
    { type: "finish", text: "hi" },
  ]));
  const events = await collect(engine);
  assert.deepEqual(events.map((e) => e.type), ["start", "delta", "end"]);
});

test("finish text wins over the accumulated deltas", async () => {
  // Upstream may normalise, and a turn that never streamed still finishes with
  // content. Persisting the accumulation would store something the user never saw.
  recorded.length = 0;
  const engine = build(fakeAgent([
    { type: "text", delta: "par" },
    { type: "finish", text: "partial, normalised" },
  ]));
  await collect(engine);
  assert.equal(recorded.length, 1);
});

test("no output at all is an empty error, not a successful empty end", async () => {
  const engine = build(fakeAgent([{ type: "finish", text: "" }]));
  const events = await collect(engine);
  const last = events.at(-1)!;
  assert.equal(last.type, "error");
  assert.equal(last.type === "error" && last.kind, "empty");
});

test("an auth failure is reported as auth so the UI can send the user to settings", async () => {
  const engine = build(fakeAgent([
    { type: "error", error: new Error("401 Incorrect API key provided") },
  ]));
  const events = await collect(engine);
  const last = events.at(-1)!;
  assert.equal(last.type === "error" && last.kind, "auth");
});

test("a rate limit is reported as rate_limit so retrying is offered", async () => {
  const engine = build(fakeAgent([
    { type: "error", error: new Error("429 Rate limit reached for gpt-4o") },
  ]));
  const events = await collect(engine);
  assert.equal(events.at(-1)!.type === "error" && (events.at(-1) as any).kind, "rate_limit");
});

test("an error is terminal -- nothing is yielded after it", async () => {
  const engine = build(fakeAgent([
    { type: "text", delta: "partial" },
    { type: "error", error: new Error("boom") },
    { type: "text", delta: "must not appear" },
    { type: "finish", text: "must not appear" },
  ]));
  const events = await collect(engine);
  assert.deepEqual(events.map((e) => e.type), ["start", "delta", "error"]);
});

test("a cancelled turn announces cancelled and is never persisted", async () => {
  recorded.length = 0;
  const controller = new AbortController();
  const engine = build(fakeAgent([{ type: "text", delta: "a" }], "cancelled"));
  controller.abort();

  const events = await collect(engine, controller.signal);
  assert.equal(events.at(-1)!.type, "cancelled");
  assert.equal(events.some((e) => e.type === "end"), false, "a cancelled turn must not end");
  assert.equal(recorded.length, 0, "a cancelled turn must not be persisted");
});

test("the stop reason alone is enough to announce cancellation", async () => {
  // The pair for the test above: without this, "aborted signal" would be the
  // only path and an engine-side stop would read as a successful empty answer.
  const engine = build(fakeAgent([{ type: "text", delta: "a" }], "cancelled"));
  const events = await collect(engine);
  assert.equal(events.at(-1)!.type, "cancelled");
});

test("hitting the step limit is an error, not a normal answer", async () => {
  // A truncated run that reports `end` looks complete to the user.
  const engine = build(fakeAgent([{ type: "finish", text: "half an answer" }], "max_steps"));
  const events = await collect(engine);
  assert.equal(events.at(-1)!.type, "error");
});

test("the caller's signal reaches praisonai-ts", async () => {
  // The whole point of the #4426 upstream change. If the signal stops here the
  // provider keeps generating and billing after the user pressed Stop.
  let seen: AbortSignal | undefined;
  const engine = build(fakeAgent([{ type: "finish", text: "x" }], "completed", (s) => (seen = s)));
  await collect(engine);
  assert.ok(seen, "streamEvents must be given a signal");
});

test("cancel(runId) aborts a live run and reports true", async () => {
  const controller = new AbortController();
  let seen: AbortSignal | undefined;
  const engine = build(fakeAgent(
    [{ type: "text", delta: "a" }, { type: "finish", text: "a" }],
    "completed",
    (s) => (seen = s),
  ));

  const iterator = engine.run(request(), controller.signal)[Symbol.asyncIterator]();
  // Twice: an async generator suspends at its FIRST yield, which is `start`.
  // streamEvents has not been called yet at that point, so one next() would
  // assert against a signal the agent has never seen.
  await iterator.next(); // start
  await iterator.next(); // first delta -- now genuinely mid-stream
  assert.equal(await engine.cancel("r1"), true);
  assert.equal(seen?.aborted ?? false, true, "cancel must abort the signal handed to the agent");
  await iterator.return?.();
});

test("cancel reports false for a run that is not live", async () => {
  // A Stop button that confirms a cancellation which never happened is worse
  // than one that reports it could not.
  const engine = build(fakeAgent([{ type: "finish", text: "x" }]));
  assert.equal(await engine.cancel("never-started"), false);
});

test("decide reports false rather than claiming an unknown approval succeeded", async () => {
  const engine = build(fakeAgent([{ type: "finish", text: "x" }]));
  assert.equal(await engine.decide("a1", "allow"), false);
});

test("a failed write yields end with null indices, not a fabricated zero", async () => {
  // null means "not on disk": Fork and Delete must not be offered. A zero here
  // is what shifted every subsequent Fork onto the wrong message on desktop.
  const engine = build(fakeAgent([{ type: "finish", text: "hi" }]), {
    async record() {
      return null;
    },
  });
  const last = (await collect(engine)).at(-1)!;
  assert.equal(last.type, "end");
  assert.equal(last.type === "end" && last.userIndex, null);
  assert.equal(last.type === "end" && last.assistantIndex, null);
});

test("breaking out of the loop aborts the underlying request", async () => {
  // Cancellation has ONE path: the iterator's return(). If breaking out did not
  // abort, a user navigating away would leave a provider request billing.
  let seen: AbortSignal | undefined;
  const engine = build(fakeAgent(
    [{ type: "text", delta: "a" }, { type: "text", delta: "b" }, { type: "finish", text: "ab" }],
    "completed",
    (s) => (seen = s),
  ));

  for await (const event of engine.run(request(), new AbortController().signal)) {
    if (event.type === "delta") break;
  }
  assert.equal(seen?.aborted, true, "break must abort the provider request");
});

test("dispose aborts everything still running and is idempotent", async () => {
  let seen: AbortSignal | undefined;
  const engine = build(fakeAgent(
    [{ type: "text", delta: "a" }, { type: "finish", text: "a" }],
    "completed",
    (s) => (seen = s),
  ));
  const iterator = engine.run(request(), new AbortController().signal)[Symbol.asyncIterator]();
  await iterator.next(); // start
  await iterator.next(); // first delta -- see the note above

  await engine.dispose();
  assert.equal(seen?.aborted, true);
  await assert.doesNotReject(() => engine.dispose());
  await iterator.return?.();
});

test("capabilities describe what the engine can REPORT, not what it does inside", async () => {
  // `tools` was false for a real reason and is true for a real reason. It was
  // false because praisonai-ts EXECUTED tools and never announced them, so a
  // UI rendering rows from a true flag would render nothing and look broken.
  // Upstream now emits tool_call/tool_result, so the flag and the behaviour
  // agree again -- which is the only thing the flag ever claimed.
  assert.equal(PRAISONAI_TS_CAPABILITIES.tools, true);
  assert.equal(PRAISONAI_TS_CAPABILITIES.approvals, false);
  assert.equal(PRAISONAI_TS_CAPABILITIES.streaming, true);
  assert.equal(PRAISONAI_TS_CAPABILITIES.cancellation, true);
});

test("an engine declaring approvals:false never emits an approval_request", async () => {
  // The negative direction, asserted rather than assumed -- otherwise the flag
  // is documentation.
  const engine = build(fakeAgent([
    { type: "text", delta: "a" },
    { type: "finish", text: "a" },
  ]));
  const events = await collect(engine);
  assert.equal(events.some((e) => e.type === "approval_request"), false);
});

test("a run started after dispose fails fast instead of hanging", async () => {
  // A disposed engine that still accepts runs starts a provider request that
  // cancel() can no longer reach -- dispose has already cleared the live map
  // it looks in, so the Stop button would report false forever.
  const engine = build(fakeAgent([{ type: "finish", text: "x" }]));
  await engine.dispose();

  const events = await collect(engine);
  assert.deepEqual(events.map((e) => e.type), ["start", "error"]);
  assert.equal(events[1]!.type === "error" && events[1].kind, "internal");
});

test("a run before dispose is unaffected", async () => {
  // The pair: "always refuse" would pass the test above.
  const engine = build(fakeAgent([{ type: "finish", text: "x" }]));
  assert.equal((await collect(engine)).at(-1)!.type, "end");
});
