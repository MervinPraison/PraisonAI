/**
 * The small formatters, as pure functions with no DOM anywhere near them.
 *
 * They live in one file for one reason: every one of them has a wrong answer
 * that looks plausible, and a wrong answer inlined at a call site is a wrong
 * answer nothing can test.
 *
 *  - TRUNCATION. `text.slice(0, n)` cuts by UTF-16 code unit, so it splits a
 *    surrogate pair and the phone renders U+FFFD. Every emoji, every Indic
 *    conjunct and every flag is at risk, and the desktop never noticed because
 *    it truncated nothing. Cutting is done on grapheme clusters here.
 *
 *  - UNKNOWN vs ZERO. `tool_result.seconds` is null when the engine did not
 *    observe the call begin. Rendering that as "0.0s" states a measurement that
 *    was never taken -- and "the tool returned instantly" is exactly the wrong
 *    conclusion for a call whose start was lost. Null gets its own glyph.
 *
 *  - CLOCK SKEW. A phone's wall clock can be behind the timestamp it wrote, so
 *    `now - updated` goes negative. "in -3 minutes" is the visible symptom of
 *    a bug the user cannot act on; it is clamped instead.
 */

/** What a value that was never measured renders as. Deliberately not "0". */
export const UNKNOWN = "—";

const ELLIPSIS = "…";

/**
 * Grapheme clusters, not code points and certainly not code units.
 *
 * Intl.Segmenter keeps a ZWJ sequence such as a family emoji whole; the
 * Array.from fallback at least never splits a surrogate pair, which is the
 * defect that produces a replacement character on screen.
 */
const segmenter =
  typeof Intl.Segmenter === "function"
    ? new Intl.Segmenter(undefined, { granularity: "grapheme" })
    : null;

export function graphemes(text: string): readonly string[] {
  if (segmenter === null) return Array.from(text);
  return Array.from(segmenter.segment(text), (part) => part.segment);
}

/**
 * The first `limit` grapheme clusters, and whether the text had more.
 *
 * `Segments` is lazily iterable; `Array.from` is what forces the whole string.
 * Taking only what is needed turns "segment 40,000 clusters to keep 119" into
 * "segment 120", which is the difference between 10ms and 0.05ms per call --
 * and `buildTranscript` re-derives every tool preview on EVERY publish, so
 * this is paid on each frame of a streaming answer.
 */
export function graphemePrefix(
  text: string,
  limit: number,
): { readonly parts: readonly string[]; readonly hasMore: boolean } {
  if (segmenter === null) {
    const all = Array.from(text);
    return { parts: all.slice(0, limit), hasMore: all.length > limit };
  }
  const parts: string[] = [];
  for (const part of segmenter.segment(text)) {
    if (parts.length === limit) return { parts, hasMore: true };
    parts.push(part.segment);
  }
  return { parts, hasMore: false };
}

/**
 * At most `max` grapheme clusters, with the ellipsis counted as one of them.
 *
 * Returning the input unchanged when it already fits matters: a caller uses
 * identity to decide whether it needs a title attribute at all.
 */
export function truncate(text: string, max: number): string {
  if (!Number.isFinite(max) || max <= 0) return "";

  // A code-unit length is an upper bound on the grapheme count: no cluster is
  // ever fewer than one unit. So if the string already fits by units, it fits
  // by graphemes, and there is nothing to segment.
  //
  // This check used to come AFTER `graphemes(text)`. Segmenting is O(n) and
  // allocates one string per cluster, so a 40kB tool result cost 11ms and
  // 40,000 allocations to discover it needed no truncation at all -- and
  // `buildTranscript` re-derives every tool preview on EVERY publish, so that
  // was paid again on each frame of a streaming answer. Measured at 8 tools
  // with 40kB outputs: 44ms per publish and ~361MB of garbage across one turn,
  // to regenerate previews that had not changed since the tool returned.
  if (text.length <= max) return text;

  // Only `max + 1` clusters are ever needed: `max` to keep, and one more to
  // learn whether anything was cut. Materialising the rest was pure waste --
  // and unbounded, so a single tool returning 40kB of one-line JSON cost ~10ms
  // on EVERY publish, roughly thirty times a second, with no memoisation.
  // The earlier length check only saves the case that already fits; a long
  // output always overflows and always paid the full segmentation.
  const { parts, hasMore } = graphemePrefix(text, max + 1);
  if (!hasMore && parts.length <= max) return text;
  if (max === 1) return ELLIPSIS;
  return parts.slice(0, max - 1).join("") + ELLIPSIS;
}

/** The first line, for a one-line preview of a multi-line tool output. */
export function firstLine(text: string): string {
  const at = text.indexOf("\n");
  return at === -1 ? text : text.slice(0, at);
}

/**
 * A duration in seconds, or UNKNOWN for null.
 *
 * Sub-10s keeps a decimal because that is the range a tool call actually lives
 * in and "3s" hides the difference between 2.5 and 3.4.
 */
export function formatElapsed(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds) || seconds < 0) return UNKNOWN;
  if (seconds < 10) return `${seconds.toFixed(1)}s`;

  const total = Math.round(seconds);
  if (total < 60) return `${total}s`;

  const minutes = Math.floor(total / 60);
  if (minutes < 60) return `${minutes}m ${String(total % 60).padStart(2, "0")}s`;

  return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, "0")}m`;
}

const UNITS = ["", "k", "M", "B", "T"] as const;

/** A token or character count. Never negative, never NaN, never "1000.0k". */
export function formatCount(value: number): string {
  if (!Number.isFinite(value) || value < 0) return UNKNOWN;

  const whole = Math.floor(value);
  if (whole < 1000) return String(whole);

  let scaled = whole;
  let unit = 0;
  while (scaled >= 1000 && unit < UNITS.length - 1) {
    scaled /= 1000;
    unit += 1;
  }

  let text = scaled.toFixed(1);
  // 999_999 scales to 999.999k, which rounds to "1000.0k". Promote the unit
  // rather than print a number that is wider than the one it replaced.
  if (Number(text) >= 1000 && unit < UNITS.length - 1) {
    scaled /= 1000;
    unit += 1;
    text = scaled.toFixed(1);
  }
  return `${text}${UNITS[unit] ?? ""}`;
}

/**
 * "2h ago" for a chat list entry, falling back to a date once relative time
 * stops being useful.
 *
 * The date is ISO rather than locale-formatted so the output is the same on
 * every device and can be asserted; the view layer may localise it later.
 */
export function formatRelative(atMs: number, nowMs: number): string {
  if (!Number.isFinite(atMs) || !Number.isFinite(nowMs)) return UNKNOWN;

  // Clamped, not signed: a phone whose clock is behind the timestamp it wrote
  // must not render "in -3 minutes" at a user who can do nothing about it.
  const elapsed = Math.max(0, nowMs - atMs);
  const seconds = elapsed / 1000;

  if (seconds < 45) return "just now";
  if (seconds < 3600) return `${Math.max(1, Math.round(seconds / 60))}m ago`;
  if (seconds < 86_400) return `${Math.round(seconds / 3600)}h ago`;
  if (seconds < 604_800) return `${Math.round(seconds / 86_400)}d ago`;

  return new Date(atMs).toISOString().slice(0, 10);
}
