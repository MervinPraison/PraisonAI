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
import { decodeEvent, isDecoded } from "../../../protocol/src/decode.ts";
import { createSseReader } from "../../../protocol/src/sse.ts";
import { classify, type Readiness } from "./readiness.ts";

export interface RemoteHttpOptions {
  /** Base URL of the engine, no trailing slash. */
  readonly baseUrl: string;
  readonly http: HttpPort;
  /** Sent as a bearer token when present. The desktop engine is unauthenticated
   *  on loopback; anything off-device must not be. */
  readonly token?: string;
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
  const base = options.baseUrl.replace(/\/+$/, "");
  const id = options.id ?? "remote-http";

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
  const postOk = async (path: string, body: unknown): Promise<boolean> => {
    try {
      const response = await options.http.send({
        method: "POST",
        url: `${base}${path}`,
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
      const response = await options.http.send({
        method: "POST",
        url: `${base}/chat`,
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
            const outcome = decodeEvent({ ...safeParse(frame.data), type: frame.event });
            if (isDecoded(outcome)) yield outcome.event;
          }
        }
      } finally {
        // Release the socket whether we finished, aborted, or threw.
        await reader.cancel().catch(() => {});
      }
    },

    async decide(approvalId: string, choice: ApprovalChoice): Promise<boolean> {
      return postOk(`/approve/${encodeURIComponent(approvalId)}`, { choice });
    },

    async cancel(runId: string): Promise<boolean> {
      return postOk(`/cancel/${encodeURIComponent(runId)}`, {});
    },

    async dispose(): Promise<void> {
      // Nothing held open between runs; each run owns its reader and releases
      // it in a finally.
    },
  };
}

/** A frame's data that is not JSON is not a reason to throw -- decodeEvent
 *  will report it as unparseable with a reason. */
function safeParse(data: string): Record<string, unknown> {
  try {
    const parsed: unknown = JSON.parse(data);
    return parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : {};
  } catch {
    return {};
  }
}

/** Probe `/health` and classify it. Separate from the engine so a connection
 *  manager can check readiness before offering the engine at all. */
export async function probeHealth(
  http: HttpPort,
  baseUrl: string,
  token?: string,
): Promise<Readiness> {
  const base = baseUrl.replace(/\/+$/, "");
  try {
    const response = await http.send({
      method: "GET",
      url: `${base}/health`,
      headers: token === undefined ? {} : { authorization: `Bearer ${token}` },
      signal: new AbortController().signal,
    });
    const body = response.body;
    let text = "";
    if (body !== null) {
      const reader = body.getReader();
      const decoder = new TextDecoder();
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        text += decoder.decode(value, { stream: true });
      }
      text += decoder.decode();
    }
    return classify({ kind: "http", status: response.status, body: text });
  } catch (error) {
    return classify({
      kind: "transport",
      detail: error instanceof Error ? error.message : String(error),
    });
  }
}
