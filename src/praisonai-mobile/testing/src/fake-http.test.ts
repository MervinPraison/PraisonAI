/**
 * The fake HTTP transport, tested as the thing engine tests depend on.
 *
 * Two of its behaviours are load-bearing for tests written against it, and a
 * mutation sweep found both unguarded:
 *
 *   the route table picks the LONGEST matching suffix, so `/chats` does not
 *   shadow `/chat` -- inverting it silently mis-routes a test to the wrong
 *   handler and the test still passes, against the wrong thing;
 *
 *   `streamOf` chunks its body deliberately, "because a frame split across
 *   chunks is the normal case on a real network". Emitting an extra
 *   zero-length chunk, or the whole body at once, changes what the SSE reader
 *   is exercised with -- and the reader's pending-CR logic is precisely
 *   sensitive to chunk boundaries. A fake that stops splitting can mask the
 *   CRLF defect this package has already shipped once.
 *
 * This is the fifth fake in the package to get its own tests after being
 * caught misrepresenting what it stands in for.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { createFakeHttp, streamOf } from "./fake-http.ts";

const send = (http: ReturnType<typeof createFakeHttp>, url: string) =>
  http.send({ url, method: "POST", headers: {}, signal: new AbortController().signal });

test("the longest matching suffix wins, so a general route does not shadow a specific one", async () => {
  const http = createFakeHttp();
  http.on("/chat", () => ({ status: 200, headers: {}, body: null }));
  http.on("/v1/chat", () => ({ status: 201, headers: {}, body: null }));

  const specific = await send(http, "http://engine.test/v1/chat");
  assert.equal(specific.status, 201, "the more specific route must win");

  const general = await send(http, "http://engine.test/chat");
  assert.equal(general.status, 200);
});

test("an unmatched request is a 404, not a silent success", async () => {
  const http = createFakeHttp();
  http.on("/chat", () => ({ status: 200, headers: {}, body: null }));
  const missed = await send(http, "http://engine.test/nothing-registered");
  assert.equal(missed.status, 404, "an unregistered path must be visibly unhandled");
});

test("every request is recorded, in order", async () => {
  const http = createFakeHttp();
  http.on("/a", () => ({ status: 200, headers: {}, body: null }));
  http.on("/b", () => ({ status: 200, headers: {}, body: null }));
  await send(http, "http://engine.test/a");
  await send(http, "http://engine.test/b");
  assert.deepEqual(
    http.sent.map((r) => r.url),
    ["http://engine.test/a", "http://engine.test/b"],
  );
});

test("streamOf splits the body, and emits no empty chunks", async () => {
  // The chunking is the point: a frame split across chunks is the normal case
  // on a real network, and the SSE reader's pending-CR logic is sensitive to
  // exactly where the boundaries fall. An extra zero-length chunk at the end
  // is not something a real network produces, and it changes what the reader
  // is being exercised with.
  const read = async (text: string, size?: number): Promise<number[]> => {
    const reader = (size === undefined ? streamOf(text) : streamOf(text, size)).getReader();
    const sizes: number[] = [];
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      sizes.push(value.length);
    }
    return sizes;
  };

  assert.deepEqual(await read(""), [], "an empty body is no chunks at all");
  assert.deepEqual(await read("abcdefg"), [7], "a body shorter than the chunk size is one chunk");
  assert.deepEqual(await read("abcdefgh"), [7, 1], "and a longer one is split");
  assert.deepEqual(await read("abcdef", 2), [2, 2, 2], "the chunk size is honoured exactly");
  assert.equal(
    (await read("abcdefghij", 3)).includes(0),
    false,
    "a zero-length chunk is not something a network produces",
  );
});

test("streamOf reassembles to exactly the input", async () => {
  const text = 'event: delta\r\ndata: {"msg_id":"m","text":"hello"}\r\n\r\n';
  const reader = streamOf(text, 3).getReader();
  const parts: Uint8Array[] = [];
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    parts.push(value);
  }
  const joined = new TextDecoder().decode(
    Uint8Array.from(parts.flatMap((p) => [...p])),
  );
  assert.equal(joined, text, "no byte may be lost or duplicated by the chunking");
});
