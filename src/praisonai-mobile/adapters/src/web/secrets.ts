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
    // Never true for this adapter, and the reason is above: a module-scoped
    // Map is not a keychain.
    //
    // This comment used to claim "the composition root refuses to hand a
    // hardware-backed secret to an engine when the transport is not native,
    // and this flag is half of that check". There is no such check. The flag
    // is read in exactly one place -- the settings view's warning row
    // (ui/src/settings/view-model.ts) -- and app/src/boot.ts has never
    // consulted it. Describing a guard that does not exist is worse than
    // having no guard, because it stops the next reader looking for one.
    //
    // Nor is the guard needed yet: no secret reaches an engine at all.
    // `createRemoteHttpEngine` accepts a `token`, and registry.ts does not
    // pass one, so the stored API key is currently read by nothing. When that
    // is wired, THIS is the flag the refusal should consult -- and it should
    // arrive with a test, not with a comment.
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
