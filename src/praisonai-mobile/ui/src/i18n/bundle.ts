/**
 * Assembling a locale's table, and being LOUD about what it is missing.
 *
 * A translation is never finished. A key gets added in English on Tuesday and
 * the twelve other tables get it in three weeks, if at all. What every i18n
 * library gets wrong is what happens in between, and there are exactly two
 * wrong answers, both of which ship:
 *
 *  - RETURN THE KEY. The user sees `transcript.tool.unresolved` where a word
 *    should be. It is at least visible, but it is visible to the USER and not
 *    to the developer, and it is unreadable to both.
 *
 *  - RETURN EMPTY STRING. This is the one that actually causes damage. A
 *    missing key becomes a button with no label, a row with no text, a screen
 *    that looks like a rendering bug. Nothing throws, nothing logs, and the
 *    only symptom is a blank rectangle in a language nobody on the team reads.
 *    A screen reader announces it as "button", full stop.
 *
 * So this file does neither. A key the translation does not supply falls back
 * to the ENGLISH text -- never blank, never a key path, always something a user
 * can act on -- and then makes the fall-through visible three ways at once:
 *
 *   1. `missing` and `mismatched` are returned as data, so a test can assert a
 *      table is complete and CI can fail on an incomplete one. This is the one
 *      that catches it before a user does.
 *   2. In `mark` mode the fallback text is bracketed -- ⟦Stopped⟧ -- so a
 *      developer or a translator running the app sees it immediately without
 *      reading a log. Chosen brackets that no locale uses in ordinary prose.
 *   3. In `throw` mode construction fails outright, for a release build that
 *      would rather not start than ship half a language.
 *
 * `silent` exists and is deliberately NOT the default: it is for a production
 * build that has already been gated on `missing.length === 0` by CI, and
 * choosing it is a decision someone has to type.
 *
 * The other job here is shape checking. A translation is data -- it may have
 * been round-tripped through JSON, or hand-edited -- so a key that should be a
 * function and arrived as a string is a real possibility, and calling it would
 * throw "x is not a function" from inside a render. That is checked, reported
 * separately from a plain omission, and falls back the same way.
 */
import { direction, type Direction } from "./locale.ts";
import { en, type StringKey, type Strings } from "./strings.ts";

/** What happens when a key falls through to English. */
export type MissingKeyMode =
  /** Bracket the fallback so it is visible on screen. The default. */
  | "mark"
  /** Refuse to build the bundle at all. For a release gate. */
  | "throw"
  /** Use the fallback verbatim. Only for a build CI has already verified. */
  | "silent";

export const MISSING_OPEN = "⟦";
export const MISSING_CLOSE = "⟧";

/** Bracket a fallback. Exported so a test asserts the same marker the runtime
 *  produces rather than a copy of it that can drift. */
export function markMissing(text: string): string {
  return `${MISSING_OPEN}${text}${MISSING_CLOSE}`;
}

export function isMarked(text: string): boolean {
  return text.startsWith(MISSING_OPEN) && text.endsWith(MISSING_CLOSE);
}

export interface Bundle {
  /** The tag this table is FOR, which may differ from the tag requested --
   *  resolveLocale() does the matching. */
  readonly locale: string;
  readonly direction: Direction;
  readonly strings: Strings;
  /** Keys the translation did not supply at all. */
  readonly missing: readonly StringKey[];
  /** Keys supplied with the wrong shape -- a string where a function belongs,
   *  which would have thrown at the call site instead of here. */
  readonly mismatched: readonly StringKey[];
}

/** True when this table can be shipped as a complete translation. */
export function isComplete(bundle: Bundle): boolean {
  return bundle.missing.length === 0 && bundle.mismatched.length === 0;
}

/** A one-line report for a log or a CI failure message. */
export function describeBundle(bundle: Bundle): string {
  if (isComplete(bundle)) return `i18n: ${bundle.locale} complete`;
  const parts: string[] = [];
  if (bundle.missing.length > 0) parts.push(`missing ${bundle.missing.join(", ")}`);
  if (bundle.mismatched.length > 0) parts.push(`wrong shape ${bundle.mismatched.join(", ")}`);
  return `i18n: ${bundle.locale} incomplete -- ${parts.join("; ")}`;
}

/** Wrap a fallback function so its RESULT carries the marker. Marking the
 *  function itself would be invisible; the string it returns is what a user
 *  reads. */
function markFunction(fn: (...args: never[]) => string): (...args: never[]) => string {
  return (...args: never[]) => markMissing(fn(...args));
}

/**
 * Build a table for `locale` from a partial translation.
 *
 * Total: it always returns a usable `Strings` (or throws in `throw` mode,
 * which is the point of that mode). It never returns a table with a blank or a
 * key path in it.
 */
export function createBundle(
  locale: string,
  translation: Partial<Strings> = {},
  mode: MissingKeyMode = "mark",
): Bundle {
  const reference = en as unknown as Readonly<Record<string, unknown>>;
  const supplied = translation as unknown as Readonly<Record<string, unknown>>;
  const out: Record<string, unknown> = {};
  const missing: StringKey[] = [];
  const mismatched: StringKey[] = [];

  // Driven by the keys of `en`, never by the keys of the translation. A
  // translation carrying an extra key from a version that has since been
  // deleted must not put it into the table, and -- much more importantly -- a
  // translation MISSING a key must still produce that key.
  for (const key of Object.keys(reference)) {
    const base = reference[key];
    const given = supplied[key];
    const wantsFunction = typeof base === "function";

    if (given === undefined || given === null) {
      missing.push(key as StringKey);
    } else if (wantsFunction ? typeof given === "function" : typeof given === "string") {
      out[key] = given;
      continue;
    } else {
      mismatched.push(key as StringKey);
    }

    if (mode === "silent") {
      out[key] = base;
    } else if (wantsFunction) {
      out[key] = markFunction(base as (...args: never[]) => string);
    } else {
      out[key] = markMissing(base as string);
    }
  }

  const bundle: Bundle = {
    locale,
    direction: direction(locale),
    strings: out as unknown as Strings,
    missing,
    mismatched,
  };

  if (mode === "throw" && !isComplete(bundle)) {
    throw new Error(describeBundle(bundle));
  }
  return bundle;
}

/**
 * The English bundle.
 *
 * Built through the same path as every other locale rather than being handed
 * `en` directly, so the assembly code is exercised by the default of the app
 * and cannot rot into something only the tests run.
 */
export const enBundle: Bundle = createBundle("en", en, "silent");
