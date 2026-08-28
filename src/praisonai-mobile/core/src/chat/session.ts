/**
 * The live chat: the user's side of the conversation, and where a turn lands.
 *
 * Until this file existed, `ChatRepository` was fully tested and called by
 * nothing. A turn streamed, rendered, and evaporated. The gap was structural
 * rather than an oversight: `TurnState` is assistant-only, `StoredChat` has
 * both roles, and nothing owned the join.
 *
 * WHO PERSISTS, AND WHY IT IS HERE
 *
 * `end.userIndex` is authoritative and cannot be computed by a client -- a
 * cancelled or errored turn stays on screen and is never written, so screen
 * position and disk position diverge immediately. The only honest source is
 * whatever actually did the write. So this implements `RunPersistence`: the
 * engine asks it to record a turn, and the indices in `end` are the ones this
 * file really produced. `null` means the write failed and the turn is NOT on
 * disk, which is what tells the UI to withhold Fork and Delete.
 *
 * A cancelled or errored turn is never offered here at all -- engines only
 * call `record` on success -- so "not persisted" needs no special case.
 */
import type { StoragePort } from "../ports/storage.ts";
import { createChatRepository, type ChatRepository, type StoredChat, type StoredMessage } from "./repository.ts";

/** What the engine ports call. Mirrors the engine-side interface exactly. */
export interface RecordedIndices {
  readonly userIndex: number;
  readonly assistantIndex: number;
  readonly versions: number;
  readonly active: number;
}

export interface SessionDeps {
  readonly storage: StoragePort;
  readonly engineId: string;
  /** Injected so a test is deterministic and a device is not. */
  readonly now: () => number;
  readonly newChatId: () => string;
}

export interface Session {
  /** The chat being viewed, or null before anything is opened or sent. */
  current(): StoredChat | null;
  open(chatId: string): Promise<boolean>;
  /** Start a fresh chat. The next send creates it on disk. */
  reset(): void;
  /**
   * Called by the engine when a turn succeeded.
   *
   * `prompt` is the user's message. It is written HERE and not when the user
   * pressed send, because a turn that never completes must not leave a
   * dangling user message in a persisted transcript with no reply under it.
   */
  record(prompt: string, answer: string): Promise<RecordedIndices | null>;
  list(): Promise<readonly { id: string; title: string; updated: number }[]>;
  remove(chatId: string): Promise<void>;
  readonly repository: ChatRepository;
}

/** The first line of the first user message, trimmed to something a list row
 *  can show. A chat called "Untitled" forever is a list nobody can scan. */
export function titleFrom(prompt: string): string {
  const line = prompt.split("\n").find((l) => l.trim() !== "")?.trim() ?? "";
  if (line === "") return "Untitled";
  // Cut on a code POINT boundary: slicing by unit splits a surrogate pair and
  // renders a replacement character in the chat list.
  const points = [...line];
  return points.length <= 60 ? line : `${points.slice(0, 59).join("")}…`;
}

export function createSession(deps: SessionDeps): Session {
  const repository = createChatRepository(deps.storage);
  let chat: StoredChat | null = null;

  return {
    current: () => chat,

    async open(chatId) {
      const loaded = await repository.load(chatId);
      if (!loaded.ok) return false;
      chat = loaded.chat;
      return true;
    },

    reset() {
      chat = null;
    },

    async record(prompt, answer) {
      const at = deps.now();
      const user: StoredMessage = { role: "user", content: prompt, at };
      const assistant: StoredMessage = { role: "assistant", content: answer, at };

      const base: StoredChat = chat ?? {
        id: deps.newChatId(),
        title: titleFrom(prompt),
        updated: at,
        messages: [],
        engineId: deps.engineId,
      };

      const messages = [...base.messages, user, assistant];
      const next: StoredChat = { ...base, messages, updated: at };

      try {
        await repository.save(next);
      } catch {
        // The turn is on screen and NOT on disk. Reporting null is what makes
        // the UI withhold Fork and Delete, which would otherwise address a
        // message that does not exist.
        return null;
      }

      chat = next;
      // Indices into the persisted message array, which is the only thing
      // Fork and Delete can address.
      return {
        userIndex: messages.length - 2,
        assistantIndex: messages.length - 1,
        versions: 1,
        active: 0,
      };
    },

    list: () => repository.list(),

    async remove(chatId) {
      await repository.remove(chatId);
      if (chat?.id === chatId) chat = null;
    },

    repository,
  };
}


/**
 * A `Session` seen as the engine's `RunPersistence`.
 *
 * The two halves were designed apart and never reconciled, and that is exactly
 * why nothing was ever wired: `Session.record` takes a prompt, the engine's
 * `RunPersistence.record` takes a whole `RunRequest`, and the signatures do not
 * line up. So the session was built, the port was declared, and no conversation
 * was ever written -- a gap that read as closed from either end.
 *
 * Naming the adapter rather than inlining a lambda at the call site is
 * deliberate: this is the one place the two vocabularies meet, and a lambda
 * buried in composition is a seam nobody can find later.
 *
 * `chatId` is deliberately NOT used to switch chats here. The session already
 * knows which conversation is open; taking direction from the request instead
 * would let an in-flight turn write into whichever chat the user has since
 * navigated to.
 */
export function persistenceFor(session: Session): {
  record(request: { readonly prompt: string }, answer: string): Promise<RecordedIndices | null>;
} {
  return {
    record: (request, answer) => session.record(request.prompt, answer),
  };
}
