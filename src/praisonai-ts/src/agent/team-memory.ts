/**
 * The shared memory an AgentTeam holds on behalf of its tasks.
 *
 * Python parity: `AgentTeam(memory=...)` builds one `Memory` for the whole team
 * and assigns it to every task that did not bring its own. The effect on a run
 * is in `_prepare_task_prompt`: retrieved memory is appended to the task prompt
 * (bare bullet lines, no section headers), and each finished task writes its
 * result back. This module is that effect, held by the team rather than pushed
 * into member agents -- an Agent's own `memory=` stays its own.
 */

import { Logger } from '../utils/logger';
import { Memory, type MemoryConfig } from '../memory/memory';
import { notYetHonoured } from '../utils/parity-notice';

/** The minimum a team memory store must do. Matches `Agent`'s memory contract. */
export interface TeamMemoryStore {
  search(query: string, limit?: number): Promise<Array<{ entry: { content: string; role: string; metadata?: Record<string, any> }; score: number }>>;
  add(content: string, role: 'user' | 'assistant' | 'system', metadata?: Record<string, any>): Promise<unknown>;
}

/** The value `AgentTeam({ memory })` accepts. */
export type TeamMemoryInput =
  | boolean
  | string
  | MemoryConfig
  | TeamMemoryStore
  | { userId?: string; user_id?: string; config?: MemoryConfig; [key: string]: unknown };

/** What {@link resolveTeamMemory} works out from the `memory` option. */
export interface TeamMemorySettings {
  /** Python parity: AgentTeam.shared_memory. Undefined when memory is off. */
  store?: TeamMemoryStore;
  /** A memory file to open lazily (needs fs, so it is deferred to first use). */
  file?: string;
  /** Python parity: AgentTeam.user_id (default "praison"). */
  userId: string;
}

function looksLikeStore(value: unknown): value is TeamMemoryStore {
  const store = value as TeamMemoryStore | undefined;
  return !!store && typeof store.search === 'function' && typeof store.add === 'function';
}

/**
 * Resolve `memory` into a shared store, mirroring what Python's resolver
 * accepts: `False`/`None` off, `True` on with defaults, a config, a memory
 * instance, or a `MultiAgentMemoryConfig`-shaped object carrying `user_id`.
 */
export function resolveTeamMemory(value: unknown): TeamMemorySettings {
  const off: TeamMemorySettings = { userId: 'praison' };
  if (value === undefined || value === null || value === false) return off;
  if (value === true) return { store: new Memory(), userId: 'praison' };

  if (typeof value === 'string' && /[\/\\]|\.jsonl?$/.test(value)) return { file: value, userId: 'praison' };

  if (looksLikeStore(value)) return { store: value, userId: 'praison' };

  if (value && typeof value === 'object') {
    const source = value as Record<string, unknown>;
    const userId = typeof source.userId === 'string' ? source.userId
      : typeof source.user_id === 'string' ? source.user_id
        : 'praison';
    const inner = source.config;
    if (looksLikeStore(inner)) return { store: inner, userId };
    const config = (inner && typeof inner === 'object' ? inner : source) as MemoryConfig;
    return { store: new Memory(config), userId };
  }

  const unusable = typeof value === 'string'
    ? `Provider preset ${JSON.stringify(value)} is not available`
    : `A ${typeof value} is not a memory config`;
  notYetHonoured('AgentTeam', 'memory', `${unusable}; pass true, a MemoryConfig, a file path or a memory instance.`);
  return off;
}

/**
 * The team's shared memory: recall before a task, remember after it.
 *
 * Created only when `memory` is truthy, so a team without it does no work and
 * allocates no store.
 */
export class TeamMemory {
  private store?: TeamMemoryStore;
  private readonly file?: string;
  /** Python parity: AgentTeam.user_id. */
  readonly userId: string;

  constructor(settings: TeamMemorySettings) {
    this.store = settings.store;
    this.file = settings.file;
    this.userId = settings.userId;
  }

  /** The underlying store (Python parity: `team.shared_memory`), if open. */
  getStore(): TeamMemoryStore | undefined {
    return this.store;
  }

  private async ensureStore(): Promise<TeamMemoryStore | undefined> {
    if (!this.store && this.file) {
      const { FileMemory } = await import('../memory/file-memory');
      const store = new FileMemory({ filePath: this.file });
      await store.initialize();
      this.store = store as unknown as TeamMemoryStore;
    }
    return this.store;
  }

  /**
   * Memory relevant to `prompt`, formatted the way Python appends it to a task
   * prompt: bare bullet lines, no section header. Empty string when nothing is
   * recalled, so the caller can leave the prompt untouched.
   */
  async recall(prompt: string, limit: number = 3): Promise<string> {
    const store = await this.ensureStore();
    if (!store) return '';
    try {
      // Search wide, then keep only this team's own entries. A store shared
      // across teams/users tags each write with its userId (see `remember`);
      // untagged entries predate scoping and stay visible. Without this filter
      // a reused store leaks one user's memories into another's prompt.
      const hits = await store.search(prompt, Math.max(limit, 10));
      const lines = hits
        .filter((hit) => this.ownedByTeam(hit?.entry?.metadata))
        .map((hit) => (hit?.entry?.content ?? '').trim())
        .filter((content) => content.length > 0)
        .slice(0, limit)
        .map((content) => `• ${content}`);
      return lines.join('\n');
    } catch (error) {
      await Logger.warn('Team memory recall failed:', error);
      return '';
    }
  }

  /** An entry belongs to this team when its userId matches, or it carries none. */
  private ownedByTeam(metadata?: Record<string, any>): boolean {
    const owner = metadata?.userId ?? metadata?.user_id;
    return owner === undefined || owner === null || owner === this.userId;
  }

  /** Write a finished task back to the shared store. */
  async remember(prompt: string, result: string, taskName: string): Promise<void> {
    const store = await this.ensureStore();
    if (!store) return;
    try {
      await store.add(prompt, 'user', { task: taskName, userId: this.userId });
      if (result) await store.add(result, 'assistant', { task: taskName, userId: this.userId });
    } catch (error) {
      await Logger.warn('Team memory write failed:', error);
    }
  }
}

/** Build the team's shared memory, or undefined when `memory` is off. */
export function createTeamMemory(value: unknown): { memory?: TeamMemory; userId: string } {
  const settings = resolveTeamMemory(value);
  if (!settings.store && !settings.file) return { userId: settings.userId };
  return { memory: new TeamMemory(settings), userId: settings.userId };
}
