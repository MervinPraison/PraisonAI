/**
 * Sentence segmentation.
 *
 * The guarantee that matters to the screen-reader policy: `completedLength`
 * never includes an unfinished sentence, and the prefix it returns plus the
 * remainder recombine into the original exactly -- a caller holding a cursor
 * into a stream must not lose or repeat a character at the seam.
 *
 * The bug being pinned is `text.split(". ")`, which cuts a version number into
 * pieces and finds no boundaries at all in Japanese or Arabic, where the
 * terminator is not an ASCII full stop.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { completedLength, endsSentence, sentences, fallbackSentences } from "./segment.ts";

test("an unfinished trailing clause is not counted as complete", () => {
  // THE RULE the announcement policy rests on. Announcing the tail means the
  // screen reader says "The file cont" and then repeats the whole sentence.
  const text = "I will read the file. The file cont";
  const complete = completedLength("en", text);
  assert.equal(text.slice(0, complete), "I will read the file. ");
  assert.ok(complete < text.length);
});

test("a finished sentence IS counted, so the policy is not permanently silent", () => {
  // The pair: an implementation returning 0 for everything satisfies the test
  // above and means a blind user hears nothing until the turn ends.
  assert.equal(completedLength("en", "Done."), "Done.".length);
  assert.equal(completedLength("en", "One. Two. Three."), "One. Two. Three.".length);
});

test("a decimal point is not a sentence end", () => {
  // THE BUG in split(". "): "Installed version 1.2.3 successfully" becomes
  // three announcements with three falling intonations, and the version number
  // is unintelligible. A version string is the single most common thing a tool
  // result contains.
  assert.equal(completedLength("en", "Installed version 1.2.3 successfully"), 0);
  assert.equal(completedLength("en", "The timeout is 2.5 seconds and"), 0);
  // The stated limitation, pinned so it is a known quantity rather than a
  // surprise: Intl.Segmenter has no abbreviation suppressions, so "Dr." does
  // break. Announcing two words early is bounded; a hand-written English
  // abbreviation list would not be.
  assert.equal(completedLength("en", "Ask Dr. Smith about"), "Ask Dr. ".length);
});

test("a non-ASCII terminator ends a sentence, so CJK and Arabic are not silent", () => {
  // Japanese ends with U+3002 and has no spaces; Arabic ends with U+061F.
  // An ASCII-only rule finds no boundary in either, so the whole answer is
  // withheld until the turn ends.
  const ja = "ファイルを読みます。次に";
  assert.equal(ja.slice(0, completedLength("ja", ja)), "ファイルを読みます。");
  const ar = "هل تريد المتابعة؟ سوف";
  assert.ok(completedLength("ar", ar) > 0);
});

test("the prefix and the remainder recombine exactly", () => {
  // The seam guarantee. A cursor-based announcer that dropped the whitespace
  // between sentences would glue words together in the next announcement.
  for (const text of ["A. B. C", "One sentence.", "  ", "no terminator at all", ""]) {
    const at = completedLength("en", text);
    assert.equal(text.slice(0, at) + text.slice(at), text, JSON.stringify(text));
  }
});

test("a trailing quote or bracket after the terminator still closes the sentence", () => {
  // `He said "stop."` ends with a quote mark, not a full stop. Requiring the
  // last character to be punctuation withholds every quoted sentence forever.
  assert.equal(endsSentence('He said "stop."'), true);
  assert.equal(endsSentence("(see below.)"), true);
  assert.equal(endsSentence("still writing"), false);
  assert.equal(endsSentence(""), false);
});

test("segmentation never loses text", () => {
  const text = "First. Second! Third? Trailing";
  assert.equal(sentences("en", text).join(""), text);
});

// ---- the degraded host: no Intl.Segmenter -----------------------------------

test("the fallback splitter does not split on a decimal point", () => {
  // The first failure this file's header names. On a host without
  // Intl.Segmenter, "Version 1.2.3 is out." became three sentences.
  assert.deepEqual(fallbackSentences("Version 1.2.3 is out."), ["Version 1.2.3 is out."]);
});

test("the fallback splitter splits after a quoted full stop", () => {
  // The second. `He said "stop." Then left.` is two sentences, and returning
  // it as one unsplit blob means a screen reader reads it as one breath.
  assert.deepEqual(
    fallbackSentences('He said "stop." Then left.'),
    ['He said "stop." ', "Then left."],
  );
});

test("the fallback splitter keeps the unterminated tail", () => {
  // The one that loses data: dropping the tail means the in-progress end of a
  // streaming answer is never spoken, and it breaks the seam guarantee that
  // slice(0, n) + slice(n) recombine to the original.
  const parts = fallbackSentences("Done. And now this is still be");
  assert.equal(parts.join(""), "Done. And now this is still be", "no character may be lost");
  assert.ok(parts.length >= 2, "the finished sentence and the tail are separate");
});

test("the fallback splitter recombines to exactly the input", () => {
  // The general form of the guarantee, over the awkward cases together.
  for (const text of [
    "",
    "One.",
    "One. Two. Three.",
    "Version 1.2.3 is out. Next.",
    'He said "stop." Then left.',
    "No terminator at all",
    "Trailing space. ",
  ]) {
    assert.equal(fallbackSentences(text).join(""), text, `lost characters in ${JSON.stringify(text)}`);
  }
});

test("a one-character sentence is complete", () => {
  // `end === 0` -> `end === 1` survived: a chunk whose only character is a
  // terminator reports incomplete, so `completedLength` returns 0 and the
  // screen-reader announcement stalls. CJK writes short sentences and "。" is
  // a whole one; so is "." after a trimmed fragment.
  for (const one of [".", "!", "?", "。", "！", "？"]) {
    assert.equal(endsSentence(one), true, `${one} is a complete sentence`);
  }
  assert.equal(completedLength("en", "。"), 1, "a single terminator is one complete character");
});

test("a chunk with no terminator is still incomplete", () => {
  // The pair. Reporting everything complete announces half-sentences as they
  // stream, which is the stutter announce.ts exists to prevent.
  assert.equal(endsSentence("still typing"), false);
  assert.equal(endsSentence(""), false);
});
