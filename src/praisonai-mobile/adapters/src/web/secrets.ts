/**
 * SecretsPort in process memory.
 *
 * `isHardwareBacked` is false and must stay false. There is no keychain in a
 * browser, and the settings view is expected to warn on it. An adapter that
 * claimed hardware backing here would let a user believe a key is protected
 * when it is one devtools panel away.
 *
 * Values live in a module-scoped Map rather than localStorage on purpose: a
 * secret in localStorage survives the tab, is readable by any script on the
 * origin, and ends up in a browser profile backup.
 */
import type { SecretRef, SecretsPort } from "../../../core/src/ports/secrets.ts";

const compose = (ref: SecretRef): string => `${ref.slot}:${ref.account}`;

export function createWebSecrets(): SecretsPort {
  const store = new Map<string, string>();

  return {
    // Never true for this adapter. The composition root refuses to hand a
    // hardware-backed secret to an engine when the transport is not native,
    // and this flag is half of that check.
    isHardwareBacked: false,

    async has(ref) {
      return store.has(compose(ref));
    },
    async get(ref) {
      return store.get(compose(ref)) ?? null;
    },
    async set(ref, value) {
      store.set(compose(ref), value);
    },
    async delete(ref) {
      store.delete(compose(ref));
    },
  };
}
