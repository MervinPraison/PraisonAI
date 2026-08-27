/**
 * Persistence, as opaque strings.
 *
 * Serialisation deliberately does NOT live here. core/src/chat/repository.ts
 * owns the JSON shape and the schema version, so swapping the backing store --
 * a Tauri store file, SQLite, AsyncStorage, OPFS -- changes no format and can
 * lose no data. An adapter that knew the shape would have to be migrated in
 * lockstep with every format change, which is precisely the coupling this
 * package exists to avoid.
 */

export type Namespace = "chats" | "settings" | "drafts" | "cache";

/** A bare string key is unrepresentable, so every write is namespaced by
 *  construction rather than by convention. */
export interface StorageKey {
  readonly namespace: Namespace;
  readonly id: string;
}

export interface StoragePort {
  /** `null` for a missing key. Absence is not an error; only I/O failure is. */
  read(key: StorageKey): Promise<string | null>;

  /**
   * Atomic: a concurrent read sees either the old value or the new one, never a
   * truncated file.
   *
   * On mobile this is a data-loss bug rather than a theoretical one -- iOS can
   * kill a suspended app with no further callback, so a write interrupted
   * halfway is a normal occurrence rather than a crash scenario.
   */
  write(key: StorageKey, value: string): Promise<void>;

  /** Removing an absent key succeeds. */
  remove(key: StorageKey): Promise<void>;

  listIds(namespace: Namespace): Promise<readonly string[]>;

  clear(namespace: Namespace): Promise<void>;
}
