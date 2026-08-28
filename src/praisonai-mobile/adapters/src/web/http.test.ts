/**
 * The web HttpPort.
 *
 * It had no test, and a mutation audit found two survivors that matter:
 * deleting `signal: request.signal` (Stop reaches the engine and never reaches
 * `fetch`), and flipping `sendsFromNative` to true — the flag this file's own
 * header calls "load-bearing rather than informational", because it is the
 * claim that an API key does not enter the webview heap.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { createWebHttp } from "./http.ts";

/** A fetch that records exactly what it was handed. */
function recordingFetch() {
  const calls: { url: string; init: RequestInit }[] = [];
  const impl = (async (url: unknown, init: unknown) => {
    calls.push({ url: String(url), init: (init ?? {}) as RequestInit });
    return {
      status: 200,
      headers: { forEach: (cb: (v: string, k: string) => void) => cb("application/json", "content-type") },
      body: null,
    };
  }) as unknown as typeof fetch;
  return { impl, calls };
}

test("the caller's abort signal is handed to fetch", () => {
  // Deleting this line survived the whole suite. Stop would reach the engine
  // and never reach the network: the provider keeps generating, and keeps
  // billing, after the user pressed the button.
  const { impl, calls } = recordingFetch();
  const controller = new AbortController();

  return createWebHttp(impl)
    .send({ url: "https://x.test", method: "POST", headers: {}, signal: controller.signal })
    .then(() => {
      assert.equal(calls[0]?.init.signal, controller.signal, "the signal must reach fetch");
    });
});

test("aborting the caller's signal aborts what fetch was given", () => {
  // Identity alone could be satisfied by a detached signal that never fires.
  const { impl, calls } = recordingFetch();
  const controller = new AbortController();

  return createWebHttp(impl)
    .send({ url: "https://x.test", method: "GET", headers: {}, signal: controller.signal })
    .then(() => {
      controller.abort();
      assert.equal((calls[0]?.init.signal as AbortSignal).aborted, true);
    });
});

test("it never claims to send from native", () => {
  // The composition root refuses to hand a hardware-backed secret to a
  // non-native transport. A dishonest flag here makes that check decorative
  // and puts a keychain-held key into the JS heap.
  assert.equal(createWebHttp(recordingFetch().impl).sendsFromNative, false);
});

test("a body is passed through, and omitted when absent", () => {
  // `...(body === undefined ? {} : { body })` -- sending `body: undefined` on
  // a GET throws in some runtimes rather than being ignored.
  const { impl, calls } = recordingFetch();
  const http = createWebHttp(impl);

  return http.send({ url: "https://x.test", method: "POST", headers: {}, body: "hello", signal: new AbortController().signal })
    .then(() => http.send({ url: "https://x.test", method: "GET", headers: {}, signal: new AbortController().signal }))
    .then(() => {
      assert.equal(calls[0]?.init.body, "hello");
      assert.equal("body" in (calls[1]?.init ?? {}), false, "a GET must carry no body key at all");
    });
});

test("the method and headers reach fetch unchanged", () => {
  const { impl, calls } = recordingFetch();
  return createWebHttp(impl)
    .send({ url: "https://x.test/v1", method: "POST", headers: { authorization: "Bearer t" }, signal: new AbortController().signal })
    .then(() => {
      assert.equal(calls[0]?.url, "https://x.test/v1");
      assert.equal(calls[0]?.init.method, "POST");
      assert.deepEqual(calls[0]?.init.headers, { authorization: "Bearer t" });
    });
});

test("response headers are flattened for the caller", () => {
  const { impl } = recordingFetch();
  return createWebHttp(impl)
    .send({ url: "https://x.test", method: "GET", headers: {}, signal: new AbortController().signal })
    .then((r) => {
      assert.equal(r.status, 200);
      assert.equal(r.headers["content-type"], "application/json");
    });
});

test("the response status is reported as it was received", async () => {
  // `status: response.status` -> `status: 200` survived. Every 401, 403, 429
  // and 502 would be classified as success: the engine reads the status to
  // decide `auth` vs `transport`, so the whole recovery distinction -- go to
  // settings, or retry -- is fed a constant.
  //
  // The tests that DO cover that distinction drive the fake http, not this
  // adapter, so the one place the real status is read was unguarded.
  for (const status of [200, 204, 401, 403, 429, 500, 502]) {
    const impl = (async () => ({
      status,
      headers: { forEach: (cb: (v: string, k: string) => void) => cb("application/json", "content-type") },
      body: null,
    })) as unknown as typeof fetch;

    const response = await createWebHttp(impl).send({
      url: "https://x.test",
      method: "POST",
      headers: {},
      signal: new AbortController().signal,
    });
    assert.equal(response.status, status, `HTTP ${status} was reported as ${response.status}`);
  }
});
