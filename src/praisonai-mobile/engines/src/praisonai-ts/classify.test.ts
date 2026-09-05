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
  // The line above does NOT hold the `authentication` alternative: it also
  // matches `invalid[ _-]?x?-?api[ _-]?key`, so deleting `authentication`
  // from the regex survived it. These match that alternative and nothing
  // else -- the exact regression the source comment records as fixed.
  ["anthropic auth, no key phrase", new Error("authentication_error"), "auth"],
  ["authentication, spelled out", new Error("Authentication Error"), "auth"],
  ["authentication failed", new Error("Authentication failed for the request"), "auth"],
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

/**
 * The message a fresh install actually gets, byte for byte.
 *
 * This is the app's most likely failure by a wide margin -- it is what the very
 * first message of a new install does, before anyone has been to Settings --
 * and it classified as `internal`, whose recovery is `none`. The one error
 * whose entire answer is "open Settings and paste a key" offered no route to
 * settings, which is the outcome the docstring at the top of classify.ts says
 * the function exists to prevent.
 *
 * Reproduced on an Android 35 emulator before the fix: a fresh install, no key,
 * one message, and the transcript rendered this sentence and nothing else.
 *
 * It reaches none of the older alternatives, which is why it was missed --
 * `unauthor`, `forbidden` and `authentication` do not occur in it; `no api key`
 * does not either (it says "is missing or empty", and the only "no" nearby is
 * inside neither phrase); and `api key not` needs "not" straight after "key".
 */
const MISSING_OPENAI_KEY =
  "The OPENAI_API_KEY environment variable is missing or empty; either provide it, " +
  "or instantiate the OpenAI client with an apiKey option, like new OpenAI({ apiKey: 'My API Key' }).";

test("a key that was never SET is an auth failure, not an internal one", () => {
  assert.equal(classifyError(new Error(MISSING_OPENAI_KEY)), "auth");
});

test("the other providers' ways of saying the same thing are auth too", () => {
  assert.equal(
    classifyError(new Error("The ANTHROPIC_API_KEY environment variable is missing or empty")),
    "auth",
  );
  assert.equal(
    classifyError(new Error("GOOGLE_GENERATIVE_AI_API_KEY environment variable is not set")),
    "auth",
  );
  assert.equal(classifyError(new Error("API key is missing")), "auth");
  assert.equal(classifyError(new Error("Missing credentials")), "auth");
});

test("the missing-key patterns do not swallow unrelated failures -- the pair", () => {
  // Without this, a regex broad enough to catch the sentence above would be
  // free to catch everything, and every `retry`/`none` recovery in the app
  // would quietly become "open settings". The gap between "api key" and the
  // word that qualifies it is bounded by `[^.;]`, and each of these either has
  // no key phrase at all or puts a sentence boundary in between.
  assert.equal(classifyError(new Error("The server had an error while processing your request")), "internal");
  assert.equal(classifyError(new Error("something went sideways")), "internal");
  assert.equal(classifyError(new Error("fetch failed")), "transport");
  assert.equal(classifyError(new Error("429 Rate limit reached for gpt-4o")), "rate_limit");
  // The one that matters most: the model answered nothing. Its recovery is
  // `retry`, and sending that user to Settings to check a key that is fine
  // would be the same defect pointing the other way.
  assert.equal(classifyError(new Error("The model produced an empty response")), "internal");
});
