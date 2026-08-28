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

import { canonicalise, direction, isRtl, logicalInsets, resolveLocale, directionFromTables } from "./locale.ts";

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

// ---- the degraded host: no Intl.Locale.textInfo -----------------------------
//
// `direction()` is `directionFromIntl(tag) ?? directionFromTables(tag)`, and
// the test host is a Node with full ICU where the first half always answers.
// So the second half -- the branch that runs on an older Android WebView --
// never ran under test, and a mutation sweep found five indistinguishable
// mutations in it. These call it directly.

test("the fallback tables lay out the RTL languages right to left", () => {
  // Mutating the RTL_LANGUAGES membership test made Arabic, Hebrew, Farsi and
  // Urdu render LTR on exactly the devices most likely to hit this path.
  for (const tag of ["ar", "he", "fa", "ur", "ps", "sd"]) {
    assert.equal(directionFromTables(tag), "rtl", `${tag} must be rtl`);
  }
});

test("the fallback tables lay out everything else left to right", () => {
  // The pair. A table that answered "rtl" for everything passes the test above
  // and makes an English UI unusable, which locale.ts calls out as the
  // asymmetry that decides the default.
  for (const tag of ["en", "fr", "ja", "zh-Hans", "ru", "hi", "tr"]) {
    assert.equal(directionFromTables(tag), "ltr", `${tag} must be ltr`);
  }
});

test("a script subtag beats the language, in both directions", () => {
  // `az` and `ku` are LTR languages written in an RTL script, and `ar` and `ks`
  // are RTL languages written in an LTR one. Dropping the title-casing of the
  // script subtag made the first pair render LTR; changing the four-letter
  // length test made the second pair render RTL.
  assert.equal(directionFromTables("az-Arab"), "rtl", "an RTL script wins over an LTR language");
  assert.equal(directionFromTables("ku-Arab"), "rtl");
  assert.equal(directionFromTables("ar-Latn"), "ltr", "an LTR script wins over an RTL language");
  assert.equal(directionFromTables("ks-Deva"), "ltr");
});

test("the script subtag is matched case-insensitively", () => {
  // A wire tag is not guaranteed to be canonically cased.
  assert.equal(directionFromTables("az-arab"), "rtl");
  assert.equal(directionFromTables("az-ARAB"), "rtl");
});

test("a region subtag is not mistaken for a script", () => {
  // Regions are two letters or three digits; scripts are four letters. Reading
  // a region as a script would decide direction from the wrong subtag.
  assert.equal(directionFromTables("ar-EG"), "rtl", "a region must not override the language");
  assert.equal(directionFromTables("en-US"), "ltr");
  assert.equal(directionFromTables("ar-001"), "rtl");
});

test("the fallback never throws, whatever it is handed", () => {
  // It is the total half of a total function: `direction()` promises to always
  // answer, and this is what it falls back to.
  for (const tag of ["", "-", "x", "en_US", "!!!", "a-b-c-d-e"]) {
    assert.doesNotThrow(() => directionFromTables(tag), `threw on ${JSON.stringify(tag)}`);
  }
});

test("the fallback tables agree with Intl across a corpus of real tags", (t) => {
  // The test that finds the NEXT drift, rather than the thirteen languages
  // that were missing when it was written.
  //
  // `direction()` prefers `Intl.Locale.textInfo` and falls back to these
  // tables, so a tag the tables get wrong is invisible on every host that has
  // textInfo -- which is every host a test runs on. The only way to see it is
  // to ask both and compare. Thirteen disagreed: Baluchi, Rohingya, Saraiki,
  // Luri, Mazanderani, Gilaki, Hazaragi and five spoken Arabic varieties, all
  // rendering the whole UI left to right on the older WebViews that reach the
  // fallback.
  //
  // Skips tags this Node cannot answer for, so a small-ICU build reports
  // nothing rather than failing for the wrong reason.
  const CORPUS = [
    "ar", "he", "fa", "ur", "ps", "sd", "yi", "dv", "ckb", "ug", "syr", "nqo",
    "ks", "pnb", "arc", "bal", "rhg", "aeb", "ary", "arz", "apc", "acm", "ajp",
    "skr", "lrc", "mzn", "glk", "haz",
    "en", "fr", "de", "es", "pt", "it", "nl", "ru", "uk", "pl", "tr", "hi",
    "bn", "ta", "th", "vi", "id", "ja", "ko", "zh-Hans", "zh-Hant", "sw", "am",
  ];

  const disagreements: string[] = [];
  let compared = 0;
  for (const tag of CORPUS) {
    let fromIntl: string | null = null;
    try {
      const locale = new Intl.Locale(tag) as unknown as {
        readonly textInfo?: { readonly direction?: string };
      };
      fromIntl = locale.textInfo?.direction ?? null;
    } catch {
      fromIntl = null;
    }
    if (fromIntl === null) continue; // this Node cannot answer; not a failure
    compared += 1;
    const fromTables = directionFromTables(tag);
    if (fromIntl !== fromTables) disagreements.push(`${tag}: Intl=${fromIntl} tables=${fromTables}`);
  }

  // A small-ICU build answers `textInfo` for few tags or none. That is not a
  // drift, so the test SKIPS rather than fails -- as the header promises. The
  // threshold catches the different failure of a full-ICU host that somehow
  // compared almost nothing, which would mean the corpus stopped exercising
  // the tables. Below it we cannot tell the two apart, so we skip.
  if (compared <= 20) {
    t.skip(`only ${compared} tags were comparable; treating as a limited-ICU host`);
    return;
  }
  assert.deepEqual(disagreements, [], "the fallback tables have drifted from Intl");
});
