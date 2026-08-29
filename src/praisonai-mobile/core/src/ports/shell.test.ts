/**
 * The scheme allowlist, tested where it is defined.
 *
 * Both shells delegate to `isOpenableExternally` before handing a URL to the
 * OS, and the shared shell contract asserts each adapter refuses what it
 * refuses. Nothing tested the guard itself at its own boundary -- dropping the
 * `^` from its regex survived, so any string CONTAINING a permitted scheme
 * anywhere passed.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { isOpenableExternally } from "./shell.ts";

test("a scheme is only trusted at the START of the URL", () => {
  // Dropping the `^` from the scheme regex survived. Any string CONTAINING a
  // permitted scheme anywhere then passes: `/redirect?to=https://evil.example`
  // returns true, and so does `./rel?x=mailto:a@b`.
  //
  // This is the guard the whole file exists for -- both shells delegate to it
  // before handing a URL to the OS -- and a relative URL that smuggles an
  // allowed scheme in its query string is exactly the shape it must refuse.
  assert.equal(isOpenableExternally("/redirect?to=https://evil.example"), false);
  assert.equal(isOpenableExternally("./rel?x=mailto:a@b"), false);
  assert.equal(isOpenableExternally("//evil.example/https:"), false);
  assert.equal(isOpenableExternally("javascript:alert(1)#https:"), false);
  assert.equal(isOpenableExternally("  https://ok.example  "), true, "leading space is trimmed, not a bypass");
});

test("the refusal is about position, not about the word", () => {
  // The pair: a guard that refused anything containing "https" anywhere would
  // pass the test above and break every real link.
  assert.equal(isOpenableExternally("https://ok.example/path?next=https://other"), true);
  assert.equal(isOpenableExternally("mailto:a@b?subject=https://x"), true);
});

test("a scheme the model typed in capitals is still openable", () => {
  // Dropping `.toLowerCase()` survived. A model writes `HTTPS://example.com`
  // or `Mailto:a@b` -- both entirely legal per RFC 3986, which says schemes are
  // case-insensitive -- and the user taps the link and nothing happens.
  // It fails closed, so this is a dead link rather than a hole; a dead link
  // with no error is still the app appearing broken.
  assert.equal(isOpenableExternally("HTTPS://example.com"), true);
  assert.equal(isOpenableExternally("Mailto:a@b"), true);
  assert.equal(isOpenableExternally("TEL:+15551234"), true);
  // And the case-folding must not open anything new.
  assert.equal(isOpenableExternally("JAVASCRIPT:alert(1)"), false);
  assert.equal(isOpenableExternally("FILE:///etc/passwd"), false);
});
