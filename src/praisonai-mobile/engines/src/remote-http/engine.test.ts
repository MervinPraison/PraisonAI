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
import { createFakeHttp, sseResponse, jsonResponse, streamOf } from "../../../testing/src/fake-http.ts";
import { SCRIPTS } from "../../../testing/src/scripts.ts";
import { encodeSseFrame } from "../../../protocol/src/encode.ts";
import { PROTOCOL_VERSION } from "../../../protocol/src/version.ts";
import type { RunEvent } from "../../../protocol/src/events.ts";
import type { HttpPort } from "../../../core/src/ports/http.ts";

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

test("remote-http: a probe whose endpoint never answers gives up on the deadline, retryably", async () => {
  // The probe runs BEFORE the app mounts. An endpoint that accepts the socket
  // but never sends the response -- a still-binding engine, a black-hole proxy
  // -- must not pin boot forever: the bounded deadline aborts it and classifies
  // the timeout as retryable transport, exactly the case worth polling.
  let aborted = false;
  const hanging: HttpPort = {
    sendsFromNative: false,
    send: (request) =>
      new Promise((_resolve, reject) => {
        request.signal.addEventListener("abort", () => {
          aborted = true;
          reject(new Error("aborted"));
        });
      }),
  };
  const verdict = await probeHealth(hanging, BASE, undefined, 10);
  assert.equal(aborted, true, "the deadline must abort the stalled request");
  assert.equal(verdict.ready, false);
  assert.equal(verdict.ready === false && verdict.reason, "transport");
  assert.equal(verdict.ready === false && verdict.retryable, true);
});

test("remote-http: a probe whose body never ends gives up on the deadline", async () => {
  // The other stall: headers arrive but the /health body never closes. The
  // reader shares the request signal, so the same deadline unblocks it.
  let bodyAborted = false;
  const hangingBody: HttpPort = {
    sendsFromNative: false,
    send: async (request) => ({
      status: 200,
      headers: {},
      body: new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(new TextEncoder().encode('{"ok"'));
          request.signal.addEventListener("abort", () => {
            bodyAborted = true;
            controller.error(new Error("aborted"));
          });
        },
      }),
    }),
  };
  const verdict = await probeHealth(hangingBody, BASE, undefined, 10);
  assert.equal(bodyAborted, true, "the deadline must abort the stalled body read");
  assert.equal(verdict.ready, false);
  assert.equal(verdict.ready === false && verdict.reason, "transport");
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

// ---- the error paths, where a phone spends much of its life -----------------
//
// A package-wide sweep put `engines/` at 46.7% genuine mutation survival --
// more than double the package average, and 4.5x `core/`. Six of its seven
// survivors were on transport-failure or early-exit paths: the conformance
// harness covers the happy path thoroughly and nothing covered these.

test("a decision or cancel the engine did NOT accept is reported as refused", async () => {
  // `response.status !== 200` -> `false` survived. Every non-200 -- 202, 401,
  // 500 -- would report success, so the UI announces a stop that never
  // happened and marks an approval sent that the engine never received. Both
  // callers were written to trust this boolean.
  for (const status of [202, 400, 401, 403, 500, 502]) {
    const http = createFakeHttp();
    http.on("/approve/a1", () => ({ status, headers: {}, body: streamOf(JSON.stringify({ ok: true })) }));
    http.on("/cancel/r1", () => ({ status, headers: {}, body: streamOf(JSON.stringify({ ok: true })) }));
    const engine = createRemoteHttpEngine({ baseUrl: "http://engine.test", http });

    assert.equal(await engine.decide("a1", "allow"), false, `HTTP ${status} must not read as accepted`);
    assert.equal(await engine.cancel("r1"), false, `HTTP ${status} must not read as cancelled`);
  }
});

test("a 200 with an ok body is accepted, so the refusal test is not vacuous", async () => {
  const http = createFakeHttp();
  http.on("/approve/a1", () => ({ status: 200, headers: {}, body: streamOf(JSON.stringify({ ok: true })) }));
  http.on("/cancel/r1", () => ({ status: 200, headers: {}, body: streamOf(JSON.stringify({ ok: true })) }));
  const engine = createRemoteHttpEngine({ baseUrl: "http://engine.test", http });
  assert.equal(await engine.decide("a1", "allow"), true);
  assert.equal(await engine.cancel("r1"), true);
});

test("leaving the stream early releases the socket", async () => {
  // Dropping `await reader.cancel()` from the `finally` survived. On New chat
  // or Stop the consumer breaks out of the loop, and without the cancel the
  // engine keeps generating into a socket nobody drains -- and keeps billing.
  let cancelled = false;
  const http = createFakeHttp();
  http.on("/chat", () => ({
    status: 200,
    headers: { "content-type": "text/event-stream" },
    body: new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(
          new TextEncoder().encode(
            `event: start\ndata: ${JSON.stringify({ msg_id: "m1", run_id: "r1" })}\n\n` +
              `event: delta\ndata: ${JSON.stringify({ msg_id: "m1", text: "one" })}\n\n`,
          ),
        );
        // never closed, so only an explicit cancel releases it
      },
      cancel() {
        cancelled = true;
      },
    }),
  }));

  const engine = createRemoteHttpEngine({ baseUrl: "http://engine.test", http });
  for await (const event of engine.run(
    { prompt: "hi", chatId: "c1", runId: "r1", tools: true, regenerateOf: null, attachments: [] },
    new AbortController().signal,
  )) {
    if (event.type === "delta") break; // the consumer leaves early
  }

  assert.equal(cancelled, true, "the response stream must be released when the consumer stops reading");
});

test("the SSE event name decides the type, not a field inside the payload", async () => {
  // `{ ...parsed.value, type: frame.event }` transposed survived. A frame whose
  // data object happens to carry its own `type` would then be decoded as THAT
  // type -- and a delta arriving as an ill-formed `error` is dropped silently,
  // so text vanishes from the answer with no diagnostic.
  const http = createFakeHttp();
  http.on("/chat", () =>
    sseResponse(
      `event: start\ndata: ${JSON.stringify({ msg_id: "m1", run_id: "r1" })}\n\n` +
        `event: delta\ndata: ${JSON.stringify({ msg_id: "m1", text: "kept", type: "error" })}\n\n` +
        `event: end\ndata: ${JSON.stringify({ msg_id: "m1", user_index: 0, assistant_index: 1, versions: 1, active: 0 })}\n\n`,
    ),
  );
  const engine = createRemoteHttpEngine({ baseUrl: "http://engine.test", http });

  const events = [];
  for await (const event of engine.run(
    { prompt: "hi", chatId: "c1", runId: "r1", tools: true, regenerateOf: null, attachments: [] },
    new AbortController().signal,
  )) {
    events.push(event);
  }

  const delta = events.find((e) => e.type === "delta");
  assert.ok(delta, `the delta was lost: ${events.map((e) => e.type).join(", ")}`);
  assert.equal(delta.type === "delta" ? delta.text : null, "kept");
});

test("the request carries the RUN id and the CHAT id in their own fields", () => {
  // `run_id: request.runId` -> `request.chatId` survived. `POST /cancel/{runId}`
  // could then never match a live run, so Stop is permanently dead against the
  // remote engine -- which keeps generating and keeps billing -- and the two
  // ids are the same shape, so nothing about the payload looks wrong.
  const http = createFakeHttp();
  http.on("/chat", () => sseResponse(""));
  const engine = createRemoteHttpEngine({ baseUrl: "http://engine.test", http });

  return (async () => {
    for await (const _ of engine.run(
      { prompt: "hi", chatId: "chat-42", runId: "run-7", tools: true, regenerateOf: null, attachments: [] },
      new AbortController().signal,
    )) {
      // drain
    }
    const body = JSON.parse(String(http.sent.find((r) => r.url.includes("/chat"))?.body ?? "{}"));
    assert.equal(body.run_id, "run-7", "the run id must be the run id");
    assert.equal(body.chat_id, "chat-42", "and the chat id must be the chat id");
  })();
});

test("the stream request advertises that it wants SSE", () => {
  // Dropping `accept: "text/event-stream"` survived. A conforming proxy or
  // engine is then free to answer with something else entirely, and the
  // failure surfaces as an unparseable stream rather than as a bad request.
  const http = createFakeHttp();
  http.on("/chat", () => sseResponse(""));
  const engine = createRemoteHttpEngine({ baseUrl: "http://engine.test", http });

  return (async () => {
    for await (const _ of engine.run(
      { prompt: "hi", chatId: "c1", runId: "r1", tools: true, regenerateOf: null, attachments: [] },
      new AbortController().signal,
    )) {
      // drain
    }
    const sent = http.sent.find((r) => r.url.includes("/chat"));
    assert.equal(sent?.headers["accept"], "text/event-stream");
  })();
});

test("a base URL with several trailing slashes still builds one clean path", () => {
  // `/\/+$/` -> `/\/$/` survived: `http://host//` becomes `http://host//chat`,
  // which 404s. A user pasting an address with a stray slash gets an engine
  // that cannot be reached, and nothing says why.
  for (const base of ["http://engine.test", "http://engine.test/", "http://engine.test//", "http://engine.test///"]) {
    const http = createFakeHttp();
    http.on("/chat", () => sseResponse(""));
    const engine = createRemoteHttpEngine({ baseUrl: base, http });
    void engine;
    // The URL is built when the run starts; assert on what was sent.
  }
  const http = createFakeHttp();
  http.on("/chat", () => sseResponse(""));
  const engine = createRemoteHttpEngine({ baseUrl: "http://engine.test///", http });
  return (async () => {
    for await (const _ of engine.run(
      { prompt: "hi", chatId: "c1", runId: "r1", tools: true, regenerateOf: null, attachments: [] },
      new AbortController().signal,
    )) {
      // drain
    }
    assert.equal(http.sent[0]?.url, "http://engine.test/chat");
  })();
});

test("an approval id with URL-significant characters is encoded, not pasted", () => {
  // `encodeURIComponent(approvalId)` dropped survived. An id containing `/`,
  // `#` or `?` -- and an approvalId is opaque, so nothing forbids them --
  // posts the decision to a DIFFERENT path. The engine never sees it and the
  // run stays blocked until its timeout, with the UI showing the decision as
  // sent.
  const http = createFakeHttp();
  const engine = createRemoteHttpEngine({ baseUrl: "http://engine.test", http });

  return engine.decide("ap/1?x=2#f", "allow").then(() => {
    const url = http.sent.find((r) => r.url.includes("/approve"))?.url ?? "";
    assert.ok(url.includes("ap%2F1%3Fx%3D2%23f"), `the id was not encoded: ${url}`);
    assert.equal(url.includes("ap/1?"), false, "an unencoded id changes the path and the query");
  });
});

test("a cancel with an awkward run id is encoded too", () => {
  const http = createFakeHttp();
  const engine = createRemoteHttpEngine({ baseUrl: "http://engine.test", http });
  return engine.cancel("run/9").then(() => {
    const url = http.sent.find((r) => r.url.includes("/cancel"))?.url ?? "";
    assert.ok(url.includes("run%2F9"), `the run id was not encoded: ${url}`);
  });
});

test("a 200 whose body does not say ok:true is reported as refused", async () => {
  // `["ok"] === true` -> `!== false` survived. The status test above covers
  // non-200 only, so every one of these read as SUCCEEDED: the UI announces
  // the run stopped while it keeps streaming, and marks an approval sent that
  // the engine never got. The source comment calls this "a lie the UI cannot
  // detect", and nothing detected it.
  const bodies = ["{}", '{"ok":null}', '{"ok":0}', '{"ok":"true"}', '{"error":"unknown run id"}', "[]", "null"];
  for (const body of bodies) {
    const http = createFakeHttp();
    http.on("/approve/a1", () => ({ status: 200, headers: {}, body: streamOf(body) }));
    http.on("/cancel/r1", () => ({ status: 200, headers: {}, body: streamOf(body) }));
    const engine = createRemoteHttpEngine({ baseUrl: "http://engine.test", http });

    assert.equal(await engine.decide("a1", "allow"), false, `${body} must not read as accepted`);
    assert.equal(await engine.cancel("r1"), false, `${body} must not read as cancelled`);
  }
});

test("a cancel whose transport THREW is reported as refused", async () => {
  // The `catch` returning true survived. A dropped connection on the way to
  // /cancel would report a successful stop: the Stop button confirms a
  // cancellation that never happened, which is the one outcome the port's own
  // contract singles out as worse than reporting failure.
  const http = createFakeHttp();
  http.on("/cancel/r1", () => { throw new Error("ECONNRESET"); });
  http.on("/approve/a1", () => { throw new Error("ECONNRESET"); });
  const engine = createRemoteHttpEngine({ baseUrl: "http://engine.test", http });

  assert.equal(await engine.cancel("r1"), false);
  assert.equal(await engine.decide("a1", "allow"), false);
});

test("a 200 with ok:true IS accepted -- the pair", async () => {
  // Without this, an implementation refusing everything would satisfy all
  // three negative cases above and break every Stop and every approval.
  const http = createFakeHttp();
  http.on("/approve/a1", () => ({ status: 200, headers: {}, body: streamOf('{"ok":true}') }));
  http.on("/cancel/r1", () => ({ status: 200, headers: {}, body: streamOf('{"ok":true}') }));
  const engine = createRemoteHttpEngine({ baseUrl: "http://engine.test", http });

  assert.equal(await engine.decide("a1", "allow"), true);
  assert.equal(await engine.cancel("r1"), true);
});
