/**
 * An HttpPort the test drives.
 *
 * Records every request so a test can assert on what was sent, and serves
 * canned SSE bodies so the remote engine can be driven through every
 * conformance scenario with no server, no sockets and no sleeping.
 */
import type { HttpPort, HttpRequest, HttpResponse } from "../../core/src/ports/http.ts";

export interface FakeHttp extends HttpPort {
  /** Every request sent, in order. */
  readonly sent: readonly HttpRequest[];
  /** Queue a response for the next request to a URL ending in `suffix`. */
  on(suffix: string, response: () => HttpResponse): void;
}

/** Turn a string into the byte stream an HttpResponse body carries. Chunked
 *  deliberately, because a frame split across chunks is the normal case on a
 *  real network and the SSE reader must survive it. */
export function streamOf(text: string, chunkSize = 7): ReadableStream<Uint8Array> {
  const bytes = new TextEncoder().encode(text);
  let offset = 0;
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (offset >= bytes.length) {
        controller.close();
        return;
      }
      controller.enqueue(bytes.slice(offset, offset + chunkSize));
      offset += chunkSize;
    },
  });
}

export function jsonResponse(status: number, body: unknown): HttpResponse {
  return {
    status,
    headers: { "content-type": "application/json" },
    body: streamOf(JSON.stringify(body)),
  };
}

export function sseResponse(frames: string): HttpResponse {
  return {
    status: 200,
    headers: { "content-type": "text/event-stream" },
    body: streamOf(frames),
  };
}

export function createFakeHttp(): FakeHttp {
  const sent: HttpRequest[] = [];
  const handlers = new Map<string, () => HttpResponse>();

  return {
    sent,
    sendsFromNative: false,
    on(suffix, response) {
      handlers.set(suffix, response);
    },
    async send(request) {
      sent.push(request);
      // Longest suffix wins, so "/chat" does not shadow "/chats".
      const match = [...handlers.keys()]
        .filter((s) => request.url.endsWith(s))
        .sort((a, b) => b.length - a.length)[0];
      if (match === undefined) {
        return { status: 404, headers: {}, body: null };
      }
      return handlers.get(match)!();
    },
  };
}
