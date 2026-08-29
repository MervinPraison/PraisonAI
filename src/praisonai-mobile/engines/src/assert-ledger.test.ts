/**
 * The ledger is load-bearing -- every assertion count in the engine contract is
 * only as trustworthy as this proxy -- and it had no test of its own. Removing
 * `made += 1` from the `apply` trap survived the whole engines suite, because
 * no contract happens to use a bare `assert(x)`. That is not a harmless gap:
 * the day someone writes one it goes uncounted, and the committed constant for
 * that case is quietly wrong from then on.
 *
 * Every ledger's `assert` is bound to an explicitly annotated local. TS2775
 * refuses an `asserts` signature reached through a property chain, which is
 * also why the contracts declare theirs rather than destructuring.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { ledger, type Ledger } from "./assert-ledger.ts";

test("a namespace call is counted", () => {
  const l = ledger();
  const counted: Ledger["assert"] = l.assert;
  assert.equal(l.made(), 0, "a fresh ledger has counted nothing");
  counted.equal(1, 1);
  counted.ok(true);
  assert.equal(l.made(), 2);
});

test("a BARE assert(x) is counted too", () => {
  // `assert` is both callable and a namespace of callables. Counting only the
  // namespace leaves a whole style of assertion invisible to the ledger --
  // measured: dropping the apply trap's counter survived the entire suite.
  const l = ledger();
  const counted: Ledger["assert"] = l.assert;
  counted(true);
  counted(1 === 1);
  assert.equal(l.made(), 2, "the apply trap must count");
});

test("a FAILING assertion still throws, and is still counted", () => {
  // A proxy that swallowed the throw would turn every contract green.
  const l = ledger();
  const counted: Ledger["assert"] = l.assert;
  assert.throws(() => counted.equal(1, 2), /Expected values to be strictly equal/);
  assert.throws(() => counted(false));
  assert.equal(l.made(), 2, "an assertion that fails is an assertion that ran");
});

test("the message reaches the thrown error", () => {
  // The proxy forwards every argument, not just the first two.
  const l = ledger();
  const counted: Ledger["assert"] = l.assert;
  assert.throws(
    () => counted.equal(1, 2, "the message survives the proxy"),
    /the message survives the proxy/,
  );
  // The bare form takes a message too, and truncating the apply trap's
  // arguments to one survived until this line existed -- a failing
  // `assert(cond, "why")` would then report nothing about why.
  assert.throws(() => counted(false, "the bare form keeps its message"), /the bare form keeps its message/);
});

test("a non-function property is passed through, not wrapped", () => {
  // Dropping the `typeof value !== "function"` guard survived a first version
  // of this test, which read `assert.AssertionError` -- a class, so a function
  // either way. `name` and `length` are the properties that actually
  // distinguish the two: without the guard they come back as arrow functions,
  // and anything reading them gets a function where it expected a string.
  const l = ledger();
  const counted: Ledger["assert"] = l.assert;
  assert.equal(counted.name, "strict", "a string property must survive as a string");
  assert.equal(typeof counted.length, "number");
  assert.equal(l.made(), 0, "reading a property is not making an assertion");
});

test("two ledgers count independently", () => {
  // Each describeXContract call takes its own, and one file runs the same
  // contract against several adapters. A shared counter would make every count
  // after the first wrong.
  const first = ledger();
  const second = ledger();
  const a: Ledger["assert"] = first.assert;
  const b: Ledger["assert"] = second.assert;
  a.ok(true);
  a.ok(true);
  b.ok(true);
  assert.equal(first.made(), 2);
  assert.equal(second.made(), 1);
});

test("made() is a snapshot, not a live binding", () => {
  // Every case in the engine contract opens with `const made0 = made()` and
  // closes by differencing it. If that read tracked the counter, the
  // difference would always be zero and every count would pass.
  const l = ledger();
  const counted: Ledger["assert"] = l.assert;
  const before = l.made();
  counted.ok(true);
  assert.equal(before, 0, "the earlier read must not have moved");
  assert.equal(l.made(), 1);
});
