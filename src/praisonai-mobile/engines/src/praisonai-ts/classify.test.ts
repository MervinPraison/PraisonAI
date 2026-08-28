/**
 * Error classification.
 *
 * `kind` selects the recovery the UI offers, so a wrong answer here is a user
 * retrying a key that will never work, or waiting out a limit that does not
 * exist. The messages below are real provider strings, not invented ones.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { classifyError, statusOf } from "./classify.ts";

const cases: ReadonlyArray<readonly [string, unknown, string]> = [
  ["openai bad key", new Error("401 Incorrect API key provided: sk-***"), "auth"],
  ["openai missing key", new Error("No API key provided"), "auth"],
  ["anthropic auth", new Error("authentication_error: invalid x-api-key"), "auth"],
  ["forbidden", new Error("403 Forbidden"), "auth"],
  ["openai rate limit", new Error("429 Rate limit reached for gpt-4o"), "rate_limit"],
  ["quota", new Error("You exceeded your current quota"), "rate_limit"],
  ["overloaded", new Error("Overloaded"), "rate_limit"],
  ["reset", new Error("read ECONNRESET"), "transport"],
  ["dns", new Error("getaddrinfo ENOTFOUND api.openai.com"), "transport"],
  ["fetch", new Error("fetch failed"), "transport"],
  ["unknown", new Error("something went sideways"), "internal"],
  ["not an error", "a bare string", "internal"],
  ["null", null, "internal"],
];

for (const [name, error, expected] of cases) {
  test(`${name} classifies as ${expected}`, () => {
    assert.equal(classifyError(error), expected);
  });
}

test("a status code wins over the message text", () => {
  // Providers put prose in the message and truth in the status.
  assert.equal(classifyError({ status: 429, message: "please try again" }), "rate_limit");
  assert.equal(classifyError({ status: 401, message: "please try again" }), "auth");
});

test("auth is checked before quota, because an exhausted key mentions both", () => {
  // The ordering note in classify.ts, asserted. Without it this reads as a
  // rate limit and the user waits forever for a key that is simply invalid.
  assert.equal(classifyError(new Error("403 Forbidden: quota exceeded for this key")), "auth");
});

test("a 5xx is transport, so retry is offered rather than 'something went wrong'", () => {
  assert.equal(classifyError({ status: 503, message: "" }), "transport");
});

test("statusOf reads the shapes providers actually throw", () => {
  assert.equal(statusOf({ status: 429 }), 429);
  assert.equal(statusOf({ statusCode: 401 }), 401);
  assert.equal(statusOf({ response: { status: 500 } }), 500);
  assert.equal(statusOf(new Error("no status")), null);
  assert.equal(statusOf(null), null);
  assert.equal(statusOf({ status: "429" }), null, "a string status is not a status");
});

test("an HTTP 500 is transport, so the UI still offers Retry", () => {
  // `status >= 500` -> `> 500` survived. A plain 500 -- the single most common
  // provider failure -- would classify as `internal`, whose recovery is
  // `none`: the user is told something went wrong and offered no way to try
  // again. 502 and 503 are unaffected, so the boundary is exactly the case
  // that matters most.
  for (const status of [500, 501, 502, 503, 504]) {
    assert.equal(classifyError({ status } as never), "transport", `HTTP ${status}`);
  }
});

test("a 4xx is not transport, so Retry is not offered where it cannot help", () => {
  // The pair. Classifying everything as transport offers Retry for a bad
  // request or a revoked key, which can never succeed.
  assert.notEqual(classifyError({ status: 400 } as never), "transport");
  assert.notEqual(classifyError({ status: 422 } as never), "transport");
});

test("a 403 is an auth failure even when its message says nothing useful", () => {
  // Dropping `status === 403` survived because the message-matching branch
  // catches anything that literally contains "403" or "forbidden". A provider
  // returning `{status: 403, message: "nope"}` then classifies as `internal`,
  // and the user gets no route to their credentials -- which is the whole
  // reason ErrorKind separates auth from everything else.
  assert.equal(classifyError({ status: 403, message: "nope" } as never), "auth");
  assert.equal(classifyError({ status: 401, message: "nope" } as never), "auth");
});
