/**
 * Plurals via CLDR categories, because `n === 1 ? "" : "s"` is an English rule.
 *
 * The concrete bug: app/src/dom.ts writes
 *
 *     `${row.count} event${row.count === 1 ? "" : "s"} could not be read`
 *
 * which is correct English and wrong almost everywhere else. Polish has three
 * forms and picks a different one for 2, 5 and 22. Russian picks by the last
 * two digits. Welsh has six. Arabic has six and one of them is for zero.
 * Japanese has one, so the "s" is simply noise. None of that is expressible as
 * a ternary on `=== 1`, and the failure is invisible to an English reviewer:
 * the string renders, it is just wrong, and the only person who can see it is
 * the user who cannot report it in your language.
 *
 * `Intl.PluralRules` is the CLDR data the platform already ships. This file is
 * the thin, total wrapper around it:
 *
 *  - A LOCALE WITH NO DATA MUST NOT THROW. `new Intl.PluralRules("en_US")`
 *    raises RangeError on the underscore. A throw here happens inside a render,
 *    and a blank screen is a much worse outcome than a slightly wrong plural.
 *
 *  - `other` IS MANDATORY, THE REST ARE NOT. Every locale has `other`; only
 *    some have `zero`, `two`, `few`, `many`. Making `other` a required field
 *    of `PluralForms` turns "I forgot the fallback" into a compile error rather
 *    than an `undefined` painted into a sentence.
 *
 *  - THE SELECTED CATEGORY MAY NOT EXIST IN THE FORMS. A translator supplying
 *    only `one` and `other` for Polish is normal and incomplete. Selection
 *    walks a documented chain down to `other` rather than rendering blank.
 */

/** The CLDR cardinal categories. Not an enum: tsconfig sets
 *  `erasableSyntaxOnly`, and an enum emits JavaScript that type-stripping
 *  cannot produce. */
export type PluralCategory = "zero" | "one" | "two" | "few" | "many" | "other";

/**
 * One string per category the locale actually uses.
 *
 * `other` is required. See the header: it is the only category guaranteed to
 * exist, so it is the only one that may be relied on to be there.
 */
export interface PluralForms {
  readonly zero?: string;
  readonly one?: string;
  readonly two?: string;
  readonly few?: string;
  readonly many?: string;
  readonly other: string;
}

/**
 * Constructing an Intl.PluralRules is not free and a streaming transcript calls
 * this on every publish, so they are memoised per locale. Keyed by the raw tag
 * including the ones that failed, so a bad tag costs one failed construction
 * for the life of the process rather than one per frame.
 */
const rulesByLocale = new Map<string, Intl.PluralRules | null>();

function rulesFor(locale: string): Intl.PluralRules | null {
  const cached = rulesByLocale.get(locale);
  if (cached !== undefined) return cached;
  let rules: Intl.PluralRules | null;
  try {
    rules = new Intl.PluralRules(locale);
  } catch {
    rules = null;
  }
  rulesByLocale.set(locale, rules);
  return rules;
}

/**
 * The CLDR category for `count` in `locale`.
 *
 * Falls back to the English rule when the platform has no data at all, which is
 * both the honest answer for a host with no ICU and a visible one: an English
 * plural in a Polish UI is wrong in a way a Polish speaker can report.
 * A non-finite count is `other`, never a crash -- `usage.chars` arrives from
 * the wire and NaN has reached a formatter in this package before.
 */
export function pluralCategory(locale: string, count: number): PluralCategory {
  if (!Number.isFinite(count)) return "other";
  const rules = rulesFor(locale);
  if (rules === null) return count === 1 ? "one" : "other";
  const selected = rules.select(count);
  switch (selected) {
    case "zero":
    case "one":
    case "two":
    case "few":
    case "many":
    case "other":
      return selected;
    default:
      return "other";
  }
}

/**
 * The fallback chain when the selected category has no string supplied.
 *
 * Not just "straight to other": `many` standing in for `few` in Polish is a
 * better wrong answer than `other`, and `two` standing in for `one` is better
 * than a plural. Every chain terminates at `other`, which is always present.
 */
const FALLBACKS: Readonly<Record<PluralCategory, readonly PluralCategory[]>> = {
  zero: ["zero", "other"],
  one: ["one", "other"],
  two: ["two", "few", "many", "other"],
  few: ["few", "many", "other"],
  many: ["many", "few", "other"],
  other: ["other"],
};

/** Pick the form for `count`, never returning undefined. */
export function selectPlural(locale: string, count: number, forms: PluralForms): string {
  const category = pluralCategory(locale, count);
  for (const candidate of FALLBACKS[category]) {
    const form = forms[candidate];
    if (form !== undefined) return form;
  }
  return forms.other;
}

/**
 * The common case: a count and a noun, with the number already formatted.
 *
 * `formatted` is passed in rather than being derived from `count` because the
 * numeral itself is locale-dependent too -- Arabic-Indic digits, a comma
 * decimal separator -- and that decision belongs to format-intl.ts, not here.
 * The two arguments can legitimately disagree (2.0 formatted as "2" still
 * selects Polish `few`, not `many`), which is exactly why the CATEGORY comes
 * from the number and the TEXT comes from the string.
 */
export function countedPhrase(
  locale: string,
  count: number,
  formatted: string,
  forms: PluralForms,
): string {
  return selectPlural(locale, count, forms).replace("{n}", formatted);
}
