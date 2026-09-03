/**
 * SecretsPort over the platform keychain in `src-tauri/plugins/secrets`.
 *
 * WHY THIS EXISTS. `app/src/platform.ts` branched `storage` per platform and
 * handed `createWebSecrets()` -- a module-scoped `Map` -- to BOTH. So on a
 * phone the API key worked for exactly as long as the process lived, and the
 * user re-entered it on every single launch. `core/src/ports/secrets.ts` opens
 * by saying the port IS "the keychain (iOS) and keystore (Android)"; this is
 * the adapter that makes the sentence true on a device.
 *
 * `isHardwareBacked` IS TRUE HERE, and that is a claim, not an assumption.
 * `detectPlatform` is synchronous -- `ShellPort.insets` has to be readable
 * during the first paint -- so this file cannot ask the host "are you iOS?"
 * before answering. The invariant is kept one layer down instead: the Rust
 * plugin refuses every call on a platform with no hardware store rather than
 * falling back to a file, so a secret that was stored AT ALL through this
 * adapter is in the Keychain or the Keystore. The alternative -- a flag that
 * starts false and flips when a probe lands -- would show the "not protected"
 * warning on a keychain-backed phone for the first frames of the settings
 * screen, which is a warning that means nothing the moment it is wrong once.
 *
 * `invokeStrict`, not `invoke`. The forgiving `invoke` resolves to `null` on
 * failure, and `null` is `get`'s word for "no such secret" -- so on the
 * forgiving one a failing keychain would present as a user who never
 * configured a key, and the app would ask for it again instead of saying it
 * could not be read.
 */
import type { SecretRef, SecretsPort } from "../../../core/src/ports/secrets.ts";
import type { StrictInvoke } from "./storage.ts";

/**
 * The seam with `src-tauri/src/secrets.rs`, which declares the same four
 * strings as `pub const`s. `tools/secrets-seam.test.mjs` reads both files and
 * compares them: a rename on one side alone is silent, and silent here means
 * the settings screen says "Not set" forever while the key sits in the
 * keychain -- and every attempt to fix it by re-typing the key also fails.
 */
export const SECRET_COMMANDS = {
  read: "secret_read",
  write: "secret_write",
  remove: "secret_remove",
  has: "secret_has",
} as const;

export interface TauriSecretsDeps {
  readonly invoke: StrictInvoke;
}

/**
 * A reply that is not the shape the command promises is an I/O FAILURE, not an
 * absence -- the same distinction `createTauriStorage` draws, for the same
 * reason. A native `undefined` read as `null` would report a broken keychain
 * as "no key configured", and the user would paste a working key into a store
 * that cannot keep it.
 */
function asStringOrNull(command: string, value: unknown): string | null {
  // `undefined` as well as `null`, unlike `createTauriStorage`. A Rust
  // `Ok(None)` reaches the webview as JSON `null`; `undefined` is accepted
  // alongside it because the two are the same absence to every caller of this
  // port, and because nothing here depends on telling them apart -- an I/O
  // failure REJECTS rather than returning either, which is the distinction
  // that actually matters and the reason `invokeStrict` is used. Exercised on
  // a device: a fresh install with no key stored reports the SDK's "the
  // OPENAI_API_KEY environment variable is missing", not a shape error.
  if (value === null || value === undefined) return null;
  if (typeof value === "string") return value;
  throw new Error(`${command} returned ${typeof value}, not a string or null`);
}

function asBoolean(command: string, value: unknown): boolean {
  if (typeof value !== "boolean") {
    throw new Error(`${command} returned ${typeof value}, not a boolean`);
  }
  return value;
}

export function createTauriSecrets(deps: TauriSecretsDeps): SecretsPort {
  // The argument names are the Rust parameter names. Tauri maps a JS key onto
  // a `snake_case` Rust parameter; both of these are a single lowercase word
  // precisely so there is no case convention to get wrong -- a mismatch is a
  // deserialisation error on EVERY call, reported to the webview as "could not
  // save" with nothing pointing at the cause.
  const of = (ref: SecretRef): Record<string, unknown> => ({
    slot: ref.slot,
    account: ref.account,
  });

  return {
    // See the header. Guaranteed by the plugin refusing rather than degrading.
    isHardwareBacked: true,

    /**
     * Presence, through its OWN command.
     *
     * Rule 2 of the port: `has()` "exists so the UI can render 'configured'
     * without reading the value" and "must not fault the value into memory".
     * `get(ref) !== null` would satisfy every behavioural test in the contract
     * and copy the user's API key out of the keychain into the webview's heap
     * on every repaint of the settings screen -- where a content-script bug, a
     * crash dump or a devtools attach can reach it. So the check goes to Rust
     * as a presence query and comes back as a boolean.
     */
    async has(ref) {
      const present = await deps.invoke(SECRET_COMMANDS.has, of(ref));
      return asBoolean(SECRET_COMMANDS.has, present);
    },

    async get(ref) {
      const value = await deps.invoke(SECRET_COMMANDS.read, of(ref));
      return asStringOrNull(SECRET_COMMANDS.read, value);
    },

    async set(ref, value) {
      await deps.invoke(SECRET_COMMANDS.write, { ...of(ref), value });
    },

    async delete(ref) {
      await deps.invoke(SECRET_COMMANDS.remove, of(ref));
    },
  };
}
