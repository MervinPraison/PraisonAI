/**
 * The settings registry -> grouped rows to render.
 *
 * A settings SCREEN was impossible before this file. core/src/settings/store.ts
 * gained `defs()` and `subscribe()` precisely so a screen could render from data
 * instead of a hard-coded list that drifts the first time a setting is added --
 * a drifted list is a setting that exists, is honoured by the engine, and can
 * never be reached by the person it was added for.
 *
 * Four rules are load-bearing, and each of them has a broken version that looks
 * completely normal on screen:
 *
 *  1. A SECRET ROW HAS NO VALUE FIELD. Not "a value that is left unset" -- no
 *     field at all, and `value?: never` so writing one is a type error rather
 *     than a code review. The facade deliberately offers `hasSecret` and no
 *     getter (store.ts: so a view cannot "fault a key into the render tree
 *     where it can reach a log, a crash report or a screenshot"), and a view
 *     model with an optional `value` on the secret row is an open invitation to
 *     fill it in later.
 *
 *  2. PRESENCE HAS THREE STATES, NOT TWO. "Configured", "Not set", and NOT YET
 *     CHECKED -- because `hasSecret` is async and `buildSettings` is not.
 *     Rendering an unresolved check as "Not set" tells someone their API key is
 *     missing when it is sitting in the keychain, and the natural response is
 *     to paste it again. Same discipline as format.ts: unknown is not zero.
 *
 *  3. THE WARNING ABOUT SOFTWARE-ONLY SECRETS IS ALWAYS SURFACED WHEN IT IS
 *     TRUE. ports/secrets.ts states the whole point of the flag: "The settings
 *     view shows an explicit warning when this is false rather than implying a
 *     safety the platform is not providing." Nothing else in the package can
 *     keep that promise -- only this file renders it.
 *
 *  4. THE CONTROL KIND COMES FROM THE DEF, NEVER FROM THE CURRENT VALUE. A
 *     value read back from a hand-edited settings file is arbitrary; deriving
 *     the control from it means one bad write turns a toggle into a text box
 *     and the setting can no longer be changed back.
 *
 * Row ids are derived from the setting key, never from array position, so a
 * keyed renderer (render/reconcile.ts) cannot paint one row's contents into
 * another row's node when a section gains an entry.
 */
import type { SecretRef } from "../../../core/src/ports/secrets.ts";
import type { SettingDef, SettingValue, SettingsFacade } from "../../../core/src/settings/store.ts";
import { UNKNOWN } from "../format.ts";

/** Where a def with no `section` lands. Named so a test and a renderer agree. */
export const GENERAL_SECTION = "General";

export const CONFIGURED = "Configured";
export const NOT_SET = "Not set";

/** What a control has to be for this def to be editable at all. */
export type ControlKind = "toggle" | "choice" | "number" | "text";

/**
 * Presence of a secret, including the state the other two hide.
 *
 * `unknown` is what a row looks like before the async `hasSecret` has landed.
 * See rule 2 in the header: it is not "not set".
 */
export type PresenceState = "configured" | "not-set" | "unknown";

/** The answer to one `facade.hasSecret(ref)`, carried back with the ref that
 *  produced it -- the screen needs that same ref to call `setSecret`. */
export interface SecretStatus {
  readonly ref: SecretRef;
  readonly configured: boolean;
}

/** Resolved presence, keyed by `SettingDef.key`. A key that is absent is a
 *  check that has not come back yet, which is why this is a lookup rather than
 *  a pair of booleans. */
export type SecretPresence = ReadonlyMap<string, SecretStatus>;

export interface ValueRow {
  readonly kind: "value";
  readonly id: string;
  readonly key: string;
  /** `def.label`, falling back to the key. A screen showing `maxTokens` is at
   *  least honest; a screen showing nothing is a mystery row. */
  readonly label: string;
  readonly help: string | null;
  readonly control: ControlKind;
  readonly value: SettingValue;
  /** The closed set for a `choice` control, null for every other kind. */
  readonly choices: readonly SettingValue[] | null;
}

/**
 * A secret, rendered as presence and nothing else.
 *
 * There is no `value` field, and `value?: never` makes adding one at a call
 * site a compile error instead of a leak. See rule 1 in the header.
 */
export interface SecretRow {
  readonly kind: "secret";
  readonly id: string;
  readonly key: string;
  readonly label: string;
  readonly help: string | null;
  readonly state: PresenceState;
  /** "Configured", "Not set", or UNKNOWN for a check still in flight. */
  readonly presence: string;
  /** Where to write it. Null when nothing has told this view which slot the
   *  def belongs to -- see the note on `secretPresence`. */
  readonly ref: SecretRef | null;
  /** Structurally unfillable. Do not remove. */
  readonly value?: never;
}

/**
 * "These secrets are not protected by hardware."
 *
 * A row rather than a boolean buried in the view, so it is rendered by the same
 * loop as everything else and cannot be forgotten by a renderer that only walks
 * rows.
 */
export interface WarningRow {
  readonly kind: "warning";
  readonly id: string;
  readonly text: string;
}

export type SettingsRow = ValueRow | SecretRow;

export interface SettingsSection {
  readonly title: string;
  readonly rows: readonly SettingsRow[];
}

export interface SettingsView {
  /** Grouped, in registry order. */
  readonly sections: readonly SettingsSection[];
  /** Rendered above the sections. Empty on a platform with a real keychain. */
  readonly warnings: readonly WarningRow[];
  /** Copied through so a caller can style the whole screen, without having to
   *  re-reach for the facade it already handed us. */
  readonly secretsAreHardwareBacked: boolean;
}

/**
 * What the user is told when there is no keychain under their credentials.
 *
 * REWRITTEN, not deleted, when the Tauri build got a real keychain. The old
 * sentence -- "Secrets are stored in app memory on this platform, not in a
 * hardware-backed keychain" -- was shown on a phone AND in a browser, because
 * `platform.ts` handed `createWebSecrets()` to both. Now that a device gets
 * `src-tauri/plugins/secrets`, "this platform" is only ever the browser, and a
 * message that still said "this platform" would be technically true and
 * useless: it would name the one thing the reader already knows and omit the
 * two things they need to act on -- that the key goes no further than this tab,
 * and that it will be gone when the tab does.
 *
 * Deleting it instead was the other option and it is worse. The web build is
 * still real, its "keychain" is still a `Map`, and a settings screen that says
 * nothing reads as a settings screen with nothing to say. A message that lies
 * about where a user's API key lives is worse than no message; a message that
 * is silent about it is not much better.
 *
 * It stays keyed off `secretsAreHardwareBacked` rather than off a platform
 * name, so it is the ADAPTER that decides -- which means a future adapter that
 * cannot reach a keychain gets the warning without anyone remembering to add
 * it.
 */
export const SOFTWARE_SECRETS_WARNING =
  "This browser has no keychain, so a key you enter is kept in this tab's memory only. " +
  "It is not saved anywhere, and you will have to enter it again next time.";

/**
 * The control a def needs.
 *
 * Precedence is deliberate. A boolean is a toggle even if someone listed
 * `choices: [true, false]`, because a two-item picker of raw values is a worse
 * toggle. An EMPTY `choices` array is not a picker: a picker with nothing in it
 * is a control that cannot be operated, so the underlying type still wins.
 */
export function controlFor(def: SettingDef): ControlKind {
  if (typeof def.default === "boolean") return "toggle";
  if (def.choices !== undefined && def.choices.length > 0) return "choice";
  if (typeof def.default === "number") return "number";
  return "text";
}

/** `def.label` or the key. Exported so a screen's other affordances (a search
 *  field, a deep link) label a setting the same way its row does. */
export function labelOf(def: SettingDef): string {
  const label = def.label?.trim() ?? "";
  return label === "" ? def.key : label;
}

/** The words for a presence state. Exported so the renderer that REFRESHES a
 *  row after an async `hasSecret` lands says the same thing the first paint
 *  said -- two spellings of "Configured" is two rows that look like different
 *  states. */
export function presenceLabel(state: PresenceState): string {
  switch (state) {
    case "configured":
      return CONFIGURED;
    case "not-set":
      return NOT_SET;
    case "unknown":
      // Not "Not set". Telling someone their key is missing while the keychain
      // lookup is still in flight is how a working key gets pasted twice.
      return UNKNOWN;
  }
}

function secretRow(def: SettingDef, presence: SecretPresence): SecretRow {
  const status = presence.get(def.key);
  const state: PresenceState =
    status === undefined ? "unknown" : status.configured ? "configured" : "not-set";
  return {
    kind: "secret",
    id: `secret:${def.key}`,
    key: def.key,
    label: labelOf(def),
    help: def.help ?? null,
    state,
    presence: presenceLabel(state),
    ref: status?.ref ?? null,
  };
}

function valueRow(def: SettingDef, facade: SettingsFacade): ValueRow {
  const stored = facade.get(def.key);
  const control = controlFor(def);
  return {
    kind: "value",
    id: `setting:${def.key}`,
    key: def.key,
    label: labelOf(def),
    help: def.help ?? null,
    control,
    // `??`, never `||`: a stored `false`, `0` or "" is a deliberate choice, and
    // `||` would quietly redraw the default over the top of it -- a toggle the
    // user switched off that switches itself back on when the screen reopens.
    value: stored ?? def.default,
    choices: control === "choice" ? (def.choices ?? null) : null,
  };
}

/**
 * Build the whole screen.
 *
 * `secretPresence` defaults to empty, which renders every secret as UNKNOWN
 * rather than as "Not set" -- the honest state for a screen whose async checks
 * have not resolved on first paint.
 */
export function buildSettings(
  facade: SettingsFacade,
  secretPresence: SecretPresence = new Map(),
): SettingsView {
  // Insertion-ordered by construction, so section order is REGISTRY order: the
  // order the author of the registry chose. Alphabetical would silently
  // reshuffle the screen the day a section is renamed.
  const sections = new Map<string, SettingsRow[]>();
  const seen = new Set<string>();

  for (const def of facade.defs()) {
    // Defensive: two defs sharing a key would produce two rows with the same
    // id, which is exactly how a keyed renderer paints one row into another
    // row's node. First one wins, like the store's own map.
    if (seen.has(def.key)) continue;
    seen.add(def.key);

    const title = def.section?.trim() === "" ? GENERAL_SECTION : (def.section ?? GENERAL_SECTION);
    const rows = sections.get(title) ?? [];
    rows.push(def.secret === true ? secretRow(def, secretPresence) : valueRow(def, facade));
    sections.set(title, rows);
  }

  const warnings: WarningRow[] = facade.secretsAreHardwareBacked
    ? []
    : [{ kind: "warning", id: "warning:software-secrets", text: SOFTWARE_SECRETS_WARNING }];

  return {
    sections: [...sections].map(([title, rows]) => ({ title, rows })),
    warnings,
    secretsAreHardwareBacked: facade.secretsAreHardwareBacked,
  };
}

/** Every row, flattened, for a caller that does not group -- and for asserting
 *  that ids are unique across the whole screen and not merely within a group. */
export function rowsOf(view: SettingsView): readonly SettingsRow[] {
  return view.sections.flatMap((section) => section.rows);
}

/** Narrow to the secret rows, for a caller wiring the "replace key" flow. */
export function secretRowsOf(view: SettingsView): readonly SecretRow[] {
  return rowsOf(view).filter((row): row is SecretRow => row.kind === "secret");
}

const TRUE_WORDS = new Set(["true", "1", "on", "yes"]);
const FALSE_WORDS = new Set(["false", "0", "off", "no"]);

function parseFor(def: SettingDef, raw: string): SettingValue | null {
  switch (controlFor(def)) {
    case "toggle": {
      const word = raw.trim().toLowerCase();
      if (TRUE_WORDS.has(word)) return true;
      if (FALSE_WORDS.has(word)) return false;
      return null;
    }
    case "choice": {
      const wanted = raw.trim();
      // The CHOICE is returned, not the parsed text, so the stored value's type
      // comes from the closed set rather than from what a field happened to
      // contain. A picker that can smuggle a value outside its own list is a
      // picker in name only.
      const match = def.choices?.find((choice) => String(choice) === wanted);
      return match ?? null;
    }
    case "number": {
      const text = raw.trim();
      // Number("") is 0, not NaN. Without this line an emptied field reads as
      // a deliberate zero -- a max-tokens of 0 that the user never typed.
      if (text === "") return null;
      const value = Number(text);
      return Number.isFinite(value) ? value : null;
    }
    case "text":
      // Returned exactly as typed. Trimming here would silently rewrite what
      // someone entered; a def that wants it trimmed says so in `validate`.
      return raw;
  }
}

/**
 * A string from a text field -> a value that is safe to `set`, or null.
 *
 * Pure, so a screen can disable its Save button on the same answer it would get
 * from writing -- and so an unparseable value never reaches `facade.set`, where
 * the refusal would come back as a silent `false` long after the field lost
 * focus.
 *
 * The def's own `validate` runs last: parsing says "this is a number", the def
 * says "and it is in range". Skipping it here would let a screen offer a value
 * the store then refuses, which reads to the user as a setting that will not
 * stick.
 */
export function validateInput(def: SettingDef, raw: string): SettingValue | null {
  // A secret has no text-field path into the plain store. It goes to
  // `setSecret`, and returning a SettingValue here is the first step of the
  // journey that ends with an API key in the settings file.
  if (def.secret === true) return null;

  const parsed = parseFor(def, raw);
  if (parsed === null) return null;
  return def.validate === undefined ? parsed : def.validate(parsed);
}
