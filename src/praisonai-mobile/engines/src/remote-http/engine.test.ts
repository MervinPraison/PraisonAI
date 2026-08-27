/**
 * The remote-HTTP engine, driven through the full conformance suite over a
 * fake HttpPort.
 *
 * This is the moment the seam stops being a claim. The scripted fake and this
 * engine share no code -- one replays an array, the other parses SSE frames off
 * a byte stream -- and both are held to the same 20-odd contract cases. An
 * interface with one implementation is an interface shaped around that
 * implementation; this is the second, and it is the one that talks to a real
 * server.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { describeEngineContract, type ScenarioName } from "../conformance.ts";
import { createRemoteHttpEngine, probeHealth } from "./engine.ts";
import { createFakeHttp, sseResponse, jsonResponse } from "../../../testing/src/fake-http.ts";
import { SCRIPTS } from "../../../testing/src/scripts.ts";
import { encodeSseFrame } from "../../../protocol/src/encode.ts";
import { PROTOCOL_VERSION } from "../../../protocol/src/version.ts";
import type { RunEvent } from "../../../protocol/src/events.ts";

const BASE = "http://engine.test:8000";

/** Encode a script as the SSE bytes a real engine would write. */
const framesFor = (script: readonly RunEvent[]): string =>
  script.map(encodeSseFrame).join("");

/**
 * Build an engine wired to a fake server serving `scenario`.
 *
 * The approval and cancel endpoints answer honestly: only ids that appear in
 * the scenario's script are accepted, so `deciding an unknown approval returns
 * false` is a real behaviour rather than a hardcoded false.
 */
function engineFor(scenario: ScenarioName) {
  const http = createFakeHttp();
  const script = SCRIPTS[scenario];

  const knownApprovals = new Set(
    script.filter((e) => e.type === "approval_request").map((e) => e.approvalId),
  );
  const liveRuns = new Set<string>();

  http.on("/chat", () => {
    liveRuns.add("r1");
    return sseResponse(framesFor(script));
  });
  http.on("/health", () => jsonResponse(200, { ok: true, version: PROTOCOL_VERSION }));

  // The engine builds the path itself, so match on the prefix segment.
  for (const id of knownApprovals) {
    http.on(`/approve/${id}`, () => {
      const first = knownApprovals.has(id);
      knownApprovals.delete(id);
      return jsonResponse(200, { ok: first });
    });
  }
  http.on("/cancel/r1", () => {
    const live = liveRuns.has("r1");
    liveRuns.delete("r1");
    return jsonResponse(200, { ok: live });
  });

  return { http, engine: createRemoteHttpEngine({ baseUrl: BASE, http }) };
}

describeEngineContract({
  name: "remote-http",
  async create(scenario) {
    return engineFor(scenario).engine;
  },
});

// ---- behaviour specific to this transport ---------------------------------

test("remote-http: a frame split across chunk boundaries is still decoded", async () => {
  // The fake streams in 7-byte chunks, so every scenario above already exercises
  // this -- but assert it directly, because a stateless SSE split would lose the
  // tail of most frames on a real network and the failure would look like a
  // flaky model rather than a parser bug.
  const { engine } = engineFor("happy");
  const events: RunEvent[] = [];
  for await (const event of engine.run(
    { prompt: "hi", chatId: "c1", runId: "r1", tools: true, regenerateOf: null, attachments: [] },
    new AbortController().signal,
  )) {
    events.push(event);
  }
  assert.equal(events[0]?.type, "start");
  assert.equal(events.filter((e) => e.type === "delta").length, 2);
});

test("remote-http: a 401 surfaces as an auth error rather than a transport failure", async () => {
  // The UI offers different recovery for each: settings for one, retry for the
  // other. Collapsing them sends the user to the wrong place.
  const http = createFakeHttp();
  http.on("/chat", () => jsonResponse(401, { error: "bad key" }));
  const engine = createRemoteHttpEngine({ baseUrl: BASE, http });

  const events: RunEvent[] = [];
  for await (const event of engine.run(
    { prompt: "hi", chatId: "c1", runId: "r1", tools: true, regenerateOf: null, attachments: [] },
    new AbortController().signal,
  )) {
    events.push(event);
  }
  assert.equal(events[0]?.type, "error");
  assert.equal(events[0]?.type === "error" && events[0].kind, "auth");
});

test("remote-http: a bearer token is sent when configured and omitted when not", async () => {
  // The desktop engine is unauthenticated on loopback. Anything off-device must
  // not be, and a token that is silently dropped is worse than no token.
  const withToken = createFakeHttp();
  withToken.on("/chat", () => sseResponse(framesFor(SCRIPTS.happy)));
  const authed = createRemoteHttpEngine({ baseUrl: BASE, http: withToken, token: "s3cret" });
  for await (const _ of authed.run(
    { prompt: "hi", chatId: "c1", runId: "r1", tools: true, regenerateOf: null, attachments: [] },
    new AbortController().signal,
  )) { /* drain */ }
  assert.equal(withToken.sent[0]?.headers["authorization"], "Bearer s3cret");

  const noToken = createFakeHttp();
  noToken.on("/chat", () => sseResponse(framesFor(SCRIPTS.happy)));
  const anon = createRemoteHttpEngine({ baseUrl: BASE, http: noToken });
  for await (const _ of anon.run(
    { prompt: "hi", chatId: "c1", runId: "r1", tools: true, regenerateOf: null, attachments: [] },
    new AbortController().signal,
  )) { /* drain */ }
  assert.equal(noToken.sent[0]?.headers["authorization"], undefined);
});

test("remote-http: probeHealth refuses an engine that answers 200 with ok false", async () => {
  const http = createFakeHttp();
  http.on("/health", () => jsonResponse(200, { ok: false, version: PROTOCOL_VERSION }));
  const verdict = await probeHealth(http, BASE);
  assert.equal(verdict.ready, false);
  assert.equal(verdict.ready === false && verdict.reason, "unhealthy");
});

test("remote-http: probeHealth accepts a healthy engine", async () => {
  // The pair, so "always refuse" cannot pass the test above.
  const http = createFakeHttp();
  http.on("/health", () => jsonResponse(200, { ok: true, version: PROTOCOL_VERSION }));
  const verdict = await probeHealth(http, BASE);
  assert.equal(verdict.ready, true);
});

test("remote-http: an unreachable engine is a retryable transport failure, not a crash", async () => {
  const http = createFakeHttp();
  http.on("/health", () => {
    throw new Error("ECONNREFUSED");
  });
  const verdict = await probeHealth(http, BASE);
  assert.equal(verdict.ready, false);
  assert.equal(verdict.ready === false && verdict.reason, "transport");
  assert.equal(verdict.ready === false && verdict.retryable, true);
});
