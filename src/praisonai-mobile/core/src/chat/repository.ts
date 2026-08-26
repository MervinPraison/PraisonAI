/**
 * Chat persistence.
 *
 * The JSON shape and the schema version live HERE, not in an adapter. That is
 * the point of StoragePort taking opaque strings: swapping the backing store --
 * a Tauri store file, SQLite, AsyncStorage, OPFS -- changes no format and can
 * lose no data. An adapter that knew the shape would have to be migrated in
 * lockstep with every format change.
 *
 * Two rules that are not obvious:
 *
 *  - A future schemaVersion is REFUSED, not truncated. Reading a newer file
 *    with an older client and silently dropping the fields it does not
 *    understand turns a version skew into data loss on the next write.
 *
 *  - A chat that fails to parse is reported, not skipped. One corrupt file
 *    must not make a conversation quietly vanish from the list.
 */
import type { StoragePort } from "../ports/storage.ts";

/** Bump only when the shape changes incompatibly. */
export const SCHEMA_VERSION = 1;

export interface StoredMessage {
  readonly role: "user" | "assistant";
  readonly content: string;
  readonly at: number;
}

export interface StoredChat {
  readonly id: string;
  readonly title: string;
  readonly updated: number;
  readonly messages: readonly StoredMessage[];
  /** Which engine produced this transcript. Recorded so a chat opened after an
   *  engine swap can say so rather than silently mixing conventions. */
  readonly engineId: string;
}

interface ChatFile {
  readonly schemaVersion: number;
  readonly chat: StoredChat;
}

export interface ChatSummary {
  readonly id: string;
  readonly title: string;
  readonly updated: number;
}

export type LoadResult =
  | { readonly ok: true; readonly chat: StoredChat }
  | { readonly ok: false; readonly reason: "missing" | "unreadable" | "too_new"; readonly detail: string };

export interface ChatRepository {
  save(chat: StoredChat): Promise<void>;
  load(id: string): Promise<LoadResult>;
  list(): Promise<readonly ChatSummary[]>;
  remove(id: string): Promise<void>;
  /** Ids that could not be read, so a corrupt file is visible rather than a
   *  conversation that quietly disappeared. */
  listUnreadable(): Promise<readonly string[]>;
}

export function createChatRepository(storage: StoragePort): ChatRepository {
  const readFile = async (id: string): Promise<LoadResult> => {
    let raw: string | null;
    try {
      raw = await storage.read({ namespace: "chats", id });
    } catch (error) {
      return { ok: false, reason: "unreadable", detail: String(error) };
    }
    if (raw === null) return { ok: false, reason: "missing", detail: id };

    let parsed: unknown;
    try {
      parsed = JSON.parse(raw);
    } catch {
      return { ok: false, reason: "unreadable", detail: raw.slice(0, 80) };
    }

    if (parsed === null || typeof parsed !== "object") {
      return { ok: false, reason: "unreadable", detail: typeof parsed };
    }

    const file = parsed as Partial<ChatFile>;
    const version = typeof file.schemaVersion === "number" ? file.schemaVersion : 0;

    if (version > SCHEMA_VERSION) {
      // Refuse rather than read what we recognise. Dropping unknown fields and
      // writing back turns a version skew into permanent data loss.
      return {
        ok: false,
        reason: "too_new",
        detail: `schemaVersion ${version} > ${SCHEMA_VERSION}`,
      };
    }

    const chat = file.chat;
    if (chat === undefined || typeof chat !== "object" || typeof chat.id !== "string") {
      return { ok: false, reason: "unreadable", detail: "no chat object" };
    }

    return {
      ok: true,
      chat: {
        id: chat.id,
        title: typeof chat.title === "string" ? chat.title : "Untitled",
        updated: typeof chat.updated === "number" ? chat.updated : 0,
        messages: Array.isArray(chat.messages) ? chat.messages : [],
        engineId: typeof chat.engineId === "string" ? chat.engineId : "unknown",
      },
    };
  };

  return {
    async save(chat) {
      const file: ChatFile = { schemaVersion: SCHEMA_VERSION, chat };
      await storage.write({ namespace: "chats", id: chat.id }, JSON.stringify(file));
    },

    load: readFile,

    async list() {
      const ids = await storage.listIds("chats");
      const summaries: ChatSummary[] = [];
      for (const id of ids) {
        const result = await readFile(id);
        if (!result.ok) continue; // surfaced separately by listUnreadable
        summaries.push({
          id: result.chat.id,
          title: result.chat.title,
          updated: result.chat.updated,
        });
      }
      // Most recent first -- the order a chat list is always read in.
      return summaries.sort((a, b) => b.updated - a.updated);
    },

    async remove(id) {
      await storage.remove({ namespace: "chats", id });
    },

    async listUnreadable() {
      const ids = await storage.listIds("chats");
      const bad: string[] = [];
      for (const id of ids) {
        const result = await readFile(id);
        if (!result.ok && result.reason !== "missing") bad.push(id);
      }
      return bad;
    },
  };
}
