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
  graphemePrefix,
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

// ---- segmenting only what is needed -----------------------------------------

test("graphemePrefix stops at the limit and says there was more", () => {
  const { parts, hasMore } = graphemePrefix("abcdef", 3);
  assert.deepEqual(parts, ["a", "b", "c"]);
  assert.equal(hasMore, true);
});

test("graphemePrefix reports no more when the text ends first", () => {
  // The pair. Always returning hasMore:true would make truncate append an
  // ellipsis to text that fits.
  const { parts, hasMore } = graphemePrefix("ab", 5);
  assert.deepEqual(parts, ["a", "b"]);
  assert.equal(hasMore, false);
});

test("graphemePrefix counts clusters, not code units", () => {
  const { parts, hasMore } = graphemePrefix("👩‍👩‍👧‍👦👍🏽🇬🇧", 2);
  assert.deepEqual(parts, ["👩‍👩‍👧‍👦", "👍🏽"]);
  assert.equal(hasMore, true);
});

test("truncating a long single line does work proportional to max, not to the input", () => {
  // `buildTranscript` re-derives every tool preview on EVERY publish, roughly
  // thirty times a second during a streaming answer. Segmenting the whole
  // string first meant one tool returning 40kB of single-line JSON cost ~10ms
  // per publish -- on a phone, 3-5x that, so the frame budget is gone on its
  // own. The earlier length check does not help: anything long always
  // overflows and always paid in full.
  //
  // Timed rather than counted because the segmenter is not injectable. The
  // margin is deliberately enormous -- measured 0.12ms after the fix and 48ms
  // before it, so this threshold has ~170x headroom yet still fails the
  // regression by more than 2x.
  const huge = "x".repeat(200_000);
  const started = performance.now();
  const out = truncate(huge, 120);
  const elapsed = performance.now() - started;

  assert.equal(out.length, 120, "120 clusters: 119 kept plus the ellipsis");
  assert.ok(out.endsWith("…"));
  assert.ok(
    elapsed < 20,
    `truncate took ${elapsed.toFixed(1)}ms on a 200kB line -- the whole string is being segmented again`,
  );
});

test("a long line still truncates to exactly the same text as before", () => {
  // The lazy path must be byte-identical to materialising everything. Verified
  // separately over 50,010 differential cases including ZWJ sequences, skin
  // tones, regional indicators and Devanagari conjuncts; this pins the shape.
  const line = "abcdef".repeat(1000);
  assert.equal(truncate(line, 10), line.slice(0, 9) + "…");
  assert.equal(truncate("👍🏽".repeat(500), 3), "👍🏽👍🏽…");
});

// ---- the boundaries between formats ----------------------------------------

test("formatElapsed switches format AT the boundary, not one past it", () => {
  // `seconds < 10` -> `<= 10` and `minutes < 60` -> `<= 60` both survived. The
  // whole point of the thresholds is which side of them a value falls on, and
  // no test placed a value exactly on one.
  assert.equal(formatElapsed(9.94), "9.9s", "under ten keeps the decimal");
  assert.equal(formatElapsed(10), "10s", "ten exactly is whole seconds");
  assert.equal(formatElapsed(59), "59s");
  assert.equal(formatElapsed(60), "1m 00s", "sixty seconds is a minute, not 60s");
  assert.equal(formatElapsed(3599), "59m 59s");
  assert.equal(formatElapsed(3600), "1h 00m", "sixty minutes is an hour, not 60m 00s");
  assert.equal(formatElapsed(7260), "2h 01m");
});

test("formatRelative's just-now threshold is 45 seconds exactly", () => {
  // `seconds < 45` -> `< 44` survived. The threshold is the whole contract of
  // the function, and no test placed a value on it. `format-intl.ts` has the
  // same boundary and is pinned separately -- the two must not drift.
  const now = 1_700_000_000_000;
  assert.match(formatRelative(now - 44_000, now), /just now/i, "44s is still just now");
  assert.doesNotMatch(formatRelative(now - 45_000, now), /just now/i, "45s is not");
  assert.doesNotMatch(formatRelative(now - 46_000, now), /just now/i);
});
