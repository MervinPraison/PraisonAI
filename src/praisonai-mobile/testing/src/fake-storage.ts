/**
 * An in-memory StoragePort.
 *
 * Its own tests assert the same contract the real adapters must satisfy, for a
 * reason worth stating: a fake with a bug makes every test that uses it pass
 * for the wrong reason. If this returned `undefined` for a missing key while
 * the Tauri adapter returns `null`, every repository test would be green and
 * the app would still break on a device.
 */
import type { Namespace, StorageKey, StoragePort } from "../../core/src/ports/storage.ts";

export interface FakeStorage extends StoragePort {
  /** Every key ever written. */
  readonly writes: readonly StorageKey[];
  /**
   * Every VALUE ever written, so a test can assert a secret never landed here
   * under any key at all.
   *
   * `writes` alone cannot do that, though its comment used to claim it could:
   * knowing WHICH keys were written says nothing about what was in them. The
   * gap was measured -- adding one `storage.write` of the credential under a
   * new id to `SettingsStore.setSecret` survived the entire core suite,
   * because the one test that watches for a leak reads a single document by
   * name. Rule 1 of core/src/ports/secrets.ts is "a secret never passes
   * through StoragePort", not "not through settings/app".
   */
  readonly writtenValues: readonly string[];
  /** Force the next call to reject, to exercise the failure path. */
  failNext(error: string): void;
}

const compose = (key: StorageKey): string => `${key.namespace}/${key.id}`;

export function createFakeStorage(): FakeStorage {
  const store = new Map<string, string>();
  const writes: StorageKey[] = [];
  const writtenValues: string[] = [];
  let pendingFailure: string | null = null;

  const check = (): void => {
    if (pendingFailure === null) return;
    const message = pendingFailure;
    pendingFailure = null;
    throw new Error(message);
  };

  return {
    writes,
    writtenValues,
    failNext(error) {
      pendingFailure = error;
    },
    async read(key) {
      check();
      // null, never undefined. Absence is a value here, and the two are
      // different to `??` in a caller.
      return store.get(compose(key)) ?? null;
    },
    async write(key, value) {
      check();
      writes.push(key);
      writtenValues.push(value);
      store.set(compose(key), value);
    },
    async remove(key) {
      check();
      // Removing an absent key succeeds -- the caller wanted it gone and it is.
      store.delete(compose(key));
    },
    async listIds(namespace: Namespace) {
      check();
      const prefix = `${namespace}/`;
      return [...store.keys()]
        .filter((k) => k.startsWith(prefix))
        .map((k) => k.slice(prefix.length));
    },
    async clear(namespace: Namespace) {
      check();
      const prefix = `${namespace}/`;
      for (const k of [...store.keys()]) if (k.startsWith(prefix)) store.delete(k);
    },
  };
}
