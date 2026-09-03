/**
 * StoragePort over the native file store in `src-tauri/src/store.rs`.
 *
 * WHY THIS EXISTS. Until now the Tauri build used `adapters/src/web/storage.ts`
 * -- `localStorage` -- and `platform.ts` said so in a comment it called "the
 * honest interim". On iOS `localStorage` lives in a WebKit data store the
 * system may EVICT under storage pressure, so a user who does nothing wrong can
 * open the app and find their history gone, with no error and nothing to
 * report. Android's WebView survives that but is emptied by ordinary "clear
 * cache" flows. `ui/src/i18n/strings.ts` meanwhile tells the user after a crash
 * that "Your conversations are saved"; this adapter is what makes the sentence
 * true on a device.
 *
 * The five commands are all this file knows. Serialisation stays in
 * `core/src/chat/repository.ts` exactly as the port's header requires, so the
 * JSON shape and the schema version are unchanged by the swap and no migration
 * of FORMAT is needed -- only of location, which `../storage/migrate.ts` does.
 *
 * `invokeStrict`, not `invoke`. The bridge's forgiving `invoke` resolves to
 * `null` on failure, and `null` is `StoragePort.read`'s word for "no such
 * key". Built on that, a failing disk would present as an empty chat list --
 * the conversations look deleted rather than unreadable, and the next save
 * writes over them.
 */
import type { Namespace, StorageKey, StoragePort } from "../../../core/src/ports/storage.ts";

/**
 * The seam with `src-tauri/src/store.rs`, which declares the same five
 * strings as `pub const`s. `tools/storage-seam.test.mjs` reads both files and
 * compares them: a rename on one side alone is silent, and silent here means
 * every chat write rejects while the app carries on looking fine.
 */
export const STORAGE_COMMANDS = {
  read: "storage_read",
  write: "storage_write",
  remove: "storage_remove",
  listIds: "storage_list_ids",
  clear: "storage_clear",
} as const;

/** What `TauriBridge.invokeStrict` provides. Taken as a function rather than
 *  as the whole bridge so this file is testable with four lines of stub, and
 *  so a React Native port supplies its own without pretending to be Tauri. */
export type StrictInvoke = (
  command: string,
  args?: Record<string, unknown>,
) => Promise<unknown>;

export interface TauriStorageDeps {
  readonly invoke: StrictInvoke;
}

/**
 * A reply that is not the shape the command promises is an I/O FAILURE, not an
 * absence.
 *
 * The distinction is the whole reason this function exists. If a native reply
 * of `undefined` -- a command name that no longer exists, a Tauri version that
 * returns something else -- were read as `null`, every chat would read as
 * missing, `list()` would return nothing, and the app would show an empty
 * conversation list with no error at all. Throwing puts it through
 * `repository.load`'s `unreadable` branch, which the UI already reports.
 */
function asStringOrNull(command: string, value: unknown): string | null {
  if (value === null) return null;
  if (typeof value === "string") return value;
  throw new Error(`${command} returned ${typeof value}, not a string or null`);
}

function asStringArray(command: string, value: unknown): readonly string[] {
  if (!Array.isArray(value)) {
    throw new Error(`${command} returned ${typeof value}, not an array`);
  }
  for (const entry of value) {
    if (typeof entry !== "string") {
      throw new Error(`${command} returned a non-string id: ${typeof entry}`);
    }
  }
  return value as readonly string[];
}

export function createTauriStorage(deps: TauriStorageDeps): StoragePort {
  // The argument names are the Rust parameter names. Tauri maps a JS key onto
  // a `snake_case` Rust parameter, and every one of these is a single
  // lowercase word precisely so there is no case convention to get wrong -- a
  // mismatch is a deserialisation error on EVERY call, reported to the webview
  // as "storage failed" with nothing pointing at the cause.
  const of = (key: StorageKey): Record<string, unknown> => ({
    namespace: key.namespace,
    id: key.id,
  });

  return {
    async read(key) {
      const value = await deps.invoke(STORAGE_COMMANDS.read, of(key));
      return asStringOrNull(STORAGE_COMMANDS.read, value);
    },

    async write(key, value) {
      // Atomicity lives in Rust: temp file, fsync, rename, fsync the
      // directory. It cannot live here -- a webview has no way to make two
      // IPC calls atomic -- which is exactly why the port's contract had to be
      // satisfied one layer down. See src-tauri/src/store.rs.
      await deps.invoke(STORAGE_COMMANDS.write, { ...of(key), value });
    },

    async remove(key) {
      await deps.invoke(STORAGE_COMMANDS.remove, of(key));
    },

    async listIds(namespace: Namespace) {
      const ids = await deps.invoke(STORAGE_COMMANDS.listIds, { namespace });
      return asStringArray(STORAGE_COMMANDS.listIds, ids);
    },

    async clear(namespace: Namespace) {
      await deps.invoke(STORAGE_COMMANDS.clear, { namespace });
    },
  };
}
