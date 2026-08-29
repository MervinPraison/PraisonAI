/**
 * The version gate.
 *
 * The only way a version gate is ever wrong is by always saying yes or always
 * saying no, so every test here comes in a pair that forbids one of those. A
 * `checkProtocol = () => ({ok: true})` must fail this file, and so must
 * `() => ({ok: false})`.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { checkProtocol, FEATURES, PROTOCOL_VERSION, MIN_ENGINE_PROTOCOL } from "./version.ts";

test("an engine older than the minimum is refused, and the refusal is not retryable", () => {
  const verdict = checkProtocol(MIN_ENGINE_PROTOCOL - 1);
  assert.equal(verdict.ok, false);
  assert.equal(verdict.ok === false && verdict.reason, "too_old");
  // The reason must be distinguishable from a transport failure, because one is
  // worth retrying and the other will never fix itself.
  assert.notEqual(verdict.ok === false && verdict.reason, "unreadable");
});

test("an engine at the current version is accepted with nothing degraded", () => {
  // The other half of the pair: this forbids a gate that always refuses.
  const verdict = checkProtocol(PROTOCOL_VERSION);
  assert.equal(verdict.ok, true);
  assert.deepEqual(verdict.ok === true && verdict.degraded, []);
});

test("an engine newer than us is accepted, because unknown events are ignored", () => {
  // Forward compatibility is structural: decode.ts skips names and fields it
  // does not know, so a newer engine can only add things we ignore. Refusing
  // would strand every shipped client the day the engine ships first.
  const verdict = checkProtocol(PROTOCOL_VERSION + 5);
  assert.equal(verdict.ok, true);
});

test("an engine that cannot state its version is unreadable, not assumed current", () => {
  // A missing field must never read as a present one.
  for (const bad of [undefined, null, "2", NaN, Infinity, 2.5, 0, -1, {}, []]) {
    const verdict = checkProtocol(bad);
    assert.equal(verdict.ok, false, `checkProtocol(${JSON.stringify(bad)}) should refuse`);
    assert.equal(
      verdict.ok === false && verdict.reason,
      "unreadable",
      `checkProtocol(${JSON.stringify(bad)}) should be unreadable`,
    );
  }
});

test("a version between the minimum and current is accepted with its gaps named", () => {
  // Degradation must be declared, not discovered by something quietly not
  // working. This asserts the mechanism even while every FEATURE is future.
  const verdict = checkProtocol(MIN_ENGINE_PROTOCOL);
  assert.equal(verdict.ok, true);
  assert.ok(Array.isArray(verdict.ok === true ? verdict.degraded : null));
});

test("the client version matches the desktop engine's PROTOCOL_VERSION", () => {
  // A cross-language contract check, in the style of src-tauri/src/reclaim.rs,
  // which asserts its fnv1a64 matches engine/server.py's. Two constants in two
  // languages that must agree, so the day one moves this fails rather than
  // producing an unknown-event storm at runtime.
  const here = dirname(fileURLToPath(import.meta.url));
  const serverPy = join(here, "../../../praisonai-desktop/engine/server.py");

  let source: string;
  try {
    source = readFileSync(serverPy, "utf8");
  } catch {
    // The desktop package may legitimately be absent in a mobile-only checkout.
    // Skipping is honest; asserting true would be a test that proves nothing.
    return;
  }

  const match = /^PROTOCOL_VERSION\s*=\s*(\d+)/m.exec(source);
  assert.notEqual(match, null, "could not find PROTOCOL_VERSION in engine/server.py");
  assert.equal(
    Number(match?.[1]),
    PROTOCOL_VERSION,
    "mobile and desktop disagree about the protocol version",
  );
});

test("no declared feature is newer than the version this client speaks", () => {
  // The invariant behind FEATURES being empty today. Reporting a capability as
  // degraded-on-this-engine when the client has not implemented it either
  // blames the engine for our own gap, and the UI would offer a fix that
  // cannot work. Add the entry in the same change that raises the version.
  for (const feature of FEATURES) {
    assert.ok(
      feature.since <= PROTOCOL_VERSION,
      `${feature.name} is since ${feature.since} but this client speaks ${PROTOCOL_VERSION}`,
    );
  }
});

test("an engine that cannot state its version reports ABSENT, not zero", () => {
  // `engine: null` -> `engine: 0` survived. The file's own rule is that a
  // missing field must never be mistaken for a present one; `0` is a present
  // number. It reaches the user as "unreadable: engine=0 expected=2", which
  // reads as an engine that answered rather than one that did not.
  for (const bad of [undefined, null, "2", 2.5, 0, -1, {}, Number.NaN]) {
    const compat = checkProtocol(bad);
    assert.equal(compat.ok, false, `${JSON.stringify(bad ?? null)} is not a version`);
    assert.equal(compat.ok === false && compat.engine, null, "absent must read as null");
    assert.equal(
      compat.ok === false && compat.expected,
      PROTOCOL_VERSION,
      "and it must still say what we require -- that is the actionable half",
    );
  }
});

test("a refusal states the version WE expect, not the one we got", () => {
  // `expected: PROTOCOL_VERSION` -> `expected: engine` survived. A too_old
  // refusal then reads "too_old: engine=1 expected=1" -- self-contradictory,
  // and this string is the one thing a user copies into a bug report.
  const compat = checkProtocol(1);
  assert.equal(compat.ok, false);
  assert.equal(compat.ok === false && compat.reason, "too_old");
  assert.equal(compat.ok === false && compat.engine, 1, "what the engine said");
  assert.equal(
    compat.ok === false && compat.expected,
    PROTOCOL_VERSION,
    "what we require -- and it must differ from what we got",
  );
  assert.notEqual(
    compat.ok === false && compat.expected,
    compat.ok === false && compat.engine,
    "a refusal that says expected === actual explains nothing",
  );
});
