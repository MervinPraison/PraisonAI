/**
 * The formatters.
 *
 * Two of these are the whole reason the file exists: a cut that splits a
 * surrogate pair, and an unmeasured duration printed as zero. Both look correct
 * in ASCII and on a fast tool call, which is why they need tests rather than
 * review.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  UNKNOWN,
  firstLine,
  formatCount,
  formatElapsed,
  formatRelative,
  graphemes,
  truncate,
} from "./format.ts";

const EMOJI = "🙂";
/** Woman+woman+girl+boy: one grapheme, seven code points, eleven code units. */
const FAMILY = "👩‍👩‍👧‍👦";

/** Throws URIError on a lone surrogate, so it detects a split pair directly. */
const isWellFormed = (text: string): boolean => {
  try {
    encodeURIComponent(text);
    return true;
  } catch {
    return false;
  }
};

test("truncating a string of emoji never emits a broken code unit", () => {
  // `"🙂🙂🙂🙂".slice(0, 3)` splits the second pair and the phone paints U+FFFD.
  const cut = truncate(`${EMOJI}${EMOJI}${EMOJI}${EMOJI}`, 3);
  assert.equal(cut, `${EMOJI}${EMOJI}…`);
  assert.equal(isWellFormed(cut), true, "a surrogate pair was split");
  assert.equal(cut.includes("�"), false);
});

test("truncating keeps a ZWJ emoji sequence whole rather than beheading it", () => {
  // A family emoji cut anywhere inside renders as two to four separate people.
  const cut = truncate(`${FAMILY}abc`, 2);
  assert.equal(cut, `${FAMILY}…`);
  assert.equal(isWellFormed(cut), true);
});

test("a string that already fits is returned unchanged", () => {
  // The pair to the tests above: an implementation that always appended an
  // ellipsis would pass every "does not break" assertion and be useless.
  assert.equal(truncate(`${FAMILY}${FAMILY}`, 2), `${FAMILY}${FAMILY}`);
  assert.equal(truncate("short", 99), "short");
});

test("a non-positive or non-finite limit truncates to nothing instead of throwing", () => {
  // A measured width of 0 arrives during first layout; `slice(0, -1)` there
  // silently drops the last character of every label instead.
  assert.equal(truncate("hello", 0), "");
  assert.equal(truncate("hello", Number.NaN), "");
  assert.equal(truncate("hello", 1), "…");
});

test("a family emoji counts as one grapheme, not eleven code units", () => {
  assert.equal(graphemes(FAMILY).length, 1);
  assert.equal(FAMILY.length, 11, "the naive length that would have been used");
});

test("an unmeasured duration renders differently from a zero one", () => {
  // THE RULE. `tool_result.seconds` is null when the engine never saw the call
  // begin; printing "0.0s" asserts a measurement that was never taken.
  assert.equal(formatElapsed(null), UNKNOWN);
  assert.equal(formatElapsed(0), "0.0s");
  assert.notEqual(formatElapsed(null), formatElapsed(0));
});

test("a measured duration is actually formatted rather than always unknown", () => {
  // The pair: an implementation returning UNKNOWN for everything passes the
  // test above and tells the user nothing.
  assert.equal(formatElapsed(1.24), "1.2s");
  assert.equal(formatElapsed(42), "42s");
  assert.equal(formatElapsed(59.6), "1m 00s", "rounding must not print 60s");
  assert.equal(formatElapsed(3725), "1h 02m");
});

test("a negative or non-finite duration is unknown, never a negative label", () => {
  // A clock that stepped backwards mid-call produces this, and "-3.0s" is a
  // number the user cannot act on.
  assert.equal(formatElapsed(-1), UNKNOWN);
  assert.equal(formatElapsed(Number.NaN), UNKNOWN);
  assert.equal(formatElapsed(Number.POSITIVE_INFINITY), UNKNOWN);
});

test("a count is abbreviated without ever printing a promoted unit wrongly", () => {
  // 999_999 / 1000 rounds to "1000.0k", which is wider than the number it was
  // meant to shorten.
  assert.equal(formatCount(999), "999");
  assert.equal(formatCount(1000), "1.0k");
  assert.equal(formatCount(999_999), "1.0M");
  assert.equal(formatCount(1_500_000), "1.5M");
});

test("a non-finite count is unknown rather than the string NaN", () => {
  // usage.chars arrives from the wire; a decoder gap must not paint "NaN".
  assert.equal(formatCount(Number.NaN), UNKNOWN);
  assert.equal(formatCount(-5), UNKNOWN);
});

test("a timestamp in the future reads as just now, never as negative time", () => {
  // Clock skew between the write and the read is normal on a phone that slept.
  assert.equal(formatRelative(5_000, 0), "just now");
});

test("elapsed time is still reported for a timestamp in the past", () => {
  // The pair: clamping everything to "just now" would hide the whole column.
  const now = 1_000_000_000_000;
  assert.equal(formatRelative(now - 120_000, now), "2m ago");
  assert.equal(formatRelative(now - 7_200_000, now), "2h ago");
  assert.equal(formatRelative(now - 172_800_000, now), "2d ago");
  assert.equal(formatRelative(0, now).length, 10, "falls back to an ISO date");
});

test("a preview takes the first line without splitting on a missing newline", () => {
  assert.equal(firstLine("one\ntwo"), "one");
  assert.equal(firstLine("only"), "only");
});
