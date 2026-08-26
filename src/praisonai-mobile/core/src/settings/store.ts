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
  /** Secret values are routed to SecretsPort and never to StoragePort. */
  readonly secret?: boolean;
  /** Clamp or reject. Returns the value to store, or null to refuse it. */
  readonly validate?: (value: SettingValue) => SettingValue | null;
}

export interface SettingsStore {
  get(key: string): SettingValue | undefined;
  set(key: string, value: SettingValue): Promise<boolean>;
  load(): Promise<void>;
  setSecret(ref: SecretRef, value: string): Promise<void>;
  hasSecret(ref: SecretRef): Promise<boolean>;
  clearSecret(ref: SecretRef): Promise<void>;
}

/** What ui/ receives: presence, never the value. */
export interface SettingsFacade {
  get(key: string): SettingValue | undefined;
  set(key: string, value: SettingValue): Promise<boolean>;
  hasSecret(ref: SecretRef): Promise<boolean>;
  /** False on the web adapter. The settings view warns rather than implying a
   *  safety the platform is not providing. */
  readonly secretsAreHardwareBacked: boolean;
}

const STORAGE_KEY = { namespace: "settings" as const, id: "app" };

export function createSettingsStore(
  defs: readonly SettingDef[],
  storage: StoragePort,
  secrets: SecretsPort,
): SettingsStore {
  const byKey = new Map(defs.map((d) => [d.key, d]));
  const values = new Map<string, SettingValue>(defs.map((d) => [d.key, d.default]));

  const persist = async (): Promise<void> => {
    const plain: Record<string, SettingValue> = {};
    for (const [key, value] of values) {
      const def = byKey.get(key);
      // The guarantee. A secret-flagged setting never reaches StoragePort,
      // even if something upstream put one in the map.
      if (def?.secret === true) continue;
      plain[key] = value;
    }
    await storage.write(STORAGE_KEY, JSON.stringify(plain));
  };

  return {
    get(key) {
      return values.get(key);
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
      await persist();
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
        if (validated !== null) values.set(key, validated);
      }
    },

    async setSecret(ref, value) {
      await secrets.set(ref, value);
    },

    async hasSecret(ref) {
      return secrets.has(ref);
    },

    async clearSecret(ref) {
      await secrets.delete(ref);
    },
  };
}

/** Narrow a store to what a view is allowed to touch. */
export function facadeFor(store: SettingsStore, secrets: SecretsPort): SettingsFacade {
  return {
    get: (key) => store.get(key),
    set: (key, value) => store.set(key, value),
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
