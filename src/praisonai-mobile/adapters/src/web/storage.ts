/**
 * StoragePort over localStorage.
 *
 * The web adapter exists so the whole app runs in a desktop browser with no
 * Tauri at all. That is not a convenience: having a second implementation of
 * every port BEFORE shipping is what proves the seam is a seam rather than an
 * interface shaped around its only implementation.
 *
 * localStorage is synchronous and the port is async. That is deliberate -- the
 * port has to accommodate SQLite and a Rust command, so the narrower backend
 * adapts upward rather than the interface adapting downward.
 */
import type { Namespace, StorageKey, StoragePort } from "../../../core/src/ports/storage.ts";

const PREFIX = "praisonai.";
const compose = (key: StorageKey): string => `${PREFIX}${key.namespace}.${key.id}`;

export function createWebStorage(backing: Storage): StoragePort {
  return {
    async read(key) {
      // getItem returns null for a missing key, which is exactly the contract.
      return backing.getItem(compose(key));
    },

    async write(key, value) {
      // localStorage writes are atomic per key, satisfying the contract's
      // "a concurrent read sees the old value or the new one, never a
      // truncated one". A file-backed adapter has to work for this.
      backing.setItem(compose(key), value);
    },

    async remove(key) {
      backing.removeItem(compose(key));
    },

    async listIds(namespace: Namespace) {
      const prefix = `${PREFIX}${namespace}.`;
      const ids: string[] = [];
      for (let i = 0; i < backing.length; i++) {
        const key = backing.key(i);
        if (key !== null && key.startsWith(prefix)) ids.push(key.slice(prefix.length));
      }
      return ids;
    },

    async clear(namespace: Namespace) {
      const prefix = `${PREFIX}${namespace}.`;
      const doomed: string[] = [];
      for (let i = 0; i < backing.length; i++) {
        const key = backing.key(i);
        if (key !== null && key.startsWith(prefix)) doomed.push(key);
      }
      // Collected first, then removed: removing while iterating by index
      // shifts the remaining entries and silently skips every other one.
      for (const key of doomed) backing.removeItem(key);
    },
  };
}
