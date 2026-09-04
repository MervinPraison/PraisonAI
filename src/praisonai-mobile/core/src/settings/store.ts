/**
 * Settings, split across two stores by whether a value is a secret.
 *
 * engine/server.py:653 records the failure this prevents: "One reference app
 * keyrings its API keys and then writes its proxy password to the settings
 * file." Having a SecretsPort is not enough -- something has to guarantee the
 * routing, and store.test.ts asserts the fake StoragePort never saw the value.
 *
 * The UI is handed a facade with `hasSecret` and no getter, so a view cannot
 * accidentally fault a key into the render tree where it can reach a log, a
 * crash report or a screenshot.
 */
import type { SecretRef, SecretsPort } from "../ports/secrets.ts";
import type { StoragePort } from "../ports/storage.ts";

export type SettingValue = string | number | boolean;

/** "This setting only does something while THAT one holds this value." */
export interface SettingDependency {
  readonly key: string;
  readonly equals: SettingValue;
}

export interface SettingDef {
  readonly key: string;
  readonly default: SettingValue;
  /** What the settings screen calls it. Falls back to the key, which is at
   *  least honest -- but a screen showing `maxTokens` to a user is a screen
   *  written by someone who never opened it. */
  readonly label?: string;
  readonly help?: string;
  /** Groups rows under a heading. Ungrouped settings land under "General". */
  readonly section?: string;
  /** A closed set of choices. Renders as a picker rather than a free field,
   *  which is the difference between choosing a model and typing one. */
  readonly choices?: readonly SettingValue[];
  /**
   * A value that would be accepted, spelled out.
   *
   * Shown only when `validate` REFUSES what was typed. The refusal machinery
   * added in #4694 could say which setting was rejected and nothing about what
   * a good value looks like, so "Engine address was not changed" left the user
   * staring at the same field with the same wrong string in it. A def that can
   * refuse should be able to say what it wants instead; a def with no
   * `validate` has nothing to refuse and needs no example.
   */
  readonly example?: string;
  /**
   * The other setting this one depends on, and the value that switches it on.
   *
   * Declared here rather than discovered by the screen, for the same reason
   * `secretRef` is: the registry is the only layer allowed to name a concrete
   * setting, and a view that hard-codes "baseUrl is dead unless engineId is
   * remote-http" is a view that goes stale the day a third engine lands.
   *
   * A setting that does not apply is still SHOWN -- disabled, and saying which
   * switch turns it on. Hiding it loses the value the user typed from the
   * screen (never from the store) and, worse, makes the field unfindable for
   * anyone who is looking for it before they have chosen the engine that uses
   * it.
   */
  readonly appliesWhen?: SettingDependency;
  /** Secret values are routed to SecretsPort and never to StoragePort. */
  readonly secret?: boolean;
  /**
   * WHERE a secret def's value lives in the keychain.
   *
   * Without this a def could say "this is a secret" and not say which slot it
   * maps to, so a settings screen could render presence and still had no
   * sanctioned way to know where `setSecret` should write -- the mapping had
   * to be carried in by whoever built the view, which puts the one identifier
   * that addresses a stored credential outside the registry that declares it.
   *
   * Required in practice for `secret: true`; `secretRefOf` refuses the pair
   * that does not make sense rather than letting it reach a keychain call.
   */
  readonly secretRef?: SecretRef;
  /** Clamp or reject. Returns the value to store, or null to refuse it. */
  readonly validate?: (value: SettingValue) => SettingValue | null;
}

export type SettingsUnsubscribe = () => void;

export interface SettingsStore {
  get(key: string): SettingValue | undefined;
  isSet(key: string): boolean;
  /** The definitions, so a screen renders from data rather than a hard-coded
   *  list that drifts the first time a setting is added. */
  defs(): readonly SettingDef[];
  /** Fires after any accepted write. Without it a screen re-renders blindly
   *  after every `set`, including the ones that were refused. */
  subscribe(cb: () => void): SettingsUnsubscribe;
  set(key: string, value: SettingValue): Promise<boolean>;
  load(): Promise<void>;
  setSecret(ref: SecretRef, value: string): Promise<void>;
  hasSecret(ref: SecretRef): Promise<boolean>;
  clearSecret(ref: SecretRef): Promise<void>;
}

/** What ui/ receives: presence, never the value. */
export interface SettingsFacade {
  get(key: string): SettingValue | undefined;
  /** True only when the value came from storage or an accepted `set` -- never
   *  for a def's default. A caller weighing a setting against its own explicit
   *  argument needs this: `get` returns the default for an untouched key, which
   *  is indistinguishable from a deliberate choice. */
  isSet(key: string): boolean;
  set(key: string, value: SettingValue): Promise<boolean>;
  defs(): readonly SettingDef[];
  subscribe(cb: () => void): SettingsUnsubscribe;
  hasSecret(ref: SecretRef): Promise<boolean>;
  /**
   * Store a secret. WRITE-ONLY by design -- there is deliberately no getter
   * beside it, so a view can configure a key and prove one is present without
   * ever being able to fault the value into a render tree, a log or a
   * screenshot. Without this the keychain port was inert: nothing in the
   * package could write a secret at all.
   */
  setSecret(ref: SecretRef, value: string): Promise<void>;
  clearSecret(ref: SecretRef): Promise<void>;
  /** False on the web adapter. The settings view warns rather than implying a
   *  safety the platform is not providing. */
  readonly secretsAreHardwareBacked: boolean;
}

/**
 * The keychain address for a def, or null when there isn't one.
 *
 * Both mismatches are refused rather than guessed: a secret def with no ref
 * has nowhere to write, and a non-secret def with a ref would route an
 * ordinary setting into the keychain, where nothing would ever read it back.
 */
export function secretRefOf(def: SettingDef): SecretRef | null {
  if (def.secret !== true) return null;
  return def.secretRef ?? null;
}

/**
 * The VALUE of a secret setting, by key. The read-back half.
 *
 * `secretRefOf` says WHERE a secret lives; until this existed nothing said how
 * to get it out again, and `SecretsPort.get` had no caller outside its own
 * conformance suite. A key the user could store and nothing could read is the
 * same bug as no key field at all, one layer further in.
 *
 * It takes the full `SecretsPort` and NOT `SettingsFacade`, which is the whole
 * point: the facade deliberately has no getter (store.ts's header, and rule 2
 * in ports/secrets.ts -- "Only the engine receives the full port; ui/ receives
 * a facade that exposes presence and no getter"). So a view cannot reach this
 * function with what a view is given, and the type system is what says so
 * rather than a comment.
 *
 * An empty stored value comes back as null, not as "". An empty string is what
 * an `Authorization: Bearer ` header is built from before anyone notices, and
 * "absent" is the honest reading of it either way.
 */
export async function readSecretSetting(
  secrets: SecretsPort,
  defs: readonly SettingDef[],
  key: string,
): Promise<string | null> {
  const def = defs.find((d) => d.key === key);
  if (def === undefined) return null;
  // Refuses the same two mismatches `secretRefOf` refuses -- a non-secret def,
  // or a secret one with nowhere to read from -- rather than guessing a slot.
  const ref = secretRefOf(def);
  if (ref === null) return null;
  const value = await secrets.get(ref);
  return value === null || value === "" ? null : value;
}

const STORAGE_KEY = { namespace: "settings" as const, id: "app" };

/**
 * Everything in `values` that is safe to write to StoragePort.
 *
 * Extracted so a test can call it. The guard it contains is defence in depth:
 * `set` refuses a secret-flagged key and `load` drops one, so through the
 * public API nothing can put a secret into the map in the first place. That is
 * exactly why it needs its own test -- an unreachable guard is a guard nobody
 * notices the deletion of, and the day a new write path forgets the rule this
 * line is the only thing between an API key and a plaintext settings file.
 */
export function plainOnly(
  values: ReadonlyMap<string, SettingValue>,
  byKey: ReadonlyMap<string, SettingDef>,
): Record<string, SettingValue> {
  const plain: Record<string, SettingValue> = {};
  for (const [key, value] of values) {
    if (byKey.get(key)?.secret === true) continue;
    plain[key] = value;
  }
  return plain;
}

export function createSettingsStore(
  defs: readonly SettingDef[],
  storage: StoragePort,
  secrets: SecretsPort,
): SettingsStore {
  const byKey = new Map(defs.map((d) => [d.key, d]));
  const values = new Map<string, SettingValue>(defs.map((d) => [d.key, d.default]));
  /** Keys whose value came from storage or from an accepted `set`, as opposed
   *  to the def's default.
   *
   *  `get` cannot express the difference: it returns the default for a key
   *  nobody has ever touched, which reads identically to a deliberate choice.
   *  That matters wherever a caller has its own instruction to weigh -- a
   *  DEFAULT must never outrank an explicit argument, or a setting nobody set
   *  silently overrides the thing that asked. */
  const chosen = new Set<string>();

  const persist = async (): Promise<void> => {
    await storage.write(STORAGE_KEY, JSON.stringify(plainOnly(values, byKey)));
  };

  const subscribers = new Set<() => void>();
  /** Only after an ACCEPTED write. Notifying on a refused one is what makes a
   *  screen redraw a value the user did not manage to change. */
  const notify = () => {
    for (const cb of [...subscribers]) cb();
  };

  return {
    get(key) {
      return values.get(key);
    },

    isSet(key) {
      return chosen.has(key);
    },

    defs: () => defs,

    subscribe(cb) {
      subscribers.add(cb);
      return () => void subscribers.delete(cb);
    },

    async set(key, value) {
      const def = byKey.get(key);
      // An unknown key is refused rather than stored. A typo that silently
      // persists is a setting the user believes they changed.
      if (def === undefined) return false;
      if (def.secret === true) return false; // use setSecret

      const validated = def.validate === undefined ? value : def.validate(value);
      if (validated === null) return false;

      // Persist BEFORE mutating the in-memory map. `persist` reaches
      // StoragePort, which rejects on a real device (SecurityError with site
      // data blocked, QuotaExceededError under storage pressure). Updating
      // `values`/`chosen` first left `get` returning a value the next launch's
      // `load` will never read -- a setting the user believes they changed and
      // did not, and a field that cannot honestly reset to what is stored. The
      // write is committed to memory only once it is durable.
      const previous = values.get(key);
      const wasChosen = chosen.has(key);
      values.set(key, validated);
      chosen.add(key);
      try {
        await persist();
      } catch (error) {
        if (previous === undefined) values.delete(key);
        else values.set(key, previous);
        if (!wasChosen) chosen.delete(key);
        throw error;
      }
      notify();
      return true;
    },

    async load() {
      const raw = await storage.read(STORAGE_KEY);
      if (raw === null) return;
      let parsed: unknown;
      try {
        parsed = JSON.parse(raw);
      } catch {
        // A corrupt settings file falls back to defaults rather than refusing
        // to start. Losing preferences is recoverable; not launching is not.
        return;
      }
      if (parsed === null || typeof parsed !== "object") return;

      for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
        const def = byKey.get(key);
        // Unknown keys are dropped, so a hand-edited file cannot half-configure
        // the app, and a removed setting does not linger forever.
        if (def === undefined || def.secret === true) continue;
        if (typeof value !== "string" && typeof value !== "number" && typeof value !== "boolean") {
          continue;
        }
        const validated = def.validate === undefined ? value : def.validate(value);
        if (validated !== null) {
          values.set(key, validated);
          chosen.add(key);
        }
      }
    },

    async setSecret(ref, value) {
      await secrets.set(ref, value);
      // A screen renders "configured" from hasSecret, so storing a key has to
      // wake it -- otherwise the row still reads "not set" until something
      // else happens to trigger a redraw.
      notify();
    },

    async hasSecret(ref) {
      return secrets.has(ref);
    },

    async clearSecret(ref) {
      await secrets.delete(ref);
      notify();
    },
  };
}

/** Narrow a store to what a view is allowed to touch. */
export function facadeFor(store: SettingsStore, secrets: SecretsPort): SettingsFacade {
  return {
    get: (key) => store.get(key),
    isSet: (key) => store.isSet(key),
    set: (key, value) => store.set(key, value),
    defs: () => store.defs(),
    subscribe: (cb) => store.subscribe(cb),
    setSecret: (ref, value) => store.setSecret(ref, value),
    clearSecret: (ref) => store.clearSecret(ref),
    hasSecret: (ref) => store.hasSecret(ref),
    secretsAreHardwareBacked: secrets.isHardwareBacked,
  };
}

/**
 * Does this setting do anything right now?
 *
 * True for a def with no `appliesWhen`, which is nearly all of them. The
 * dependency is read through `get`, not `isSet`: a def's DEFAULT is a live
 * value -- the engine really is remote-http on the web before anyone touches
 * the picker -- and asking `isSet` would report every dependent setting as
 * inactive until its controller had been changed at least once.
 */
export function appliesTo(
  def: SettingDef,
  read: (key: string) => SettingValue | undefined,
): boolean {
  const dependency = def.appliesWhen;
  if (dependency === undefined) return true;
  return read(dependency.key) === dependency.equals;
}

/**
 * An http(s) address, normalised -- or null.
 *
 * `baseUrl` shipped with no `validate` at all, so `7.0.0.1:8765` was stored,
 * displayed back, and discovered to be wrong only when a turn failed with a
 * transport error naming nothing the user had typed. The refusal machinery to
 * say so already existed (#4694): `validateInput` -> `set` -> a `role="alert"`
 * note beside the field. What was missing was anything that ever refused.
 *
 * Everything `new URL` will not parse is refused, and so is every scheme that
 * is not http or https -- `localhost:8765` PARSES, as a URL whose protocol is
 * `localhost:`, which is exactly the near-miss a user types. A bare host with
 * no scheme cannot parse at all when it starts with a digit and parses as a
 * scheme when it does not, so neither shape is let through.
 *
 * The stored value is the parsed one, not the typed one: a trailing slash, a
 * trailing space and an uppercase host all mean the same engine, and storing
 * them apart is three settings that look different and behave identically.
 * Trailing slashes go here rather than at the two call sites that were each
 * doing `.replace(/\/+$/, "")` on their own.
 *
 * A query string or fragment is refused, not carried through. The engine
 * builds `${base}/chat`, `${base}/health`, `${base}/approve/{id}` by plain
 * concatenation (engines/src/remote-http/engine.ts), so a stored
 * "http://host:8765/?token=abc" becomes "http://host:8765/?token=abc/chat" --
 * a request for "/" with a mangled query, not "/chat". The address the user is
 * told was saved reaches none of the endpoints a turn needs. `?` and `#` have
 * no place in an engine base, so they are refused at the point the value is
 * accepted rather than silently kept and mis-joined later.
 */
export function httpUrl(): (value: SettingValue) => SettingValue | null {
  return (value) => {
    if (typeof value !== "string") return null;
    const text = value.trim();
    if (text === "") return null;
    let url: URL;
    try {
      url = new URL(text);
    } catch {
      return null;
    }
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    if (url.hostname === "") return null;
    // A base the endpoints append to cannot carry a query or fragment: `?x` and
    // `#y` would land BEFORE the `/chat` the engine concatenates, addressing "/"
    // with a broken query instead of the endpoint. Refuse rather than keep-and-
    // mis-join.
    if (url.search !== "" || url.hash !== "") return null;
    const normalised = `${url.origin}${url.pathname}`.replace(/\/+$/, "");
    // `origin` alone for a bare "http://host/", which strips to "http://host".
    return normalised === "" ? url.origin : normalised;
  };
}

/** Clamp a number into range. Lifted from the desktop settings registry, where
 *  it is a named function precisely so a test can call it. */
export function clampNum(min: number, max: number): (value: SettingValue) => SettingValue | null {
  return (value) => {
    if (typeof value !== "number" || !Number.isFinite(value)) return null;
    return Math.min(max, Math.max(min, value));
  };
}
