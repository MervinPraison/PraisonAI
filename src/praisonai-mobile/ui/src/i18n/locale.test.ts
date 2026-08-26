/**
 * Locale resolution and text direction.
 *
 * The guarantees: a regional tag finds its base language's table rather than
 * nothing; direction follows the SCRIPT and not a hand-written language list;
 * and no entry point throws on a tag that did not come from a BCP 47 parser --
 * a throw in a render path deciding page direction is a white screen.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { canonicalise, direction, isRtl, logicalInsets, resolveLocale } from "./locale.ts";

test("a regional tag resolves to the base language rather than to nothing", () => {
  // THE BUG: `supported.includes("en-GB")` is false, so a British user gets the
  // fallback locale -- or, in the version that indexes a table directly, a
  // screen of undefined. Most of the planet sends a regional tag.
  assert.equal(resolveLocale(["en-GB"], ["en", "de"], "en"), "en");
  assert.equal(resolveLocale(["pt-BR"], ["pt", "en"], "en"), "pt");
  assert.equal(resolveLocale(["zh-Hant-TW"], ["zh-Hant", "zh", "en"], "en"), "zh-Hant");
});

test("an exact match beats the prefix match, and order of preference is honoured", () => {
  // The pair: an implementation that always truncated to the language would
  // pass every assertion above and throw away zh-Hant vs zh-Hans, which are
  // not mutually readable.
  assert.equal(resolveLocale(["zh-Hant"], ["zh", "zh-Hant"], "en"), "zh-Hant");
  assert.equal(resolveLocale(["fr", "de"], ["de", "fr"], "en"), "fr");
});

test("an unsupported language falls back rather than returning the request", () => {
  // Returning "is" here is how a UI ends up rendering key paths: the caller
  // would look up a table that does not exist.
  assert.equal(resolveLocale(["is"], ["en", "de"], "en"), "en");
  assert.equal(resolveLocale([], ["en"], "en"), "en");
});

test("a malformed tag is skipped instead of throwing out of the resolver", () => {
  // A stored preference round-tripped through a POSIX or Java-shaped source
  // arrives as "en_US"; Intl.getCanonicalLocales rejects a truly broken one.
  assert.equal(resolveLocale(["!!", "de-DE"], ["de", "en"], "en"), "de");
  assert.equal(canonicalise("!!"), null);
  assert.equal(canonicalise("en_US"), "en-US", "an underscore tag is repaired, not discarded");
});

test("direction follows the script, so az-Arab is RTL and az is not", () => {
  // THE BUG a language list produces: Azerbaijani is written in both Latin and
  // Arabic script. Any `RTL = ["ar","he",...]` set gets one of the two wrong,
  // and gets ckb vs ku wrong, and gets every future script variant wrong.
  assert.equal(direction("az-Arab"), "rtl");
  assert.equal(direction("az"), "ltr");
  assert.equal(direction("ckb"), "rtl");
});

test("the obvious RTL and LTR languages are still classified correctly", () => {
  // The pair: an implementation returning "ltr" for everything passes the
  // az/az-Arab test above by accident on one of its two assertions.
  for (const tag of ["ar", "ar-EG", "he", "fa", "ur", "dv", "nqo"]) {
    assert.equal(direction(tag), "rtl", tag);
  }
  for (const tag of ["en", "en-GB", "de", "ja", "zh-Hant-TW", "ta"]) {
    assert.equal(direction(tag), "ltr", tag);
  }
  assert.equal(isRtl("he"), true);
  assert.equal(isRtl("en"), false);
});

test("direction never throws, whatever string it is handed", () => {
  // It is called to decide which way to lay the page out. An exception there
  // is a blank app, and the input can be a stored string from any source.
  for (const tag of ["", "!!", "en_US", "x", "-", "this is not a tag", "zz-ZZ-ZZ"]) {
    assert.doesNotThrow(() => direction(tag), tag);
    assert.ok(direction(tag) === "ltr" || direction(tag) === "rtl");
  }
});

test("physical insets map onto logical edges, and only swap for RTL", () => {
  // ui/src/layout/insets.ts hands out composerLeftPx/composerRightPx, which are
  // physical. A renderer writing padding-left: composerLeftPx puts the send
  // button's clearance on the wrong side of an Arabic screen.
  assert.deepEqual(logicalInsets("ltr", 12, 34), { startPx: 12, endPx: 34 });
  assert.deepEqual(logicalInsets("rtl", 12, 34), { startPx: 34, endPx: 12 });
});
