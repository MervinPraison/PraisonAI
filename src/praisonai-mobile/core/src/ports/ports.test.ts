/**
 * The ports are types, so the thing worth asserting is that each one can
 * actually be implemented.
 *
 * An interface nobody has implemented is a design sketch: it is easy to write
 * one that cannot be satisfied on a real platform, or that a fake can only
 * satisfy by lying. Writing a minimal implementation of each here means the
 * typecheck fails at the port rather than three weeks later inside an adapter.
 *
 * These are deliberately NOT the fakes -- testing/src/ owns those, and they
 * carry behaviour. These are the smallest thing the compiler will accept.
 */
import test from "node:test";
import assert from "node:assert/strict";

import type {
  AgentEnginePort,
  HttpPort,
  SecretsPort,
  ShellPort,
  StoragePort,
  TimePort,
} from "./index.ts";
import { UnsupportedCapabilityError } from "./index.ts";
import type { RunEvent } from "../../../protocol/src/events.ts";

test("the agent engine port is implementable", () => {
  const engine: AgentEnginePort = {
    id: "minimal",
    protocolVersion: 2,
    capabilities: {
      streaming: true,
      reasoning: false,
      tools: false,
      approvals: false,
      cancellation: true,
      attachments: false,
    },
    // eslint-disable-next-line require-yield
    async *run(): AsyncIterable<RunEvent> {
      return;
    },
    async decide() {
      return false;
    },
    async cancel() {
      return false;
    },
    async dispose() {},
  };
  assert.equal(engine.id, "minimal");
  assert.equal(engine.capabilities.approvals, false);
});

test("the shell port is implementable", () => {
  const noop = () => () => {};
  const shell: ShellPort = {
    kind: "fake",
    insets: { top: 0, right: 0, bottom: 0, left: 0 },
    keyboardHeightPx: 0,
    onInsetsChanged: noop,
    onKeyboardHeightChanged: noop,
    onLifecycleChanged: noop,
    onBackGesture: noop,
    haptic() {},
    async share() {},
    async openExternal() {},
  };
  // The insets snapshot is synchronous by design: first paint must place the
  // composer above the home indicator without awaiting anything.
  assert.equal(typeof shell.insets.bottom, "number");
});

test("the storage port is implementable", () => {
  const store: StoragePort = {
    async read() {
      return null;
    },
    async write() {},
    async remove() {},
    async listIds() {
      return [];
    },
    async clear() {},
  };
  assert.equal(typeof store.read, "function");
});

test("the secrets port is implementable and declares whether it is hardware backed", () => {
  const secrets: SecretsPort = {
    async has() {
      return false;
    },
    async get() {
      return null;
    },
    async set() {},
    async delete() {},
    isHardwareBacked: false,
  };
  // A port that could not express "not hardware backed" would force the web
  // adapter to imply a safety it does not provide.
  assert.equal(secrets.isHardwareBacked, false);
});

test("the http port is implementable and declares whether it sends natively", () => {
  const http: HttpPort = {
    async send() {
      return { status: 204, headers: {}, body: null };
    },
    sendsFromNative: false,
  };
  assert.equal(http.sendsFromNative, false);
});

test("the time port is implementable and hands out one scheduler per call", () => {
  const time: TimePort = {
    nowMs: () => 0,
    epochMs: () => 0,
    createScheduler: () => ({
      requestFrame() {},
      setTimer() {},
      clearTimer() {},
    }),
    every: () => () => {},
  };
  // A factory, not a singleton: stream-pacing.ts requires one gate per run,
  // because "reusing a gate across runs carries a closed gate into a new
  // answer and drops its opening tokens".
  assert.notEqual(time.createScheduler(), time.createScheduler());
});

test("UnsupportedCapabilityError names the engine and the capability", () => {
  const err = new UnsupportedCapabilityError("remote-http", "approvals");
  assert.equal(err.engineId, "remote-http");
  assert.equal(err.capability, "approvals");
  assert.match(err.message, /remote-http/);
  assert.match(err.message, /approvals/);
  // Constructed rather than inspected, so this fails if the class is ever
  // rewritten with parameter properties -- which type stripping cannot emit.
  assert.ok(err instanceof Error);
});
