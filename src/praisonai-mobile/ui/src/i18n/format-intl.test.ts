/**
 * The locale-aware formatters, and the boundary with the deterministic ones.
 *
 * The first guarantee is negative and is the reason this file exists at all:
 * ui/src/format.ts is UNCHANGED. Its tests assert literal strings, which is
 * only sound because it never asks the platform what locale or time zone it is
 * in. Adding localisation there would have made "a future timestamp never
 * renders as negative time" fail on an ICU upgrade, and a test that fails for
 * reasons unrelated to its rule gets deleted along with the rule.
 *
 * The rest of the guarantees: the two paths agree in en-US so they cannot
 * silently diverge; they genuinely differ elsewhere so the localisation is real
 * and not decorative; time zone is honoured rather than defaulted; and nothing
 * throws on a bad tag or a NaN off the wire.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  formatCountLocalised,
  formatDate,
  formatElapsedLocalised,
  formatNumber,
  formatRelativeFromStrings,
  formatRelativeLocalised,
  relativeParts,
} from "./format-intl.ts";
import { en } from "./strings.ts";
import { UNKNOWN, formatCount, formatElapsed, formatRelative } from "../format.ts";

const HOUR = 3_600_000;
const DAY = 86_400_000;
const NOW = Date.UTC(2021, 5, 15, 12, 0, 0);

test("format.ts still emits ISO and ASCII, exactly as its own tests assert", () => {
  // THE GUARANTEE. If this ever fails, the deterministic path has been
  // localised in place and every literal assertion in format.test.ts is now
  // dependent on the machine it runs on.
  assert.equal(formatRelative(NOW - 30 * DAY, NOW), "2021-05-16");
  assert.equal(formatRelative(NOW - 2 * HOUR, NOW), "2h ago");
  assert.equal(formatElapsed(1.24), "1.2s");
  assert.equal(formatCount(1_500_000), "1.5M");
  assert.equal(UNKNOWN, "—");
});

test("the localised duration path agrees with format.ts in en-US", () => {
  // Two implementations of one rule drift the moment one of them gains a case.
  // Pinning them together in the reference locale is what catches that.
  for (const seconds of [0, 1.24, 9.99, 42, 59.6, 3725]) {
    assert.equal(
      formatElapsedLocalised("en-US", en, seconds),
      formatElapsed(seconds),
      `seconds=${seconds}`,
    );
  }
  assert.equal(formatElapsedLocalised("en-US", en, null), UNKNOWN);
});

test("the localised duration path actually localises", () => {
  // The pair: an implementation that just called formatElapsed would satisfy
  // every assertion above and localise nothing.
  assert.equal(formatElapsedLocalised("de-DE", en, 1.24), "1,2s");
  assert.notEqual(formatElapsedLocalised("de-DE", en, 1.24), formatElapsed(1.24));
});

test("an unmeasured duration stays UNKNOWN and never becomes zero", () => {
  // `seconds: null` means the engine never observed the call begin. The
  // localised path must not lose that distinction on its way through Intl.
  assert.equal(formatElapsedLocalised("de-DE", en, null), en.unknownValue);
  assert.notEqual(formatElapsedLocalised("de-DE", en, null), formatElapsedLocalised("de-DE", en, 0));
  assert.equal(formatElapsedLocalised("en-US", en, -1), UNKNOWN);
  assert.equal(formatElapsedLocalised("en-US", en, Number.NaN), UNKNOWN);
});

test("padding uses the locale's own digits rather than an ASCII zero", () => {
  // `String(9).padStart(2, "0")` glues an ASCII zero onto an Arabic-Indic
  // numeral, so "09" is rendered in two different scripts.
  const arabic = formatElapsedLocalised("ar-EG", en, 69);
  assert.ok(arabic.includes("٠٩"), `expected Arabic-Indic padding, got ${arabic}`);
  assert.equal(arabic.includes("09"), false);
});

test("a count is abbreviated the way the locale abbreviates, not with a k/M table", () => {
  // Japanese groups by ten-thousands (万), which is a different SCALE and not
  // reachable by translating the suffix. German writes "Mio.".
  assert.equal(formatCountLocalised("en-US", 1_500_000), "1.5M");
  assert.equal(formatCountLocalised("ja-JP", 1_500_000), "150万");
  // Matched loosely on purpose: ICU puts a NARROW NO-BREAK SPACE before "Mio.",
  // and which invisible space it chooses has changed between ICU releases. An
  // equality assertion here would be exactly the brittle, locale-data-dependent
  // test that format.ts stays ISO to avoid.
  const german = formatCountLocalised("de-DE", 1_500_000);
  assert.ok(german.startsWith("1,5"), german);
  assert.ok(german.endsWith("Mio."), german);
});

test("relative time uses CLDR phrasing, including the forms a table gets wrong", () => {
  // "yesterday" is not "1 day ago", and Arabic has a dual form for exactly two
  // that no {n}-substitution template can produce.
  assert.equal(formatRelativeLocalised("en", en, NOW - DAY, NOW, "UTC"), "yesterday");
  assert.equal(formatRelativeLocalised("de", en, NOW - 3 * DAY, NOW, "UTC"), "vor 3 Tagen");
  assert.notEqual(
    formatRelativeLocalised("ar", en, NOW - 2 * HOUR, NOW, "UTC"),
    formatRelativeLocalised("en", en, NOW - 2 * HOUR, NOW, "UTC"),
  );
});

test("the thresholds are format.ts's, clamp included", () => {
  // A phone whose clock is behind the timestamp it wrote must not say "in -3
  // minutes" in any language, and the cutovers must not drift between the two
  // implementations.
  assert.deepEqual(relativeParts(NOW + 5000, NOW), { kind: "just-now" });
  assert.deepEqual(relativeParts(NOW - 44_000, NOW), { kind: "just-now" });
  assert.deepEqual(relativeParts(NOW - 120_000, NOW), { kind: "elapsed", unit: "minute", value: 2 });
  assert.deepEqual(relativeParts(NOW - 2 * HOUR, NOW), { kind: "elapsed", unit: "hour", value: 2 });
  assert.deepEqual(relativeParts(NOW - 30 * DAY, NOW), { kind: "date" });
  assert.deepEqual(relativeParts(Number.NaN, NOW), { kind: "unknown" });
});

test("the string-table fallback is a real path and produces real words", () => {
  // It is what makes minutesAgo/hoursAgo/daysAgo worth translating, and it is
  // reachable on a host with no Intl.RelativeTimeFormat. Tested directly rather
  // than by deleting a global out from under the rest of the file.
  assert.equal(
    formatRelativeFromStrings("en", en, relativeParts(NOW - 120_000, NOW), NOW, "UTC"),
    "2 minutes ago",
  );
  assert.equal(
    formatRelativeFromStrings("en", en, relativeParts(NOW - 60_000, NOW), NOW, "UTC"),
    "1 minute ago",
    "the singular must not read '1 minutes ago'",
  );
  assert.equal(formatRelativeFromStrings("en", en, { kind: "just-now" }, NOW, "UTC"), "just now");
  assert.equal(formatRelativeFromStrings("en", en, { kind: "unknown" }, NOW, "UTC"), UNKNOWN);
});

test("the time zone is honoured rather than defaulted to the host's", () => {
  // THE BUG a defaulted zone causes: a chat saved at 23:30 UTC shows tomorrow's
  // date to a user in Auckland, and a date test passes in London and fails in
  // Auckland for reasons nobody can reproduce.
  const lateUtc = Date.UTC(2021, 0, 1, 23, 30);
  assert.notEqual(
    formatDate("en-US", lateUtc, "UTC"),
    formatDate("en-US", lateUtc, "Pacific/Auckland"),
  );
  assert.ok(formatDate("en-US", lateUtc, "UTC").includes("2021"));
});

test("every entry point answers instead of throwing on a bad tag or a bad number", () => {
  // A throw inside a transcript row's formatter blanks the whole list, and both
  // inputs arrive from outside: the tag from stored settings, the number from
  // the wire.
  for (const tag of ["en_US", "!!", "", "zz"]) {
    assert.doesNotThrow(() => formatNumber(tag, 12.5), tag);
    assert.doesNotThrow(() => formatCountLocalised(tag, 1500), tag);
    assert.doesNotThrow(() => formatElapsedLocalised(tag, en, 42), tag);
    assert.doesNotThrow(() => formatDate(tag, NOW, "UTC"), tag);
    assert.doesNotThrow(() => formatRelativeLocalised(tag, en, NOW - HOUR, NOW, null), tag);
  }
  assert.equal(formatNumber("en", Number.NaN), UNKNOWN);
  assert.equal(formatCountLocalised("en", -1), UNKNOWN);
  assert.equal(formatDate("en", Number.NaN, "UTC"), UNKNOWN);
});
