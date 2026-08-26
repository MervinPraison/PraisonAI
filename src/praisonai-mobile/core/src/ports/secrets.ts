/**
 * The keychain (iOS) and keystore (Android).
 *
 * Two rules the desktop already learned the hard way, plus one that is new on
 * mobile. engine/server.py:653 records the first: "One reference app keyrings
 * its API keys and then writes its proxy password to the settings file."
 *
 *  1. A secret never passes through StoragePort. core/src/settings/store.ts
 *     routes any registry entry flagged `secret` here instead, and its test
 *     asserts the fake StoragePort never saw the value.
 *  2. `has()` exists so the UI can render "configured" without reading the
 *     value. Only the engine receives the full port; ui/ receives a facade
 *     that exposes presence and no getter.
 *  3. The slot is a closed union. A free-form name lets a bug write an
 *     attacker-influenced string into the keychain service namespace.
 */

export type SecretSlot = "openai" | "anthropic" | "google" | "openrouter" | "custom";

export interface SecretRef {
  readonly slot: SecretSlot;
  /** Which account within the slot. "default" for the single-key case. */
  readonly account: string;
}

export interface SecretsPort {
  /** Presence only. Must not fault the value into memory. */
  has(ref: SecretRef): Promise<boolean>;

  get(ref: SecretRef): Promise<string | null>;

  set(ref: SecretRef, value: string): Promise<void>;

  delete(ref: SecretRef): Promise<void>;

  /**
   * False on the web adapter, where "secrets" are process memory.
   *
   * The settings view shows an explicit warning when this is false rather than
   * implying a safety the platform is not providing. A silent downgrade is how
   * a user comes to believe a key is protected when it is not.
   */
  readonly isHardwareBacked: boolean;
}
