/**
 * An in-memory SecretsPort.
 *
 * `isHardwareBacked` is false and stays false. The web adapter reports the same
 * thing, and the settings view is expected to warn on it -- a fake that claimed
 * hardware backing would let a test pass that should have caught the missing
 * warning.
 */
import type { SecretRef, SecretsPort } from "../../core/src/ports/secrets.ts";

export interface FakeSecrets extends SecretsPort {
  /** Number of times a value was actually read out, so a test can assert the
   *  UI checked presence rather than faulting the secret into memory. */
  readonly reads: number;
}

const compose = (ref: SecretRef): string => `${ref.slot}:${ref.account}`;

export function createFakeSecrets(): FakeSecrets {
  const store = new Map<string, string>();
  let reads = 0;

  return {
    isHardwareBacked: false,
    get reads() {
      return reads;
    },
    async has(ref) {
      return store.has(compose(ref));
    },
    async get(ref) {
      reads += 1;
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
