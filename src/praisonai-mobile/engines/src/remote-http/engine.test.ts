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

// ---- frames the decoder refuses ---------------------------------------------

test("a malformed frame is reported, not silently dropped", async () => {
  // This engine is the ONLY production caller of decodeEvent, and it did
  // `if (isDecoded(outcome)) yield` -- discarding every rejection. So a
  // `tool_result` frame missing its `ok` made the tool disappear and the turn
  // rendered as a clean answer, while the reducer's Dropped type, the view
  // model's dropped row and seven user-facing strings sat unreachable.
  const http = createFakeHttp();
  const refused: { reason: string; detail: string }[] = [];

  http.on("/chat", () =>
    sseResponse(
      [
        `event: start\ndata: ${JSON.stringify({ msg_id: "m1", run_id: "r1" })}\n\n`,
        `event: delta\ndata: ${JSON.stringify({ msg_id: "m1", text: "hello" })}\n\n`,
        // Refused: a tool_result with no `ok`. `ok` is the ONLY signal of tool
        // success, so a frame without it cannot be interpreted at all.
        `event: tool_result\ndata: ${JSON.stringify({ msg_id: "m1", call_id: "c1", name: "rm", output: "done" })}\n\n`,
        `event: end\ndata: ${JSON.stringify({ msg_id: "m1", user_index: 0, assistant_index: 1, versions: 1, active: 0 })}\n\n`,
      ].join(""),
    ),
  );

  const engine = createRemoteHttpEngine({
    baseUrl: "http://engine.test",
    http,
    onIgnored: (reason, detail) => refused.push({ reason, detail }),
  });

  const events = [];
  for await (const event of engine.run(
    { prompt: "hi", chatId: "c1", runId: "r1", tools: true, regenerateOf: null, attachments: [] },
    new AbortController().signal,
  )) {
    events.push(event);
  }

  assert.equal(
    events.some((e) => e.type === "tool_result"),
    false,
    "an undecodable frame must not be yielded as if it were fine",
  );
  assert.equal(refused.length, 1, "the refusal must be reported to the caller");
  assert.equal(refused[0]?.reason, "missing_required_field");
  assert.equal(refused[0]?.detail, "tool_result.ok", "the detail must name the field, so a report is actionable");
});

test("a clean stream reports no refusals", async () => {
  // The pair. An engine that reported a refusal per frame would satisfy the
  // test above and mark every healthy turn as damaged.
  const http = createFakeHttp();
  const refused: unknown[] = [];
  http.on("/chat", () => sseResponse(framesFor(SCRIPTS.happy)));

  const engine = createRemoteHttpEngine({
    baseUrl: "http://engine.test",
    http,
    onIgnored: (...args) => refused.push(args),
  });

  for await (const _ of engine.run(
    { prompt: "hi", chatId: "c1", runId: "r1", tools: true, regenerateOf: null, attachments: [] },
    new AbortController().signal,
  )) {
    // drain
  }
  assert.deepEqual(refused, []);
});

test("each kind of unreadable frame reports its own reason and keeps the payload", async () => {
  // `safeParse` returned `{}` for anything it could not read, and the caller
  // spread it and added `type` -- so an HTML error page from a proxy, a body
  // truncated by a cut connection, an array, a bare string and `null` ALL came
  // back as `missing_msg_id`, with the payload gone so `detail` could not
  // recover it. Now that rejections are user-visible prose, that told the user
  // "an event arrived with no message it belongs to" about a 502 page and
  // pointed their support engineer at an engine bug that does not exist.
  const cases: { body: string; reason: string; detailHas: string }[] = [
    { body: "<html>502 Bad Gateway</html>", reason: "unparseable_json", detailHas: "502" },
    { body: '{"msg_id":"m1","te', reason: "unparseable_json", detailHas: "msg_id" },
    { body: "[1,2,3]", reason: "not_an_object", detailHas: "array" },
    { body: '"just a string"', reason: "not_an_object", detailHas: "string" },
    { body: "null", reason: "not_an_object", detailHas: "object" },
  ];

  for (const c of cases) {
    const http = createFakeHttp();
    const refused: { reason: string; detail: string }[] = [];
    http.on("/chat", () =>
      sseResponse(
        `event: start\ndata: ${JSON.stringify({ msg_id: "m1", run_id: "r1" })}\n\n` +
          `event: delta\ndata: ${c.body}\n\n` +
          `event: end\ndata: ${JSON.stringify({ msg_id: "m1", user_index: 0, assistant_index: 1, versions: 1, active: 0 })}\n\n`,
      ),
    );
    const engine = createRemoteHttpEngine({
      baseUrl: "http://engine.test",
      http,
      onIgnored: (reason, detail) => refused.push({ reason, detail }),
    });
    for await (const _ of engine.run(
      { prompt: "hi", chatId: "c1", runId: "r1", tools: true, regenerateOf: null, attachments: [] },
      new AbortController().signal,
    )) {
      // drain
    }
    assert.equal(refused[0]?.reason, c.reason, `wrong reason for ${c.body}`);
    assert.match(
      refused[0]?.detail ?? "",
      new RegExp(c.detailHas),
      `the detail must carry enough to identify the frame: ${c.body}`,
    );
  }
});

test("both 401 and 403 are auth failures, so the UI offers credentials", async () => {
  // `status === 401 || status === 403` -> dropping the 403 survived. A 403 is
  // what an engine behind a proxy or with a scoped key actually returns, and
  // classifying it `transport` makes the UI offer Retry forever instead of
  // sending the user to settings. The kind is the whole reason the error
  // carries one.
  for (const [status, kind] of [[401, "auth"], [403, "auth"], [500, "transport"], [502, "transport"]] as const) {
    const http = createFakeHttp();
    http.on("/chat", () => ({ status, headers: {}, body: null }));
    const engine = createRemoteHttpEngine({ baseUrl: "http://engine.test", http });

    const events = [];
    for await (const event of engine.run(
      { prompt: "hi", chatId: "c1", runId: "r1", tools: true, regenerateOf: null, attachments: [] },
      new AbortController().signal,
    )) {
      events.push(event);
    }
    const error = events.find((e) => e.type === "error");
    assert.equal(error?.kind, kind, `HTTP ${status} should be ${kind}`);
  }
});
