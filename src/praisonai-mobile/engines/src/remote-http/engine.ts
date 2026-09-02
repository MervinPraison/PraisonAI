/**
 * An engine that speaks to a PraisonAI engine over HTTP + SSE.
 *
 * This is the FIRST engine that talks to something real, and deliberately so.
 * It targets the desktop engine's existing protocol v2 surface unchanged, so
 * it can be pointed at a running desktop install today -- no new engine route,
 * no server work, nothing to deploy.
 *
 * It is also the second implementation of AgentEnginePort, after the scripted
 * fake. That matters more than it looks: a seam with one implementation is an
 * interface shaped around that implementation. Two, written against the same
 * conformance suite, is a seam.
 *
 * All I/O goes through HttpPort. There is no `fetch` in this file, which is
 * what lets the whole engine be driven through every conformance scenario with
 * no server and no sockets -- and what lets the Tauri adapter route the request
 * through Rust so an API key never enters the webview's heap.
 */
import type {
  AgentEnginePort,
  EngineCapabilities,
  RunRequest,
} from "../../../core/src/ports/agent-engine.ts";
import type { HttpPort } from "../../../core/src/ports/http.ts";
import type { ApprovalChoice, RunEvent } from "../../../protocol/src/events.ts";
import { PROTOCOL_VERSION } from "../../../protocol/src/version.ts";
import { decodeEvent, isDecoded, type IgnoredReason } from "../../../protocol/src/decode.ts";
import { createSseReader } from "../../../protocol/src/sse.ts";
import { classify, type Readiness } from "./readiness.ts";

export interface RemoteHttpOptions {
  /**
   * Base URL of the engine, no trailing slash.
   *
   * A RESOLVER is accepted as well as a string, and the difference is the
   * whole recovery path for a device that cannot reach its engine. This engine
   * is constructed once, at boot, and the app holds it for the session -- so a
   * captured string means the address the user corrects in Settings is
   * persisted, displayed, and then ignored until the app is force-quit. A
   * function is re-read per request, so the next message goes where the user
   * just said. A plain string still works and still means "this one, forever".
   */
  readonly baseUrl: string | (() => string);
  readonly http: HttpPort;
  /** Sent as a bearer token when present. The desktop engine is unauthenticated
   *  on loopback; anything off-device must not be. */
  readonly token?: string;
  /** Called for every frame the decoder REFUSED. Without it the refusal is
   *  invisible: a truncated answer reported as a clean success. */
  readonly onIgnored?: (reason: IgnoredReason, detail: string) => void;
  readonly id?: string;
}

const CAPABILITIES: EngineCapabilities = {
  streaming: true,
  reasoning: true,
  tools: true,
  approvals: true,
  cancellation: true,
  attachments: true,
};

export function createRemoteHttpEngine(options: RemoteHttpOptions): AgentEnginePort {
  // Resolved per call, never captured. The trailing slash is stripped here
  // rather than at the caller because a resolver's answer is not seen until
  // now: `${base}/chat` against "http://host/" produces a double slash, which
  // some servers 404 and others redirect -- losing the POST body.
  const base = (): string =>
    (typeof options.baseUrl === "string" ? options.baseUrl : options.baseUrl()).replace(/\/+$/, "");
  const id = options.id ?? "remote-http";

  // Where each in-flight run was STARTED. A resolver means `base()` can move
  // between calls -- that is the whole point, so the next /chat reaches the
  // address the user just fixed. But a run's /cancel, and an approval's
  // /approve, are addressed by an id the ORIGINATING engine minted; sending
  // them to a newly-corrected address hands a foreign id to an engine that
  // never issued it, which refuses it -- and controller.ts only aborts the
  // local reader once cancel returns true, so the original turn keeps
  // generating at the old address while the user believes they stopped it.
  // Pinning the id to the base it was born at keeps a mid-turn address change
  // from redirecting the control request off the run it belongs to.
  const runBase = new Map<string, string>();
  const approvalBase = new Map<string, string>();

  const headers = (extra: Record<string, string> = {}): Record<string, string> => ({
    "content-type": "application/json",
    ...(options.token === undefined ? {} : { authorization: `Bearer ${options.token}` }),
    ...extra,
  });

  /** Read a whole body to a string. Used for the small JSON endpoints. */
  const readAll = async (body: ReadableStream<Uint8Array> | null): Promise<string> => {
    if (body === null) return "";
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let out = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      out += decoder.decode(value, { stream: true });
    }
    return out + decoder.decode();
  };

  /** POST a small JSON request and read `{ok: boolean}` out of the reply.
   *  Returns false on anything that is not an explicit success -- reporting
   *  success for an unknown id "would be a lie the UI cannot detect". */
  const postOk = async (path: string, body: unknown, origin: string): Promise<boolean> => {
    try {
      const response = await options.http.send({
        method: "POST",
        url: `${origin}${path}`,
        headers: headers(),
        body: JSON.stringify(body),
        signal: new AbortController().signal,
      });
      if (response.status !== 200) return false;
      const parsed: unknown = JSON.parse(await readAll(response.body));
      return (
        parsed !== null &&
        typeof parsed === "object" &&
        (parsed as Record<string, unknown>)["ok"] === true
      );
    } catch {
      // A failed cancel or decision must report failure, not throw into a
      // click handler. The caller shows a retry; the run is still blocked.
      return false;
    }
  };

  return {
    id,
    protocolVersion: PROTOCOL_VERSION,
    capabilities: CAPABILITIES,

    async *run(request: RunRequest, signal: AbortSignal): AsyncIterable<RunEvent> {
      // Resolved ONCE, here, and remembered for this run's control requests.
      // The /chat POST and every later /cancel for this runId must reach the
      // same engine even if Settings changes the address mid-stream.
      const origin = base();
      runBase.set(request.runId, origin);
      const response = await options.http.send({
        method: "POST",
        url: `${origin}/chat`,
        headers: headers({ accept: "text/event-stream" }),
        body: JSON.stringify({
          prompt: request.prompt,
          chat_id: request.chatId,
          run_id: request.runId,
          tools: request.tools,
          regenerate_of: request.regenerateOf,
          attachments: request.attachments,
        }),
        signal,
      });

      if (response.status !== 200 || response.body === null) {
        // Synthesised rather than thrown: the controller turns a thrown
        // iterator into a transport error anyway, but an engine that can name
        // the failure should.
        yield {
          type: "error",
          msgId: `m_${request.runId}`,
          kind: response.status === 401 || response.status === 403 ? "auth" : "transport",
          message: `engine responded ${response.status}`,
        };
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      const readFrames = createSseReader();

      try {
        for (;;) {
          // Checked before each read rather than only at the top, so an abort
          // mid-stream stops the next event arriving.
          if (signal.aborted) return;

          const { done, value } = await reader.read();
          if (done) break;

          for (const frame of readFrames(decoder.decode(value, { stream: true }))) {
            // decodeEvent never throws. An unknown event is a recorded no-op,
            // which is what makes a newer engine safe to talk to.
            //
            // "Recorded" used to be aspirational: the ignored branch was
            // dropped on the floor here, and this is the ONLY production
            // caller of decodeEvent. So a malformed `tool_result` frame made
            // its tool vanish and the turn rendered as a clean answer, while
            // the reducer's Dropped type, the view model's dropped row and
            // seven user-facing strings sat unreachable.
            const parsed = parseFrame(frame.data);
            if (!parsed.ok) {
              options.onIgnored?.(parsed.reason, parsed.detail);
              continue;
            }
            const outcome = decodeEvent({ ...parsed.value, type: frame.event });
            if (isDecoded(outcome)) {
              // An approval blocks the run and is answered by an id THIS engine
              // minted, so its /approve must land back here even after Settings
              // moves the address. Pinned to the run's origin, not `base()`.
              if (outcome.event.type === "approval_request") {
                approvalBase.set(outcome.event.approvalId, origin);
              }
              yield outcome.event;
            } else {
              options.onIgnored?.(outcome.reason, outcome.detail);
            }
          }
        }
      } finally {
        // Release the socket whether we finished, aborted, or threw.
        await reader.cancel().catch(() => {});
        // The run is over: its id can no longer be cancelled meaningfully, so
        // drop the pin rather than let the map grow for the session. A /cancel
        // that races the natural end falls back to `base()` -- harmless, the
        // run is already gone. Approval pins outlive the map entry only until
        // decided; they are cleared in `decide`.
        runBase.delete(request.runId);
      }
    },

    async decide(approvalId: string, choice: ApprovalChoice): Promise<boolean> {
      // The engine that asked is the engine that must be told. Fall back to the
      // live resolver only for an id this instance never saw (a resumed app
      // that reconnected), where the current address is the best guess left.
      const origin = approvalBase.get(approvalId) ?? base();
      const ok = await postOk(`/approve/${encodeURIComponent(approvalId)}`, { choice }, origin);
      approvalBase.delete(approvalId);
      return ok;
    },

    async cancel(runId: string): Promise<boolean> {
      // Pinned to where the run STARTED. A mid-turn address change must not
      // redirect the stop to an engine that never issued this runId.
      return postOk(`/cancel/${encodeURIComponent(runId)}`, {}, runBase.get(runId) ?? base());
    },

    async dispose(): Promise<void> {
      // Nothing held open between runs; each run owns its reader and releases
      // it in a finally.
    },
  };
}

/** A frame's data that is not JSON is not a reason to throw -- decodeEvent
 *  will report it as unparseable with a reason. */
/**
 * Parse an SSE frame body, keeping WHY it failed.
 *
 * This used to be `safeParse`, which returned `{}` for anything it could not
 * read. Since the caller then spreads it and adds `type`, every wire failure
 * reached the decoder as an object with only a type -- so five distinct
 * failures (an HTML error page from a proxy, a truncated body from a cut
 * connection, a JSON array, a bare string, `null`) all came back as
 * `missing_msg_id`, and the payload was gone so `detail` could not recover it.
 *
 * That was survivable while rejections were discarded. They are user-visible
 * prose now: a 502 page from a proxy told the user "an event arrived with no
 * message it belongs to", pointing whoever they reported it to at an engine
 * bug that does not exist. Two shipped strings -- "not valid JSON" and "a
 * value where an event was expected" -- were unreachable for the same reason.
 */
type ParsedFrame =
  | { readonly ok: true; readonly value: Record<string, unknown> }
  | { readonly ok: false; readonly reason: IgnoredReason; readonly detail: string };

function parseFrame(data: string): ParsedFrame {
  let parsed: unknown;
  try {
    parsed = JSON.parse(data);
  } catch {
    return { ok: false, reason: "unparseable_json", detail: data.slice(0, 120) };
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { ok: false, reason: "not_an_object", detail: Array.isArray(parsed) ? "array" : typeof parsed };
  }
  return { ok: true, value: parsed as Record<string, unknown> };
}

/** How long a boot-time probe waits before giving up. This runs BEFORE the app
 *  mounts, so an endpoint that accepts the connection but never answers -- or
 *  never closes its body -- would otherwise hang `selectEngine`, `createApp`
 *  and the whole mount forever. A bounded deadline turns that stall into a
 *  named, retryable transport failure instead. */
export const PROBE_TIMEOUT_MS = 5000;

/** Probe `/health` and classify it. Separate from the engine so a connection
 *  manager can check readiness before offering the engine at all.
 *
 *  Bounded by `timeoutMs`: the probe blocks boot, so a request or body read
 *  that never completes must abort rather than pin the app on a blank screen.
 *  A timeout is classified as retryable transport -- a still-starting engine is
 *  exactly the case worth polling. */
export async function probeHealth(
  http: HttpPort,
  baseUrl: string,
  token?: string,
  timeoutMs: number = PROBE_TIMEOUT_MS,
): Promise<Readiness> {
  const base = baseUrl.replace(/\/+$/, "");
  // Abort BOTH the request and the body read below off one deadline: the reader
  // shares this response, so aborting the signal unblocks a stalled read too.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await http.send({
      method: "GET",
      url: `${base}/health`,
      headers: token === undefined ? {} : { authorization: `Bearer ${token}` },
      signal: controller.signal,
    });
    const body = response.body;
    let text = "";
    if (body !== null) {
      const reader = body.getReader();
      const decoder = new TextDecoder();
      try {
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          text += decoder.decode(value, { stream: true });
        }
        text += decoder.decode();
      } finally {
        // Release the stream lock so an aborted read does not leak the reader.
        reader.releaseLock();
      }
    }
    return classify({ kind: "http", status: response.status, body: text });
  } catch (error) {
    return classify({
      kind: "transport",
      detail: error instanceof Error ? error.message : String(error),
    });
  } finally {
    clearTimeout(timer);
  }
}
