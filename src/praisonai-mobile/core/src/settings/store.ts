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

      values.set(key, validated);
      chosen.add(key);
      await persist();
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

/** Clamp a number into range. Lifted from the desktop settings registry, where
 *  it is a named function precisely so a test can call it. */
export function clampNum(min: number, max: number): (value: SettingValue) => SettingValue | null {
  return (value) => {
    if (typeof value !== "number" || !Number.isFinite(value)) return null;
    return Math.min(max, Math.max(min, value));
  };
}
