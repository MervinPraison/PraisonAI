/**
 * The locale-aware half of formatting. The deterministic half stays in
 * ui/src/format.ts, and BOTH have to exist. This is the file that explains why.
 *
 * format.ts says so itself, about the date it falls back to for an old chat:
 *
 *     "The date is ISO rather than locale-formatted so the output is the same
 *      on every device and can be asserted; the view layer may localise it
 *      later."
 *
 * That is not laziness, it is the only way its tests mean anything.
 * `formatRelative` is asserted against literal strings. The moment it calls
 * `Intl.DateTimeFormat` with no locale and no time zone, those assertions start
 * depending on the machine running them: an ICU upgrade changes "Jan 1, 1970"
 * to "Jan 1, 1970" with a different space, a CI box in UTC and a laptop in
 * Auckland disagree about which DAY a timestamp falls on, and a test that was
 * pinning a real rule ("a future timestamp never renders as negative time")
 * starts failing for a reason that has nothing to do with the rule. A flaky
 * test gets deleted, and the rule goes with it.
 *
 * So format.ts keeps emitting ISO and ASCII, deterministically, and is what the
 * package's own tests assert against. This file is the path a RENDERER uses,
 * and it is additive: nothing in format.ts changes, no existing test moves.
 *
 * Two rules follow from that split and are enforced here rather than trusted:
 *
 *  - TIME ZONE IS A REQUIRED ARGUMENT, not a default. `Intl.DateTimeFormat`
 *    with no `timeZone` silently uses the host's, which is the single most
 *    common way a date test passes in London and fails in Auckland -- and, in
 *    production, the way a chat saved at 23:40 shows tomorrow's date. Passing
 *    null is allowed and means "the host zone", but it has to be TYPED.
 *
 *  - EVERY ENTRY POINT IS TOTAL. `new Intl.NumberFormat("en_US")` throws on the
 *    underscore. A throw inside a transcript row's formatter blanks the whole
 *    list. Every constructor here is memoised behind a try/catch and every
 *    function has a non-throwing answer.
 *
 * The numbers matter as much as the dates. `formatCount` in format.ts produces
 * "1.5M", which is English: German is "1,5 Mio.", Japanese is "150万" (a
 * DIFFERENT scale -- ten-thousands, not thousands), and Arabic may render the
 * digits as Arabic-Indic. `Intl.NumberFormat` with compact notation knows all
 * of that; a UNITS array of ["", "k", "M", "B", "T"] cannot.
 */
import { UNKNOWN } from "../format.ts";
import type { Strings } from "./strings.ts";

/** Constructors are expensive and a streaming transcript re-formats on every
 *  publish, so each configuration is built once per locale. Failures are cached
 *  too: a bad tag costs one throw for the process, not one per frame. */
const numberFormats = new Map<string, Intl.NumberFormat | null>();
const compactFormats = new Map<string, Intl.NumberFormat | null>();
const paddedFormats = new Map<string, Intl.NumberFormat | null>();
const decimalFormats = new Map<string, Intl.NumberFormat | null>();
const integerFormats = new Map<string, Intl.NumberFormat | null>();
const dateFormats = new Map<string, Intl.DateTimeFormat | null>();
const relativeFormats = new Map<string, Intl.RelativeTimeFormat | null>();

function memo<T>(cache: Map<string, T | null>, key: string, make: () => T): T | null {
  const cached = cache.get(key);
  if (cached !== undefined) return cached;
  let made: T | null;
  try {
    made = make();
  } catch {
    made = null;
  }
  cache.set(key, made);
  return made;
}

/** A plain integer or decimal in the locale's numbering system. */
export function formatNumber(locale: string, value: number): string {
  if (!Number.isFinite(value)) return UNKNOWN;
  const fmt = memo(numberFormats, locale, () => new Intl.NumberFormat(locale));
  return fmt === null ? String(value) : fmt.format(value);
}

/**
 * A count, abbreviated the way this locale abbreviates.
 *
 * The locale-aware counterpart of `formatCount`. Japanese groups by 万 and
 * German writes "Mio.": neither is reachable from a hard-coded suffix table.
 */
export function formatCountLocalised(locale: string, value: number): string {
  if (!Number.isFinite(value) || value < 0) return UNKNOWN;
  const whole = Math.floor(value);
  const fmt = memo(compactFormats, locale, () =>
    new Intl.NumberFormat(locale, { notation: "compact", maximumFractionDigits: 1 }));
  return fmt === null ? String(whole) : fmt.format(whole);
}

/**
 * A two-digit integer, padded by ICU rather than by `padStart`.
 *
 * `String(9).padStart(2, "0")` produces "09" with an ASCII zero, which is wrong
 * in a locale rendering Arabic-Indic or Devanagari digits -- the padding digit
 * would be from a different script than the number it pads.
 */
function formatPadded(locale: string, value: number): string {
  const fmt = memo(paddedFormats, locale, () =>
    new Intl.NumberFormat(locale, { minimumIntegerDigits: 2, useGrouping: false }));
  return fmt === null ? String(value).padStart(2, "0") : fmt.format(value);
}

function formatOneDecimal(locale: string, value: number): string {
  const fmt = memo(decimalFormats, locale, () =>
    new Intl.NumberFormat(locale, {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
      useGrouping: false,
    }));
  return fmt === null ? value.toFixed(1) : fmt.format(value);
}

function formatInteger(locale: string, value: number): string {
  const fmt = memo(integerFormats, locale, () =>
    new Intl.NumberFormat(locale, { maximumFractionDigits: 0, useGrouping: false }));
  return fmt === null ? String(value) : fmt.format(value);
}

/**
 * A calendar date.
 *
 * `timeZone` is required and may be null for "the host's". See the header: a
 * defaulted zone is how a timestamp renders as the wrong day.
 */
export function formatDate(locale: string, atMs: number, timeZone: string | null): string {
  if (!Number.isFinite(atMs)) return UNKNOWN;
  const key = `${locale}|${timeZone ?? ""}`;
  const fmt = memo(dateFormats, key, () =>
    new Intl.DateTimeFormat(locale, timeZone === null
      ? { dateStyle: "medium" }
      : { dateStyle: "medium", timeZone }));
  // The ISO fallback is deliberate: it is what format.ts already emits, so a
  // host with no date data degrades to the behaviour the package had before.
  return fmt === null ? new Date(atMs).toISOString().slice(0, 10) : fmt.format(new Date(atMs));
}

/**
 * How long ago, as a decision -- no strings.
 *
 * Split out from the rendering so the THRESHOLDS live in one place and can be
 * asserted without an ICU dependency. They match `formatRelative` in format.ts
 * exactly, including the clamp: a phone whose clock is behind the timestamp it
 * wrote must not say "in -3 minutes", in any language.
 */
export type RelativeParts =
  | { readonly kind: "unknown" }
  | { readonly kind: "just-now" }
  | { readonly kind: "elapsed"; readonly unit: "minute" | "hour" | "day"; readonly value: number }
  | { readonly kind: "date" };

export function relativeParts(atMs: number, nowMs: number): RelativeParts {
  if (!Number.isFinite(atMs) || !Number.isFinite(nowMs)) return { kind: "unknown" };
  const seconds = Math.max(0, nowMs - atMs) / 1000;
  if (seconds < 45) return { kind: "just-now" };
  if (seconds < 3600) return { kind: "elapsed", unit: "minute", value: Math.max(1, Math.round(seconds / 60)) };
  if (seconds < 86_400) return { kind: "elapsed", unit: "hour", value: Math.round(seconds / 3600) };
  if (seconds < 604_800) return { kind: "elapsed", unit: "day", value: Math.round(seconds / 86_400) };
  return { kind: "date" };
}

/**
 * Render the parts from the string table.
 *
 * The fallback path, for a host with no `Intl.RelativeTimeFormat`. It is a real
 * path and not dead code -- it is what makes `minutesAgo` / `hoursAgo` /
 * `daysAgo` in `Strings` worth translating -- and it is exported so it can be
 * tested directly rather than by deleting a global.
 */
export function formatRelativeFromStrings(
  locale: string,
  strings: Strings,
  parts: RelativeParts,
  atMs: number,
  timeZone: string | null,
): string {
  switch (parts.kind) {
    case "unknown":
      return strings.unknownValue;
    case "just-now":
      return strings.justNow;
    case "date":
      return formatDate(locale, atMs, timeZone);
    case "elapsed": {
      const formatted = formatInteger(locale, parts.value);
      if (parts.unit === "minute") return strings.minutesAgo(parts.value, formatted);
      if (parts.unit === "hour") return strings.hoursAgo(parts.value, formatted);
      return strings.daysAgo(parts.value, formatted);
    }
  }
}

/**
 * "2 hours ago" / "vor 2 Stunden" / "قبل ساعتين".
 *
 * Prefers `Intl.RelativeTimeFormat`, which carries CLDR's own phrasing --
 * including the ones a string table gets wrong, like Arabic's dual form for
 * exactly two. Falls back to the table when the platform has no data.
 */
export function formatRelativeLocalised(
  locale: string,
  strings: Strings,
  atMs: number,
  nowMs: number,
  timeZone: string | null,
): string {
  const parts = relativeParts(atMs, nowMs);
  if (parts.kind !== "elapsed") return formatRelativeFromStrings(locale, strings, parts, atMs, timeZone);
  const fmt = memo(relativeFormats, locale, () =>
    new Intl.RelativeTimeFormat(locale, { numeric: "auto" }));
  if (fmt === null) return formatRelativeFromStrings(locale, strings, parts, atMs, timeZone);
  return fmt.format(-parts.value, parts.unit);
}

/**
 * A duration, localised.
 *
 * The thresholds are format.ts's, unchanged: sub-10s keeps a decimal because
 * that is the range a tool call lives in, and `seconds: null` is UNKNOWN rather
 * than zero -- the engine not observing a call begin is not the same as the
 * call returning instantly.
 */
export function formatElapsedLocalised(
  locale: string,
  strings: Strings,
  seconds: number | null,
): string {
  if (seconds === null || !Number.isFinite(seconds) || seconds < 0) return strings.unknownValue;
  if (seconds < 10) return strings.durationSeconds(formatOneDecimal(locale, seconds));

  const total = Math.round(seconds);
  if (total < 60) return strings.durationSeconds(formatInteger(locale, total));

  const minutes = Math.floor(total / 60);
  if (minutes < 60) {
    return strings.durationMinutesSeconds(formatInteger(locale, minutes), formatPadded(locale, total % 60));
  }
  return strings.durationHoursMinutes(
    formatInteger(locale, Math.floor(minutes / 60)),
    formatPadded(locale, minutes % 60),
  );
}
