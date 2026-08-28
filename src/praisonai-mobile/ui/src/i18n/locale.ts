/**
 * Which locale we are in, and which way the text runs.
 *
 * Nothing in this package had a locale at all before this file: every label was
 * an English literal at its render site, so "translate the app" meant "find and
 * edit two hundred call sites", and "does this work in Arabic" had no answer
 * because there was nothing to ask the question of.
 *
 * Three concrete failures this prevents.
 *
 *  1. A TAG IS NOT A LANGUAGE. `navigator.language` returns "en-GB", "pt-BR",
 *     "zh-Hant-TW". Code that does `tables[tag]` finds nothing for "en-GB" and
 *     renders a blank screen for a British user who has a perfectly good
 *     English table sitting next to it. `resolveLocale` does the lookup match
 *     -- exact tag, then progressively shorter prefixes -- so "en-GB" lands on
 *     "en" and "zh-Hant-TW" lands on "zh-Hant" before "zh".
 *
 *  2. DIRECTION IS NOT A LANGUAGE LIST EITHER. "az-Arab" is Azerbaijani written
 *     in the Arabic script and is right-to-left; "az" is Latin and is not. A
 *     hand-written set of RTL language codes gets that wrong, and gets Kurdish
 *     ("ckb" vs "ku") wrong, and gets every future addition wrong. The script
 *     is what decides, so ICU is asked first and the table is only the fallback
 *     for a host with no locale data.
 *
 *  3. A MALFORMED TAG MUST NOT THROW. `new Intl.Locale("en_US")` -- underscore,
 *     which is what a stored preference from a Java or POSIX-shaped source
 *     looks like -- raises RangeError. Thrown out of a render path that is
 *     deciding which way to lay out the screen, that is a white screen. Every
 *     entry point here is total: it returns a direction for any string at all.
 *
 * RTL and `ui/src/layout/insets.ts`: `Geometry` exposes `composerLeftPx` and
 * `composerRightPx`, which are PHYSICAL edges. Safe-area insets from the OS are
 * physical too, so those two fields are correct as measurements -- the bug is
 * only at the point a renderer maps them onto padding. In Arabic the composer's
 * leading edge is the right one, and a renderer that writes `padding-left:
 * composerLeftPx` puts the send button's clearance on the wrong side of the
 * screen. `logicalInsets` below is the mapping, added ALONGSIDE insets.ts
 * rather than inside it: insets.ts is deliberately about arithmetic that cannot
 * produce NaN, and it has no business knowing what language the user reads.
 */

/** Which way a line of text runs. Not a boolean: "is RTL" reads wrong at half
 *  the call sites, and a boolean has no third state to grow into. */
export type Direction = "ltr" | "rtl";

/**
 * Scripts written right to left, keyed by the ISO 15924 subtag.
 *
 * Only consulted when ICU has no data for the tag. Deliberately by SCRIPT and
 * not by language: see failure 2 in the header.
 */
const RTL_SCRIPTS: ReadonlySet<string> = new Set([
  "Adlm", "Arab", "Aran", "Armi", "Avst", "Cprt", "Egyp", "Hatr", "Hebr",
  "Hung", "Khar", "Lydi", "Mand", "Mani", "Mend", "Merc", "Mero", "Narb",
  "Nbat", "Nkoo", "Orkh", "Palm", "Phli", "Phlp", "Phnx", "Prti", "Rohg",
  "Samr", "Sarb", "Sogd", "Sogo", "Syrc", "Thaa", "Yezi",
]);

/**
 * Languages whose default script is right to left.
 *
 * The last resort, for a host with no ICU data AND a tag carrying no explicit
 * script subtag. Short on purpose: it is a floor, not a source of truth.
 */
const RTL_LANGUAGES: ReadonlySet<string> = new Set([
  "ar", "arc", "az-arab", "ckb", "dv", "fa", "he", "ks", "ku-arab", "nqo",
  "pnb", "ps", "sd", "syr", "ug", "ur", "yi",
  // Added after comparing this table against `Intl.Locale.textInfo` across a
  // corpus: thirteen languages disagreed, all of them RTL by Intl and LTR
  // here. Because this table is only consulted when `textInfo` is ABSENT, the
  // gap was invisible on every host that could have revealed it, and rendered
  // the whole UI the wrong way round on the older WebViews that reach it.
  //
  // Five spoken Arabic varieties, which are what a phone's locale actually
  // reports in those regions rather than plain "ar":
  "aeb", "acm", "ajp", "apc", "ary", "arz",
  // Persian-script and Perso-Arabic languages:
  "bal", "glk", "haz", "lrc", "mzn", "skr",
  // Rohingya, whose Hanifi script is RTL:
  "rhg",
]);

/** Split a tag on either separator. A stored preference reaches us as "en_US"
 *  as often as "en-US", and only one of those is a BCP 47 tag. */
function subtags(tag: string): readonly string[] {
  return tag.split(/[-_]/).filter((part) => part !== "");
}

/**
 * A tag in the shape the Intl constructors accept, or null if it is hopeless.
 *
 * Returning null rather than throwing is the point: every caller here has a
 * sensible answer for "we could not parse that", and none of them has a
 * sensible answer for an exception.
 */
export function canonicalise(tag: string): string | null {
  const parts = subtags(tag);
  if (parts.length === 0) return null;
  const joined = parts.join("-");
  try {
    const [first] = Intl.getCanonicalLocales(joined);
    return first ?? null;
  } catch {
    return null;
  }
}

/** ICU's own answer, or null when it has no opinion or the tag will not parse. */
function directionFromIntl(tag: string): Direction | null {
  const canonical = canonicalise(tag);
  if (canonical === null) return null;
  try {
    // `textInfo` is a getter on Intl.Locale that older TypeScript lib files do
    // not declare, hence the structural probe rather than a property access.
    const locale = new Intl.Locale(canonical) as unknown as { readonly textInfo?: unknown };
    const info = locale.textInfo;
    if (typeof info !== "object" || info === null) return null;
    const direction = (info as { readonly direction?: unknown }).direction;
    return direction === "rtl" || direction === "ltr" ? direction : null;
  } catch {
    return null;
  }
}

/** The fallback: an explicit script subtag if there is one, else the language. */
/**
 * The table lookup, exported so a test can call it.
 *
 * `direction()` is `directionFromIntl(tag) ?? directionFromTables(tag)`, and
 * the test host is a Node with full ICU where the first half always answers --
 * so this half never ran under test. A mutation sweep found FIVE
 * indistinguishable mutations in it: Arabic, Hebrew, Farsi and Urdu rendering
 * LTR; `az-Arab` and `ku-Arab` rendering LTR; `ar-Latn` and `ks-Deva`
 * rendering RTL.
 *
 * This is the branch that runs on an older Android WebView without
 * `Intl.Locale.textInfo` -- exactly the devices most likely to be affected --
 * and the failure is the whole UI mirrored the wrong way, or not at all.
 */
export function directionFromTables(tag: string): Direction {
  const parts = subtags(tag).map((part) => part.toLowerCase());
  const language = parts[0] ?? "";

  // A script subtag is four letters. Checked before the language table because
  // "az-Arab" must beat "az".
  for (const part of parts.slice(1)) {
    if (part.length !== 4) continue;
    const script = part.charAt(0).toUpperCase() + part.slice(1);
    if (RTL_SCRIPTS.has(script)) return "rtl";
    return "ltr";
  }

  if (RTL_LANGUAGES.has(language)) return "rtl";
  const withScript = parts.length > 1 ? `${language}-${parts[1] ?? ""}` : language;
  return RTL_LANGUAGES.has(withScript) ? "rtl" : "ltr";
}

/**
 * Which way this locale's text runs. Total: never throws, always answers.
 *
 * "ltr" is the default for anything unrecognised, because laying an Arabic UI
 * out left to right is ugly and laying an English one out right to left is
 * unusable -- the asymmetry decides the default.
 */
export function direction(tag: string): Direction {
  return directionFromIntl(tag) ?? directionFromTables(tag);
}

export function isRtl(tag: string): boolean {
  return direction(tag) === "rtl";
}

/**
 * Physical edges mapped onto logical ones.
 *
 * `Geometry` in ui/src/layout/insets.ts hands a renderer `composerLeftPx` and
 * `composerRightPx`, which are physical and correct as measurements. This is
 * the mapping a renderer needs before it writes them into `padding-inline-
 * start` / `padding-inline-end`, or into a React Native `start`/`end`.
 *
 * Kept here, not in insets.ts: that file's contract is "no NaN, no negatives,
 * commutative under measurement order", and threading a locale through it would
 * make a layout function depend on the user's language for no arithmetic
 * reason. This is a pure adapter over its output.
 */
export interface LogicalInsets {
  /** The leading edge -- left in English, right in Arabic. */
  readonly startPx: number;
  readonly endPx: number;
}

export function logicalInsets(dir: Direction, leftPx: number, rightPx: number): LogicalInsets {
  return dir === "rtl" ? { startPx: rightPx, endPx: leftPx } : { startPx: leftPx, endPx: rightPx };
}

/**
 * Pick the best supported locale for what the user asked for.
 *
 * BCP 47 lookup, in the order the user ranked them: for each requested tag, try
 * the whole tag and then each shorter prefix. "en-GB" therefore matches a
 * supported "en", which is the case a naive `supported.includes(tag)` gets
 * wrong for most of the planet.
 *
 * `fallback` is returned when nothing matches, so the result is always a tag
 * that actually has a table behind it -- never the user's unsupported request,
 * which is how a UI ends up rendering keys instead of words.
 */
export function resolveLocale(
  requested: readonly string[],
  supported: readonly string[],
  fallback: string,
): string {
  const available = new Map<string, string>();
  for (const tag of supported) {
    const canonical = canonicalise(tag);
    if (canonical !== null) available.set(canonical.toLowerCase(), canonical);
  }

  for (const want of requested) {
    const canonical = canonicalise(want);
    if (canonical === null) continue;
    const parts = canonical.split("-");
    for (let length = parts.length; length > 0; length -= 1) {
      const candidate = parts.slice(0, length).join("-").toLowerCase();
      const hit = available.get(candidate);
      if (hit !== undefined) return hit;
    }
  }

  return fallback;
}
