/**
 * Moving an existing install's conversations from one StoragePort to another.
 *
 * WHY IT IS WARRANTED. Every Tauri build up to now wrote chats and settings to
 * `localStorage`, because `platform.ts` handed the web adapter to both
 * platforms. Switching the Tauri build to the native file store without this
 * would not lose that data to a bug -- it would lose it to the change itself:
 * the next launch reads an empty store, `list()` returns nothing, and every
 * conversation the user had is simply not there. The user cannot tell that
 * apart from the eviction bug this change exists to fix, which would make the
 * fix indistinguishable from the disease.
 *
 * It is cheap, one-time, and testable, and the alternative -- "the app has not
 * shipped, so nobody has data" -- is a claim about other people's devices that
 * nobody in this repo can check. Dev builds, TestFlight builds and sideloads
 * all have real `localStorage` today.
 *
 * THREE RULES, each of which is a way this could destroy what it is protecting:
 *
 *  - It never OVERWRITES. A key already in the target wins, always. Running
 *    twice, or running after the user has already had a session on the new
 *    store, must not roll a conversation back to its older copy.
 *  - It never DELETES the source. The old copy stays where it was, so a
 *    rollback to a previous build finds its data intact. `localStorage` is
 *    evictable, which is why it is not the destination -- but a copy that
 *    might be evicted is strictly better than one that was deleted.
 *  - It is marked DONE in the target, not in the source. The source is the
 *    thing that can disappear; a marker written there would be lost with it
 *    and the migration would run again over an emptied store forever.
 */
import type { Namespace, StoragePort } from "../../../core/src/ports/storage.ts";

/**
 * Written to the target once the copy has finished.
 *
 * In `cache` because it is derived state: clearing the cache namespace at
 * worst re-runs a migration that copies nothing, since every key it would copy
 * is already present and skipped.
 */
export const MIGRATION_MARKER = { namespace: "cache", id: "migrated-from-web-storage" } as const;

/**
 * The namespaces worth carrying over.
 *
 * `cache` is deliberately absent: it is by definition rebuildable, and copying
 * it would also copy the marker, which would make a second migration think it
 * had already run before it had copied anything.
 */
export const MIGRATED_NAMESPACES: readonly Namespace[] = ["chats", "settings", "drafts"];

export interface MigrationResult {
  /** Keys actually copied. `0` with `ran: true` is a clean install. */
  readonly copied: number;
  /** Keys skipped because the target already had them. */
  readonly kept: number;
  /** False when the marker said this had already happened. */
  readonly ran: boolean;
}

/**
 * Copy every key the app cares about from `from` into `to`, once.
 *
 * Throws if the TARGET cannot be read or written -- that is the store the app
 * is about to depend on, and a failure there is worth surfacing. A failure
 * reading the SOURCE is not fatal: `localStorage` may be gone (evicted, or a
 * host that has none), which is precisely the situation with nothing to
 * migrate.
 */
export async function migrateStorage(
  from: StoragePort,
  to: StoragePort,
): Promise<MigrationResult> {
  if ((await to.read(MIGRATION_MARKER)) !== null) {
    return { copied: 0, kept: 0, ran: false };
  }

  let copied = 0;
  let kept = 0;

  for (const namespace of MIGRATED_NAMESPACES) {
    let ids: readonly string[];
    try {
      ids = await from.listIds(namespace);
    } catch {
      // No source to read. Not an error: an install with no old data is the
      // common case, and refusing to boot over it would be absurd.
      continue;
    }

    for (const id of ids) {
      const key = { namespace, id };
      // Never overwrite. The target's copy is the newer one by construction --
      // it can only exist because the app already wrote it on the new store.
      if ((await to.read(key)) !== null) {
        kept += 1;
        continue;
      }
      let value: string | null;
      try {
        value = await from.read(key);
      } catch {
        continue; // one unreadable key must not abandon the rest
      }
      if (value === null) continue;
      await to.write(key, value);
      copied += 1;
    }
  }

  // Written LAST. A marker written first would, on a crash mid-copy, declare a
  // half-finished migration complete and strand whatever had not been copied.
  await to.write(MIGRATION_MARKER, JSON.stringify({ copied, kept }));
  return { copied, kept, ran: true };
}

/**
 * `target`, with a one-time preparation step that every call awaits.
 *
 * `detectPlatform` is synchronous -- `ShellPort.insets` has to be readable
 * during the first paint, and platform.ts's header explains why that decision
 * cannot become a promise. So the migration cannot happen during detection. It
 * happens on the first storage call instead, and every StoragePort method is
 * already async, so no signature above this changes.
 *
 * The promise is memoised, so ten concurrent reads at boot run one migration
 * rather than ten interleaved ones.
 *
 * A failed migration does NOT take the store down with it. The new store still
 * works; the old data is still in `localStorage` and can be tried again next
 * launch, because the marker is only written on success. Blocking every read
 * on it would turn "we could not copy your old chats" into "the app does not
 * start".
 */
export function preparedStorage(
  target: StoragePort,
  prepare: () => Promise<unknown>,
  onError: (error: unknown) => void = (error) => console.warn("storage-migration", error),
): StoragePort {
  let started: Promise<void> | null = null;

  const ready = (): Promise<void> => {
    started ??= prepare().then(
      () => {},
      (error: unknown) => {
        onError(error);
      },
    );
    return started;
  };

  return {
    async read(key) {
      await ready();
      return target.read(key);
    },
    async write(key, value) {
      await ready();
      return target.write(key, value);
    },
    async remove(key) {
      await ready();
      return target.remove(key);
    },
    async listIds(namespace) {
      await ready();
      return target.listIds(namespace);
    },
    async clear(namespace) {
      await ready();
      return target.clear(namespace);
    },
  };
}
