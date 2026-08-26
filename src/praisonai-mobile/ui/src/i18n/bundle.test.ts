/**
 * Bundle assembly and the missing-key strategy.
 *
 * The guarantee: a key a translation forgot NEVER renders blank and never
 * renders a key path. It falls back to English, and the fall-through is
 * reported as data so CI can fail on it and marked in the text so a developer
 * running the app sees it without reading a log.
 *
 * The bug: an i18n layer that returns "" for a missing key produces a button
 * with no label. Nothing throws, nothing logs, and a screen reader announces it
 * as "button" -- in a language nobody on the team reads.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { createBundle, describeBundle, enBundle, isComplete, isMarked, markMissing } from "./bundle.ts";
import { en, stringKeys, type Strings } from "./strings.ts";

test("a missing key falls back to real English text, never to blank", () => {
  // THE BUG. An empty label is invisible to the developer and unusable for the
  // user, and it is what most "return the key or empty string" layers do.
  const bundle = createBundle("de", { routeChats: "Chats" });
  assert.notEqual(bundle.strings.stopped, "");
  assert.ok(bundle.strings.stopped.includes(en.stopped), "the English word must survive");
  assert.notEqual(bundle.strings.approvalQuestion("bash"), "");
  assert.ok(bundle.strings.approvalQuestion("bash").includes("bash"));
});

test("a missing key is marked so the fall-through is visible while developing", () => {
  // Reported in data AND visible on screen. The data catches it in CI; the
  // marker catches it in the hands of whoever is doing the translation.
  const bundle = createBundle("de", { routeChats: "Chats" });
  assert.equal(isMarked(bundle.strings.stopped), true);
  assert.equal(isMarked(bundle.strings.approvalQuestion("bash")), true);
  assert.ok(bundle.missing.includes("stopped"));
  assert.equal(bundle.missing.includes("routeChats"), false);
});

test("a supplied key is used verbatim and is not marked", () => {
  // The pair: an implementation that marked everything would pass every
  // assertion above and make a finished translation unreadable.
  const bundle = createBundle("de", { routeChats: "Unterhaltungen" });
  assert.equal(bundle.strings.routeChats, "Unterhaltungen");
  assert.equal(isMarked(bundle.strings.routeChats), false);
});

test("a complete translation reports complete and marks nothing", () => {
  const bundle = createBundle("en-GB", en);
  assert.equal(isComplete(bundle), true);
  assert.deepEqual(bundle.missing, []);
  assert.equal(bundle.strings.stopped, en.stopped);
  assert.equal(isMarked(bundle.strings.stopped), false);
});

test("silent mode is available but is NOT the default", () => {
  // The whole point of the file. A silent default is how a half-finished
  // translation ships without anybody noticing.
  const marked = createBundle("de", {});
  const silent = createBundle("de", {}, "silent");
  assert.equal(isMarked(marked.strings.stopped), true);
  assert.equal(silent.strings.stopped, en.stopped);
  // Silent still REPORTS: the text is quiet, the data is not.
  assert.ok(silent.missing.length > 0);
});

test("throw mode refuses to build an incomplete bundle at all", () => {
  // For a release gate that would rather fail the build than ship half a
  // language. The message names the keys, so the failure is actionable.
  assert.throws(
    () => createBundle("de", { routeChats: "Chats" }, "throw"),
    (error: unknown) => error instanceof Error && error.message.includes("stopped"),
  );
  assert.doesNotThrow(() => createBundle("en", en, "throw"));
});

test("a key supplied with the wrong shape is caught here, not at the call site", () => {
  // A translation round-tripped through JSON can turn a function into a
  // string. Calling it would throw "is not a function" from inside a render;
  // here it is a reported mismatch with a working fallback.
  const broken = { approvalQuestion: "Allow?" } as unknown as Partial<Strings>;
  const bundle = createBundle("de", broken);
  assert.ok(bundle.mismatched.includes("approvalQuestion"));
  assert.equal(typeof bundle.strings.approvalQuestion, "function");
  assert.ok(bundle.strings.approvalQuestion("bash").includes("bash"));
});

test("every key of the interface is produced, whatever the translation omits", () => {
  // The table is driven by en's keys, not the translation's, so a translation
  // that is 3% done still yields a table with 100% of the keys present.
  const bundle = createBundle("de", {});
  const keys = stringKeys();
  assert.ok(keys.length > 30, "the table should actually enumerate the product");
  for (const key of keys) {
    const value = (bundle.strings as unknown as Record<string, unknown>)[key];
    assert.ok(typeof value === "string" || typeof value === "function", key);
    if (typeof value === "string") assert.notEqual(value, "", key);
  }
});

test("an extra key from an older translation does not reach the table", () => {
  const bundle = createBundle("de", { legacyKey: "x" } as unknown as Partial<Strings>);
  assert.equal((bundle.strings as unknown as Record<string, unknown>)["legacyKey"], undefined);
});

test("the direction travels with the bundle", () => {
  assert.equal(createBundle("ar", {}).direction, "rtl");
  assert.equal(enBundle.direction, "ltr");
  assert.equal(enBundle.locale, "en");
});

test("the report reads as a sentence a human can act on", () => {
  assert.ok(describeBundle(enBundle).includes("complete"));
  assert.ok(describeBundle(createBundle("de", {})).includes("missing"));
  assert.equal(markMissing("Stopped"), "⟦Stopped⟧");
});
