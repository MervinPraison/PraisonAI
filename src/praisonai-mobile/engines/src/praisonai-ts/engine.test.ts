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

import {
  createPraisonTsEngine,
  PRAISONAI_TS_CAPABILITIES,
  type ConversationHistory,
  type RunPersistence,
} from "./engine.ts";
import type {
  PraisonAgent,
  PraisonAgentEvent,
  PraisonHistoryMessage,
  PraisonStopReason,
} from "./agent-api.ts";
import type { HistoryMessage } from "../../../core/src/chat/history.ts";
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

/**
 * What the agent was actually told, per turn.
 *
 * Recorded rather than asserted inline because the whole conversation-memory
 * question is "what reached the model", and a fake that only yields events can
 * answer questions about the OUTPUT of a turn and nothing about its input.
 */
interface AgentCalls {
  /** One entry per `setHistory` call, in order. A turn that never called it
   *  leaves the array shorter, which is what a dropped call looks like. */
  readonly histories: (readonly PraisonHistoryMessage[])[];
  /** The prompt string handed to `streamEvents`, per turn. */
  readonly prompts: string[];
}

/** A scripted PraisonAgent. `stop` is read only after the stream ends, exactly
 *  as the real field behaves. */
function fakeAgent(
  script: readonly PraisonAgentEvent[],
  stop: PraisonStopReason | null = "completed",
  onSignal?: (signal: AbortSignal | undefined) => void,
  calls?: AgentCalls,
): PraisonAgent {
  return {
    lastStopReason: stop,
    setHistory(messages) {
      // Copied: the engine hands over an array it built, and a test that held
      // the live reference would pass even if the engine later mutated it.
      calls?.histories.push(messages.map((m) => ({ ...m })));
    },
    async *streamEvents(prompt, opts) {
      calls?.prompts.push(prompt);
      onSignal?.(opts?.signal);
      for (const event of script) {
        if (opts?.signal?.aborted) return;
        yield event;
      }
    },
  };
}

const noCalls = (): AgentCalls => ({ histories: [], prompts: [] });

/** A fixed conversation, as the session would report it. */
const historyOf = (...messages: readonly HistoryMessage[]): ConversationHistory => ({
  messages: () => messages,
});

const NO_HISTORY: ConversationHistory = { messages: () => [] };

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

const build = (
  agent: PraisonAgent,
  p: RunPersistence = persistence(),
  history: ConversationHistory = NO_HISTORY,
  historyBudget?: number,
) => {
  let n = 0;
  return createPraisonTsEngine({
    createAgent: () => agent,
    persistence: p,
    history,
    newMsgId: () => `m${++n}`,
    ...(historyBudget === undefined ? {} : { historyBudget }),
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

// ---- what is WRITTEN, not only what is streamed -----------------------------
//
// The fake persistence above records `req` and throws the answer away, so no
// test in this file could see what actually reaches the repository. A mutation
// sweep found the consequence: `answer = event.text` -> `+=` survived. The
// screen is built from the streamed deltas and looks right; the PERSISTED
// transcript contains the answer twice. Reopening the chat shows it doubled.

/** A persistence that keeps the answer, which the one above does not. */
function capturing() {
  const writes: { prompt: string; answer: string }[] = [];
  const port: RunPersistence = {
    async record(req, answer) {
      writes.push({ prompt: req.prompt, answer });
      return { userIndex: 0, assistantIndex: 1, versions: 1, active: 0 };
    },
  };
  return { writes, port };
}

const runAll = async (engine: ReturnType<typeof build>): Promise<void> => {
  for await (const _ of engine.run(
    { prompt: "hi", chatId: "c1", runId: "r1", tools: true, regenerateOf: null, attachments: [] },
    new AbortController().signal,
  )) {
    // drain
  }
};

test("the finish text REPLACES the streamed accumulation when persisting", async () => {
  // `finish` carries the full text and the engine trusts it over the
  // accumulation, because upstream may normalise. Appending instead writes the
  // answer twice to disk while the screen, built from the deltas, looks
  // perfectly correct.
  const p = capturing();
  await runAll(
    build(
      fakeAgent([
        { type: "text", delta: "Hello" },
        { type: "text", delta: " world" },
        { type: "finish", text: "Hello world" },
      ]),
      p.port,
    ),
  );
  assert.deepEqual(p.writes.map((w) => w.answer), ["Hello world"]);
});

test("a normalising finish wins over what was streamed", async () => {
  // The reason the assignment exists at all: upstream may return a tidied
  // version. Persisting the concatenation would store text the model did not
  // finally say.
  const p = capturing();
  await runAll(
    build(
      fakeAgent([
        { type: "text", delta: "helo" },
        { type: "finish", text: "hello" },
      ]),
      p.port,
    ),
  );
  assert.deepEqual(p.writes.map((w) => w.answer), ["hello"]);
});

test("a turn that never streamed still persists the text it finished with", async () => {
  // The other half of trusting `finish`: a non-streaming provider produces no
  // deltas at all, and the accumulation would be empty.
  const p = capturing();
  await runAll(build(fakeAgent([{ type: "finish", text: "the whole answer" }]), p.port));
  assert.deepEqual(p.writes.map((w) => w.answer), ["the whole answer"]);
});

test("with no finish event, the streamed deltas are what gets persisted", async () => {
  // The pair. Trusting only `finish` would persist nothing for a provider
  // that streams and then simply stops.
  const p = capturing();
  await runAll(
    build(fakeAgent([{ type: "text", delta: "one " }, { type: "text", delta: "two" }]), p.port),
  );
  assert.deepEqual(p.writes.map((w) => w.answer), ["one two"]);
});

test("a run started with an ALREADY-aborted signal produces no answer", async () => {
  // `if (signal.aborted) controller.abort()` -> `if (false)` survived. The
  // `else` branch's `addEventListener("abort")` never fires for a signal that
  // aborted BEFORE the listener was attached, so the run streams to completion
  // and persists an answer nobody is waiting for.
  //
  // Reachable through dispose-then-new-run, and through Stop followed
  // immediately by Send: the controller hands the engine a signal that is
  // already down.
  const p = capturing();
  const engine = build(
    fakeAgent([
      { type: "text", delta: "this should never be streamed" },
      { type: "finish", text: "nor persisted" },
    ]),
    p.port,
  );

  const controller = new AbortController();
  controller.abort(); // down BEFORE the run starts

  const events = [];
  for await (const event of engine.run(
    { prompt: "hi", chatId: "c1", runId: "r1", tools: true, regenerateOf: null, attachments: [] },
    controller.signal,
  )) {
    events.push(event);
  }

  assert.equal(
    events.some((e) => e.type === "delta"),
    false,
    `an already-aborted run streamed: ${events.map((e) => e.type).join(", ")}`,
  );
  assert.deepEqual(p.writes, [], "and it must not have persisted an answer");
});

test("a run with a live signal still streams, so the abort test is not vacuous", async () => {
  const p = capturing();
  const engine = build(fakeAgent([{ type: "text", delta: "kept" }, { type: "finish", text: "kept" }]), p.port);
  const events = [];
  for await (const event of engine.run(
    { prompt: "hi", chatId: "c1", runId: "r1", tools: true, regenerateOf: null, attachments: [] },
    new AbortController().signal,
  )) {
    events.push(event);
  }
  assert.ok(events.some((e) => e.type === "delta"));
  assert.deepEqual(p.writes.map((w) => w.answer), ["kept"]);
});

// ---- conversation memory ---------------------------------------------------
//
// The engine sent `request.prompt` and only `request.prompt`, so the app stored
// a conversation, rendered it, and showed the model none of it. Measured on a
// device: "What is the capital of France?" -> "Paris", then "And its
// population?" -> a request for clarification. These cases are the gates on
// that, and each one is written to die under a specific way of half-doing it.

test("the prior conversation is restored onto the agent before the prompt is sent", async () => {
  // The whole defect in one assertion. Removing the `setHistory` call -- the
  // state this file was written against -- leaves `histories` empty here.
  const calls = noCalls();
  const engine = build(
    fakeAgent([{ type: "finish", text: "About 2.1 million." }], "completed", undefined, calls),
    persistence(),
    historyOf(
      { role: "user", content: "What is the capital of France?" },
      { role: "assistant", content: "Paris." },
    ),
  );

  await collect(engine, new AbortController().signal, request({ prompt: "And its population?" }));

  assert.equal(calls.histories.length, 1, "setHistory must be called exactly once per turn");
  assert.deepEqual(calls.histories[0], [
    { role: "user", content: "What is the capital of France?" },
    { role: "assistant", content: "Paris." },
  ]);
});

test("the restored conversation keeps its ORDER, oldest first", async () => {
  // Reversing the array is the cheapest way to look like this works while
  // handing the model a conversation that runs backwards -- the answer before
  // the question, the follow-up before what it follows.
  const calls = noCalls();
  const engine = build(
    fakeAgent([{ type: "finish", text: "ok" }], "completed", undefined, calls),
    persistence(),
    historyOf(
      { role: "user", content: "first" },
      { role: "assistant", content: "second" },
      { role: "user", content: "third" },
      { role: "assistant", content: "fourth" },
    ),
  );

  await collect(engine);

  assert.deepEqual(
    calls.histories[0]?.map((m) => m.content),
    ["first", "second", "third", "fourth"],
    "history must arrive in the order it was said",
  );
});

test("the restored conversation keeps its ROLES", async () => {
  // A history whose roles are all "user" reads to the model as one person
  // talking to themselves, and it will happily answer a question it already
  // answered. Content-only assertions cannot see this.
  const calls = noCalls();
  const engine = build(
    fakeAgent([{ type: "finish", text: "ok" }], "completed", undefined, calls),
    persistence(),
    historyOf(
      { role: "user", content: "q1" },
      { role: "assistant", content: "a1" },
      { role: "user", content: "q2" },
      { role: "assistant", content: "a2" },
    ),
  );

  await collect(engine);

  assert.deepEqual(
    calls.histories[0]?.map((m) => m.role),
    ["user", "assistant", "user", "assistant"],
  );
});

test("the prompt of the turn being run is NOT also in its history", async () => {
  // The other half of the seam. `session.record` writes a turn only after it
  // succeeds, so the live prompt is genuinely absent from the store -- but an
  // engine that appended `request.prompt` to the history "to be safe" would
  // ask the model the same question twice in one request, and the passing
  // tests above would not notice.
  const calls = noCalls();
  const engine = build(
    fakeAgent([{ type: "finish", text: "ok" }], "completed", undefined, calls),
    persistence(),
    historyOf({ role: "user", content: "earlier" }, { role: "assistant", content: "reply" }),
  );

  await collect(engine, new AbortController().signal, request({ prompt: "the live question" }));

  assert.deepEqual(calls.prompts, ["the live question"], "the prompt still travels as the prompt");
  assert.equal(
    calls.histories[0]?.some((m) => m.content === "the live question"),
    false,
    "the live prompt must not also appear in the history",
  );
});

test("history is read PER TURN, so a turn sees what the turn before it recorded", async () => {
  // The engine is built once and held for the session, so a history captured
  // at construction would freeze at whatever was on disk when the app booted --
  // which for a fresh launch is the empty conversation, and for a reopened one
  // is correct until the first reply and wrong forever after.
  const calls = noCalls();
  const conversation: HistoryMessage[] = [];
  const engine = build(
    fakeAgent([{ type: "finish", text: "an answer" }], "completed", undefined, calls),
    persistence(),
    { messages: () => conversation },
  );

  await collect(engine, new AbortController().signal, request({ prompt: "one", runId: "r1" }));
  conversation.push({ role: "user", content: "one" }, { role: "assistant", content: "an answer" });
  await collect(engine, new AbortController().signal, request({ prompt: "two", runId: "r2" }));

  assert.deepEqual(calls.histories[0], [], "the first turn has nothing to remember");
  assert.deepEqual(calls.histories[1], [
    { role: "user", content: "one" },
    { role: "assistant", content: "an answer" },
  ]);
});

test("a first turn calls setHistory with an empty conversation rather than skipping it", async () => {
  // Unconditional on purpose: a guard would make the first turn of every
  // conversation the one path that does not go through the restore, and that
  // is the path least likely to be exercised by any other test here.
  const calls = noCalls();
  const engine = build(
    fakeAgent([{ type: "finish", text: "hi" }], "completed", undefined, calls),
  );

  await collect(engine);

  assert.deepEqual(calls.histories, [[]]);
});

test("history over the budget is truncated to the RECENT end, not the oldest", async () => {
  // The turn must still run. Letting the provider answer "what happens when
  // the context is full" means a 400 mid-answer with no way forward.
  const calls = noCalls();
  const engine = build(
    fakeAgent([{ type: "finish", text: "ok" }], "completed", undefined, calls),
    persistence(),
    historyOf(
      { role: "user", content: "aaaa" },
      { role: "assistant", content: "bbbb" },
      { role: "user", content: "cccc" },
      { role: "assistant", content: "dddd" },
    ),
    8, // room for the last two messages only
  );

  const events = await collect(engine);

  assert.deepEqual(calls.histories[0]?.map((m) => m.content), ["cccc", "dddd"]);
  assert.equal(events.at(-1)?.type, "end", "a truncated history must not fail the turn");
});
