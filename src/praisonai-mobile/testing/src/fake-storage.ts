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
  /** Every key ever written, so a test can assert a secret never landed here. */
  readonly writes: readonly StorageKey[];
  /** Force the next call to reject, to exercise the failure path. */
  failNext(error: string): void;
}

const compose = (key: StorageKey): string => `${key.namespace}/${key.id}`;

export function createFakeStorage(): FakeStorage {
  const store = new Map<string, string>();
  const writes: StorageKey[] = [];
  let pendingFailure: string | null = null;

  const check = (): void => {
    if (pendingFailure === null) return;
    const message = pendingFailure;
    pendingFailure = null;
    throw new Error(message);
  };

  return {
    writes,
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
