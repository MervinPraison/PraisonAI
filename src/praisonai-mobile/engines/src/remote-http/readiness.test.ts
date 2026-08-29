/**
 * The readiness classifier.
 *
 * Ported from src-tauri/src/health.rs's own test module, keeping its test names
 * so a divergence between the Rust and the TS shows up as the same-named test
 * failing on one side only.
 *
 * The case that matters most is `http_200_with_ok_false_is_not_ready`. Every
 * other test here would pass against `classify = () => ready`, and a client
 * that trusts the status code routes a user's chat into a broken engine and
 * then reports the nonsense that comes back as a model failure.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { classify, type Probe } from "./readiness.ts";
import { PROTOCOL_VERSION } from "../../../protocol/src/version.ts";

const http = (status: number, body: string): Probe => ({ kind: "http", status, body });
const ok = (extra: Record<string, unknown> = {}): Probe =>
  http(200, JSON.stringify({ ok: true, version: PROTOCOL_VERSION, ...extra }));

test("a_healthy_body_is_ready", () => {
  const verdict = classify(ok());
  assert.equal(verdict.ready, true);
  assert.equal(verdict.ready === true && verdict.protocol, PROTOCOL_VERSION);
});

test("http_200_with_ok_false_is_not_ready", () => {
  // THE RULE. The engine reports failure with a 200 and ok:false, so status
  // alone is not readiness.
  const verdict = classify(http(200, JSON.stringify({ ok: false, version: PROTOCOL_VERSION })));
  assert.equal(verdict.ready, false);
  assert.equal(verdict.ready === false && verdict.reason, "unhealthy");
});

test("a_missing_ok_field_is_not_read_as_healthy", () => {
  // Absent must never be mistaken for present. `body.ok !== true` rather than
  // `body.ok === false`, so `{}` and `{ok: "yes"}` are both refused.
  //
  // Every body here carries a VALID version, and the reason is asserted rather
  // than just `ready === false`. The first version of this test did neither,
  // and `body.ok !== true` -> `!body.ok` survived it: `{ok: "yes"}` and
  // `{ok: 1}` are truthy, so they fell through to the version check and were
  // refused as `version_mismatch` instead. The assertion held for the wrong
  // reason, which is the same as not holding.
  const truthyButNotTrue = [
    { ok: "yes" }, { ok: 1 }, { ok: "false" }, { ok: {} }, { ok: [] }, { ok: "true" },
  ];
  for (const partial of truthyButNotTrue) {
    const body = { ...partial, version: PROTOCOL_VERSION };
    const verdict = classify(http(200, JSON.stringify(body)));
    assert.equal(verdict.ready, false, `${JSON.stringify(body)} must not be ready`);
    assert.equal(
      verdict.ready === false && verdict.reason,
      "unhealthy",
      `${JSON.stringify(body)} must be refused as UNHEALTHY, not for some later reason`,
    );
  }
  // And the falsy-or-absent ones, which the mutant does still catch.
  for (const partial of [{}, { ok: null }, { ok: false }, { ok: 0 }]) {
    const body = { ...partial, version: PROTOCOL_VERSION };
    const verdict = classify(http(200, JSON.stringify(body)));
    assert.equal(verdict.ready === false && verdict.reason, "unhealthy", JSON.stringify(body));
  }
});

test("an_unhealthy_engine_is_worth_retrying", () => {
  // `retryable: true` -> `false` survived. An engine still binding its socket
  // is declared permanently dead, so a connection manager stops polling and
  // the user never gets a working engine without restarting the app.
  const verdict = classify(http(200, JSON.stringify({ ok: false, version: PROTOCOL_VERSION })));
  assert.equal(verdict.ready === false && verdict.retryable, true);
});

test("a_healthy_engine_IS_ready_-_the_pair", () => {
  // Without this, a classify() that refused everything would satisfy every
  // negative case above.
  const verdict = classify(http(200, JSON.stringify({ ok: true, version: PROTOCOL_VERSION })));
  assert.equal(verdict.ready, true);
});

test("a_transport_failure_is_retryable_because_the_engine_may_still_be_binding", () => {
  const verdict = classify({ kind: "transport", detail: "ECONNREFUSED" });
  assert.equal(verdict.ready, false);
  assert.equal(verdict.ready === false && verdict.reason, "transport");
  assert.equal(verdict.ready === false && verdict.retryable, true);
});

test("a_version_mismatch_is_never_retryable_because_it_cannot_fix_itself", () => {
  // The distinction health.rs was written to preserve. Retrying a permanent
  // refusal on a phone is a battery bug.
  const verdict = classify(http(200, JSON.stringify({ ok: true, version: 1 })));
  assert.equal(verdict.ready, false);
  assert.equal(verdict.ready === false && verdict.reason, "version_mismatch");
  assert.equal(verdict.ready === false && verdict.retryable, false);
});

test("a_transport_failure_and_a_version_mismatch_do_not_share_a_reason", () => {
  // The pair that forbids collapsing them. If both mapped to one reason the
  // supervisor could only retry both or neither, and one of those is wrong.
  const transport = classify({ kind: "transport", detail: "x" });
  const mismatch = classify(http(200, JSON.stringify({ ok: true, version: 1 })));
  assert.notEqual(
    transport.ready === false && transport.reason,
    mismatch.ready === false && mismatch.reason,
  );
  assert.notEqual(
    transport.ready === false && transport.retryable,
    mismatch.ready === false && mismatch.retryable,
  );
});

test("a_missing_version_is_unreadable_not_assumed_current", () => {
  const verdict = classify(http(200, JSON.stringify({ ok: true })));
  assert.equal(verdict.ready, false);
  assert.equal(verdict.ready === false && verdict.reason, "version_mismatch");
  assert.match(verdict.ready === false ? verdict.detail : "", /unreadable/);
});

test("a_non_200_status_is_not_ready", () => {
  for (const status of [404, 500, 502, 301]) {
    const verdict = classify(http(status, "{}"));
    assert.equal(verdict.ready, false, `${status} must not be ready`);
    assert.equal(verdict.ready === false && verdict.reason, "http_status");
  }
});

test("a_body_that_is_not_json_is_malformed_and_never_throws", () => {
  // A captive portal, a proxy error page, or a different service on the port.
  // The classifier must report, not throw.
  for (const body of ["<html>Not Found</html>", "", "null", "[]", "42"]) {
    assert.doesNotThrow(() => classify(http(200, body)));
    const verdict = classify(http(200, body));
    assert.equal(verdict.ready, false, `${JSON.stringify(body)} must not be ready`);
  }
});

test("a_newer_engine_is_ready_because_unknown_events_are_ignored", () => {
  // Forward compatibility is structural: decode.ts skips names and fields it
  // does not know, so a newer engine can only add things we ignore.
  const verdict = classify(http(200, JSON.stringify({ ok: true, version: PROTOCOL_VERSION + 3 })));
  assert.equal(verdict.ready, true);
});

test("the_classifier_can_actually_refuse", () => {
  // Positive control. Every other test above passes against a classifier that
  // always returns ready; this one, paired with a_healthy_body_is_ready,
  // forbids both always-yes and always-no.
  const healthy = classify(ok());
  const broken = classify(http(200, JSON.stringify({ ok: false })));
  assert.equal(healthy.ready, true);
  assert.equal(broken.ready, false);
});

test("any status that is not exactly 200 is an http_status failure", () => {
  // `probe.status !== 200` -> `> 200` survived: a sub-200 status (100, 101,
  // 199) would fall through and be classified from its BODY, so a websocket
  // upgrade or a "continue" reported `ready: true`. The engine would then be
  // offered as usable and every request to it fail.
  const body = JSON.stringify({ ok: true, version: PROTOCOL_VERSION });
  for (const status of [100, 101, 199, 201, 204, 301, 404, 500, 503]) {
    const verdict = classify(http(status, body));
    assert.equal(verdict.ready, false, `HTTP ${status} must not read as ready`);
    assert.equal(
      verdict.ready === false ? verdict.reason : null,
      "http_status",
      `HTTP ${status} must be a status failure, not classified from its body`,
    );
  }
});

test("a 200 is still classified from its body, so the status test is not vacuous", () => {
  assert.equal(classify(ok()).ready, true);
});
