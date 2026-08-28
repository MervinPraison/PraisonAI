/**
 * Where one sentence ends and the next begins, per locale.
 *
 * This exists for the screen-reader announcement policy in ui/src/a11y, which
 * has to answer "how much of a half-written answer is safe to speak yet". The
 * obvious implementation -- split on ". " -- fails in three ways that are all
 * silent:
 *
 *  - "Run npm i. Then..." is fine, but "Installed version 1.2.3 successfully"
 *    is cut into three pieces, and a screen reader reads three fragments with
 *    three falling intonations. `Intl.Segmenter` knows a decimal point is not a
 *    sentence end; a split on ". " cannot.
 *
 *  - Japanese has no spaces and terminates with U+3002 IDEOGRAPHIC FULL STOP.
 *    Splitting on ". " finds nothing, so a Japanese answer is announced as one
 *    unbroken wall at the end of the turn or not at all.
 *
 *  - Arabic terminates with U+061F and U+06D4. Same outcome.
 *
 * The other half of the job is the STREAMING half, and it is the reason this
 * is not just `sentences()`. Mid-stream, the last segment is almost always a
 * half-typed sentence. Announcing it means the screen reader says "The file
 * cont" and then, a moment later, says the whole sentence again from the top.
 * `completedLength` returns only the prefix that is finished, so the caller can
 * hold the tail back until it is.
 *
 * ONE LIMITATION, STATED RATHER THAN HIDDEN. `Intl.Segmenter` does not expose
 * ICU's abbreviation suppression lists, so "Ask Dr. Smith" is segmented after
 * "Dr.". The consequence is bounded and cosmetic -- a screen reader announces
 * two words a beat early -- and it is not worth a hand-written abbreviation
 * list, which would be English-only and would therefore reintroduce exactly the
 * class of bug this file exists to remove.
 */

/** Sentence terminators across scripts, plus the ellipsis a model actually
 *  emits. ASCII-only detection is what makes CJK and Arabic silent. */
const TERMINATORS = new Set([
  ".", "!", "?", "…", // . ! ? …
  "。", "！", "？", // 。！？ CJK fullwidth
  "؟", "۔", // ؟ ۔ Arabic question mark, Urdu full stop
  "।", "॥", // । ॥ Devanagari danda
  "՜", "՞", // ՜ ՞ Armenian
  "።", // ። Ethiopic
]);

/** Closers that may legitimately follow a terminator: `He said "stop."` ends a
 *  sentence even though its last character is a quote mark. */
const CLOSERS = new Set([
  '"', "'", ")", "]", "}", "»", "”", "’", "」", "』", "）",
]);

const segmenters = new Map<string, Intl.Segmenter | null>();

function sentenceSegmenter(locale: string): Intl.Segmenter | null {
  const cached = segmenters.get(locale);
  if (cached !== undefined) return cached;
  let made: Intl.Segmenter | null;
  try {
    // `granularity: "sentence"` is the whole reason to reach for Segmenter;
    // format.ts uses the same API at "grapheme" for the same class of reason.
    made = new Intl.Segmenter(locale, { granularity: "sentence" });
  } catch {
    made = null;
  }
  segmenters.set(locale, made);
  return made;
}

/** The sentences of `text`, each including its own trailing whitespace. */
export function sentences(locale: string, text: string): readonly string[] {
  if (text === "") return [];
  const segmenter = sentenceSegmenter(locale);
  if (segmenter === null) return fallbackSentences(text);
  return Array.from(segmenter.segment(text), (part) => part.segment);
}

/**
 * Does this chunk look finished?
 *
 * Trailing whitespace and trailing closers are stripped first, so `stop.")\n`
 * is finished and `stop and` is not.
 */
export function endsSentence(chunk: string): boolean {
  let end = chunk.length;
  while (end > 0) {
    const ch = chunk.charAt(end - 1);
    if (ch.trim() === "" || CLOSERS.has(ch)) {
      end -= 1;
      continue;
    }
    break;
  }
  if (end === 0) return false;
  return TERMINATORS.has(chunk.charAt(end - 1));
}

/**
 * How many code units from the start of `text` form COMPLETE sentences.
 *
 * 0 means "nothing is safe to announce yet". The returned length includes the
 * whitespace after the last terminator, so `text.slice(0, n)` and
 * `text.slice(n)` recombine exactly -- a caller keeping a cursor into the
 * stream must not lose or duplicate a character at the seam.
 */
export function completedLength(locale: string, text: string): number {
  if (text === "") return 0;
  let complete = 0;
  let cursor = 0;
  for (const sentence of sentences(locale, text)) {
    cursor += sentence.length;
    if (endsSentence(sentence)) complete = cursor;
  }
  return complete;
}

/**
 * No-ICU fallback: split after a terminator followed by whitespace or end.
 *
 * Worse than Segmenter at every one of the cases in the header, and used only
 * when the platform has no segmentation data at all. It never SPLITS wrongly in
 * a way that loses text -- the pieces still concatenate back to the input --
 * so the seam guarantee above holds either way.
 */
/**
 * The no-Segmenter splitter, exported so a test can call it.
 *
 * `sentences()` uses `Intl.Segmenter` whenever it exists, and it always does
 * on the test host -- so this path never ran. Three mutations survived in it,
 * one per failure this file's own header names: splitting on a decimal point,
 * splitting mid-CJK, and failing to split after a quoted full stop. A fourth
 * dropped the unterminated tail entirely, which on a host without Segmenter
 * means a blind user never hears the in-progress end of an answer, and breaks
 * the documented seam guarantee that slice(0,n) + slice(n) recombine.
 */
export function fallbackSentences(text: string): readonly string[] {
  const out: string[] = [];
  let start = 0;
  for (let i = 0; i < text.length; i += 1) {
    if (!TERMINATORS.has(text.charAt(i))) continue;
    let end = i + 1;
    while (end < text.length && CLOSERS.has(text.charAt(end))) end += 1;
    // A terminator glued to the next word is a decimal point or an
    // abbreviation, not a sentence end -- the one case the fallback can catch.
    if (end < text.length && text.charAt(end).trim() !== "") continue;
    while (end < text.length && text.charAt(end).trim() === "") end += 1;
    out.push(text.slice(start, end));
    start = end;
    i = end - 1;
  }
  if (start < text.length) out.push(text.slice(start));
  return out;
}
