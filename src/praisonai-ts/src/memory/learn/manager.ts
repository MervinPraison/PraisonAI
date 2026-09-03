/**
 * LearnManager - central manager for continuous learning capabilities.
 *
 * Python parity: praisonaiagents/memory/learn/manager.py
 *
 * Coordinates every learning store according to `LearnConfig` and exposes a
 * single capture / retrieve surface (manager.py:24-40).
 *
 * Mode semantics (`LearnConfig.mode`) are not applied inside the Python
 * manager; the agent applies them in
 * `agent/memory_mixin.py:704-772` (`_process_auto_learning`). That dispatch
 * is ported here as {@link LearnManager.processAutoLearning} so the manager
 * is usable stand-alone:
 * - DISABLED (default): no automatic extraction, manual capture only.
 * - AGENTIC: extract and store after each conversation.
 * - PROPOSE: extract, but queue in `pendingLearnings` for approval.
 */

import { LearnBackend, LearnMode, LearnScope, type LearnConfig } from '../../config/index';
import { BaseLLM } from '../../llm/index';
import { Logger } from '../../utils/logger';
import {
  toLearnEntryDict,
  type LearnEntryData,
  type LearnManagerProtocol,
  type LearnMessage,
  type LearnProtocol,
  type ProcessConversationResult,
} from './protocols';
import {
  BaseStore,
  DecisionStore,
  FeedbackStore,
  ImprovementStore,
  InsightStore,
  LearnEntry,
  MongoDBLearnBackend,
  PatternStore,
  PersonaStore,
  RedisLearnBackend,
  SQLiteLearnBackend,
  ThreadStore,
  type LearnStorageBackend,
} from './stores';

// ============================================================================
// Config
// ============================================================================

/**
 * Full learn configuration accepted by {@link LearnManager}.
 *
 * Extends the package-level {@link LearnConfig} (config/index.ts) with the
 * fields Python's dataclass has and the TS interface does not yet carry.
 * Python parity: praisonaiagents/config/feature_configs.py:143-197 (`LearnConfig`)
 */
export interface LearnManagerConfig extends Omit<LearnConfig, 'scope'> {
  /** feature_configs.py:170 */
  persona?: boolean;
  /** feature_configs.py:171 */
  insights?: boolean;
  /** feature_configs.py:172 */
  thread?: boolean;
  /** feature_configs.py:173 */
  patterns?: boolean;
  /** feature_configs.py:174 */
  decisions?: boolean;
  /** feature_configs.py:175 */
  feedback?: boolean;
  /** feature_configs.py:176 */
  improvements?: boolean;
  /** feature_configs.py:179 (`nudge_interval`, 0 = disabled) */
  nudgeInterval?: number;
  /** feature_configs.py:180 (`nudge_min_tool_iters`) */
  nudgeMinToolIters?: number;
  /** feature_configs.py:181 (`propose_skills`) */
  proposeSkills?: boolean;
  /** feature_configs.py:184 (`mode`, default DISABLED) */
  mode?: LearnMode | 'disabled' | 'agentic' | 'propose';
  /** feature_configs.py:187 (`scope`, default PRIVATE) */
  scope?: LearnScope | 'private' | 'shared';
  /** feature_configs.py:190 (`backend`, default FILE) */
  backend?: LearnBackend | 'file' | 'sqlite' | 'redis' | 'mongodb' | string;
  /** feature_configs.py:191 (`db_url`) */
  dbUrl?: string | null;
  /** feature_configs.py:192 (`store_path`) */
  storePath?: string;
  /** feature_configs.py:195 (`max_entries`, 0 = unbounded) */
  maxEntries?: number;
  /** feature_configs.py:196 (`retention_days`, 0 = never) */
  retentionDays?: number;
  /** feature_configs.py:199 (`llm` model name for extraction) */
  llm?: string | null;
}

/** `LearnManagerConfig` with every Python default applied. */
export type ResolvedLearnConfig = Required<
  Omit<LearnManagerConfig, 'dbUrl' | 'storePath' | 'llm' | 'autoConsolidate'>
> & {
  dbUrl: string | null;
  storePath: string | null;
  llm: string | null;
  autoConsolidate: boolean;
};

/**
 * Apply the Python dataclass defaults (feature_configs.py:169-199).
 */
export function resolveLearnConfig(config?: LearnManagerConfig | null): ResolvedLearnConfig {
  const c = config ?? {};
  return {
    persona: c.persona ?? true,
    insights: c.insights ?? true,
    thread: c.thread ?? true,
    patterns: c.patterns ?? false,
    decisions: c.decisions ?? false,
    feedback: c.feedback ?? false,
    improvements: c.improvements ?? false,
    nudgeInterval: c.nudgeInterval ?? 0,
    nudgeMinToolIters: c.nudgeMinToolIters ?? 3,
    proposeSkills: c.proposeSkills ?? false,
    mode: c.mode ?? LearnMode.DISABLED,
    scope: c.scope ?? LearnScope.PRIVATE,
    backend: c.backend ?? LearnBackend.FILE,
    dbUrl: c.dbUrl ?? null,
    storePath: c.storePath ?? null,
    maxEntries: c.maxEntries ?? 0,
    retentionDays: c.retentionDays ?? 0,
    llm: c.llm ?? null,
    autoConsolidate: c.autoConsolidate ?? false,
  };
}

/**
 * Extraction hook used by `processConversation`. Python's `llm` argument is a
 * model name; the TypeScript port additionally accepts a function so tests and
 * hosts can supply their own extractor without a network call. It receives the
 * extraction prompt and returns the raw JSON text or an already-parsed object.
 */
export type LearnExtractor = (prompt: string) => Promise<string | Record<string, unknown>> | string | Record<string, unknown>;

/** A store the manager can drive: built-in or any `LearnProtocol` implementation. */
export type LearnStore = LearnProtocol;

const EMPTY_RESULT = (): ProcessConversationResult => ({
  persona: [],
  insights: [],
  patterns: [],
  improvements: [],
  stored: {},
});

// ============================================================================
// LearnManager
// ============================================================================

/**
 * Central manager for continuous learning within the memory system.
 * Python parity: praisonaiagents/memory/learn/manager.py:24-716 (`LearnManager`)
 */
export class LearnManager implements LearnManagerProtocol {
  readonly config: ResolvedLearnConfig;
  readonly userId: string;
  readonly storePath: string | null;
  private readonly _backend: LearnStorageBackend | null;
  private readonly _stores: Map<string, LearnStore> = new Map();
  private readonly _customStores: Record<string, LearnStore>;
  private _pending: LearnEntry[] = [];

  /**
   * manager.py:42-171
   *
   * @param config       Enables/disables capabilities; Python defaults applied when omitted.
   * @param userId       Scopes the learnings; `"default"` when omitted (manager.py:78).
   * @param storePath    Custom directory; falls back to `config.storePath` (manager.py:79).
   * @param customStores Extra or overriding stores keyed by name; must implement `LearnProtocol`
   *                     (manager.py:56-58). Custom stores win over built-ins (manager.py:165-168).
   */
  constructor(
    config?: LearnManagerConfig | null,
    userId?: string | null,
    storePath?: string | null,
    customStores?: Record<string, LearnStore> | null,
  ) {
    this.config = resolveLearnConfig(config);
    this.userId = userId || 'default';
    this.storePath = storePath || this.config.storePath || null;

    // manager.py:81-86
    this._backend = this._createBackend();
    if (this._backend !== null) {
      void Logger.info(`LearnManager using ${String(this.config.backend)} backend`);
    }

    const scope = String(this.config.scope);
    this._customStores = customStores ?? {};

    // Retention policy, 0 = unbounded (manager.py:95-99)
    const retention = { maxEntries: this.config.maxEntries, retentionDays: this.config.retentionDays };
    const common = { userId: this.userId, scope, backend: this._backend, ...retention };

    // Built-in stores first; custom stores may override (manager.py:101-163)
    if (this.config.persona && !('persona' in this._customStores)) {
      this._stores.set('persona', new PersonaStore({ storePath: this._getStorePath('persona'), ...common }));
    }
    if (this.config.insights && !('insights' in this._customStores)) {
      this._stores.set('insights', new InsightStore({ storePath: this._getStorePath('insights'), ...common }));
    }
    if (this.config.thread && !('threads' in this._customStores)) {
      this._stores.set('threads', new ThreadStore({ storePath: this._getStorePath('threads'), ...common }));
    }
    if (this.config.patterns && !('patterns' in this._customStores)) {
      this._stores.set('patterns', new PatternStore({ storePath: this._getStorePath('patterns'), ...common }));
    }
    if (this.config.decisions && !('decisions' in this._customStores)) {
      this._stores.set('decisions', new DecisionStore({ storePath: this._getStorePath('decisions'), ...common }));
    }
    if (this.config.feedback && !('feedback' in this._customStores)) {
      this._stores.set('feedback', new FeedbackStore({ storePath: this._getStorePath('feedback'), ...common }));
    }
    if (this.config.improvements && !('improvements' in this._customStores)) {
      this._stores.set(
        'improvements',
        new ImprovementStore({ storePath: this._getStorePath('improvements'), ...common }),
      );
    }

    // Custom stores last (manager.py:165-168)
    for (const [name, store] of Object.entries(this._customStores)) {
      this._stores.set(name, store);
    }
  }

  /**
   * Create a storage backend from config; `null` means FILE (manager.py:173-216).
   * Any failure logs a warning and falls back to FILE, exactly like Python.
   */
  private _createBackend(): LearnStorageBackend | null {
    const backend = String(this.config.backend);

    if (backend === 'file') return null;

    if (backend === 'sqlite') {
      try {
        let dbPath = this.config.dbUrl || `${this.storePath || 'learn'}/learn.db`;
        // Strip the sqlite:/// prefix if present (manager.py:189-191).
        if (dbPath.startsWith('sqlite:///')) dbPath = dbPath.slice('sqlite:///'.length);
        return new SQLiteLearnBackend(dbPath, 'learn_store');
      } catch (err) {
        void Logger.warn(`Failed to create SQLite backend: ${(err as Error)?.message ?? err}. Falling back to FILE.`);
        return null;
      }
    }

    if (backend === 'redis') {
      try {
        return new RedisLearnBackend(this.config.dbUrl || 'redis://localhost:6379', 'praison:learn:');
      } catch (err) {
        void Logger.warn(`Failed to create Redis backend: ${(err as Error)?.message ?? err}. Falling back to FILE.`);
        return null;
      }
    }

    if (backend === 'mongodb') {
      try {
        return new MongoDBLearnBackend(this.config.dbUrl || 'mongodb://localhost:27017/', 'praison_learn');
      } catch (err) {
        void Logger.warn(`Failed to create MongoDB backend: ${(err as Error)?.message ?? err}. Falling back to FILE.`);
        return null;
      }
    }

    void Logger.warn(`Unknown learn backend '${backend}'. Falling back to FILE.`);
    return null;
  }

  /** manager.py:218-222 */
  private _getStorePath(storeName: string): string | null {
    if (this.storePath) return `${this.storePath}/${storeName}.json`;
    return null;
  }

  /** The active stores by name (read-only view; Python exposes `_stores`). */
  get stores(): ReadonlyMap<string, LearnStore> {
    return this._stores;
  }

  // --------------------------------------------------------------------------
  // Capture (manager.py:224-279)
  // --------------------------------------------------------------------------

  /** manager.py:224-228 */
  capturePersona(content: string, category: string = 'general'): LearnEntry | null {
    const store = this._stores.get('persona');
    return store instanceof PersonaStore ? store.addPreference(content, category) : null;
  }

  /** manager.py:230-234 */
  captureInsight(content: string, source: string = 'interaction'): LearnEntry | null {
    const store = this._stores.get('insights');
    return store instanceof InsightStore ? store.addInsight(content, source) : null;
  }

  /** manager.py:236-240 */
  captureThread(summary: string, threadId: string): LearnEntry | null {
    const store = this._stores.get('threads');
    return store instanceof ThreadStore ? store.addThreadSummary(summary, threadId) : null;
  }

  /** manager.py:242-246 */
  capturePattern(pattern: string, patternType: string = 'general'): LearnEntry | null {
    const store = this._stores.get('patterns');
    return store instanceof PatternStore ? store.addPattern(pattern, patternType) : null;
  }

  /** manager.py:248-257 */
  captureDecision(decision: string, reasoning: string = '', outcome: string = ''): LearnEntry | null {
    const store = this._stores.get('decisions');
    return store instanceof DecisionStore ? store.addDecision(decision, reasoning, outcome) : null;
  }

  /** manager.py:259-268 */
  captureFeedback(feedback: string, rating: number | null = null, source: string = 'user'): LearnEntry | null {
    const store = this._stores.get('feedback');
    return store instanceof FeedbackStore ? store.addFeedback(feedback, rating, source) : null;
  }

  /** manager.py:270-279 */
  captureImprovement(proposal: string, area: string = 'general', priority: string = 'medium'): LearnEntry | null {
    const store = this._stores.get('improvements');
    return store instanceof ImprovementStore ? store.addImprovement(proposal, area, priority) : null;
  }

  // --------------------------------------------------------------------------
  // Retrieval (manager.py:281-329)
  // --------------------------------------------------------------------------

  /** Entries from every enabled store, keyed by store name (manager.py:281-292). */
  getLearningContext(limitPerStore: number = 5): Record<string, LearnEntryData[]> {
    const context: Record<string, LearnEntryData[]> = {};
    for (const [name, store] of this._stores) {
      context[name] = store.listAll(limitPerStore).map(toLearnEntryDict);
    }
    return context;
  }

  /** Search across all enabled stores; stores with no hits are omitted (manager.py:294-301). */
  search(query: string, limit: number = 10): Record<string, LearnEntryData[]> {
    const results: Record<string, LearnEntryData[]> = {};
    for (const [name, store] of this._stores) {
      const entries = store.search(query, limit);
      if (entries.length > 0) results[name] = entries.map(toLearnEntryDict);
    }
    return results;
  }

  /** manager.py:303-308 */
  getPersonaContext(limit: number = 10): string[] {
    const store = this._stores.get('persona');
    if (!store) return [];
    return store.listAll(limit).map((e) => toLearnEntryDict(e).content);
  }

  /** manager.py:310-315 */
  getInsightsContext(limit: number = 10): string[] {
    const store = this._stores.get('insights');
    if (!store) return [];
    return store.listAll(limit).map((e) => toLearnEntryDict(e).content);
  }

  /** manager.py:317-322 */
  clearAll(): Record<string, number> {
    const cleared: Record<string, number> = {};
    for (const [name, store] of this._stores) cleared[name] = store.clear();
    return cleared;
  }

  /**
   * Entry counts per store (manager.py:324-329). Python reads `store._entries`;
   * custom stores without that attribute count as 0 here instead of throwing.
   */
  getStats(): Record<string, number> {
    const stats: Record<string, number> = {};
    for (const [name, store] of this._stores) {
      if (store instanceof BaseStore) {
        stats[name] = store.entryCount;
      } else {
        const raw = (store as { _entries?: unknown })._entries;
        stats[name] =
          raw instanceof Map ? raw.size : raw && typeof raw === 'object' ? Object.keys(raw as object).length : 0;
      }
    }
    return stats;
  }

  /** Archive stale/excess entries across all stores (manager.py:331-350). */
  prune(): Record<string, number> {
    const pruned: Record<string, number> = {};
    for (const [name, store] of this._stores) {
      const pruneFn = (store as { prune?: () => number }).prune;
      if (typeof pruneFn === 'function') {
        try {
          pruned[name] = pruneFn.call(store);
        } catch (err) {
          void Logger.warn(`Failed to prune store '${name}': ${(err as Error)?.message ?? err}`);
          pruned[name] = 0;
        }
      }
    }
    return pruned;
  }

  // --------------------------------------------------------------------------
  // PROPOSE mode queue (manager.py:352-432)
  // --------------------------------------------------------------------------

  /** Pending learnings awaiting approval - a copy (manager.py:352-355). */
  get pendingLearnings(): LearnEntry[] {
    return [...this._pending];
  }

  /**
   * Queue a learning for user approval (manager.py:357-381).
   *
   * @param content  The learning content.
   * @param category Target store name (`persona`, `insights`, `patterns`, ...).
   * @param metadata Optional metadata; `category` and `status: "pending"` are added.
   */
  addPending(content: string, category: string = 'persona', metadata?: Record<string, any> | null): LearnEntry {
    const entryId = `pending_${category}_${this._pending.length}_${Date.now() / 1000}`;
    const entry = new LearnEntry({
      id: entryId,
      content,
      metadata: { ...(metadata ?? {}), category, status: 'pending' },
    });
    this._pending.push(entry);
    return entry;
  }

  /**
   * Approve a pending learning - move it into its store, or `persona` when the
   * category has no store (manager.py:383-402). Returns `false` if not found.
   */
  approveLearning(entryId: string): boolean {
    const idx = this._pending.findIndex((e) => e.id === entryId);
    if (idx === -1) return false;
    const entry = this._pending[idx];
    const category = String(entry.metadata.category ?? 'persona');
    const target = this._stores.get(category) ?? this._stores.get('persona');
    if (target) target.add(entry.content, entry.metadata);
    this._pending.splice(idx, 1);
    return true;
  }

  /** Discard a pending learning (manager.py:404-417). */
  rejectLearning(entryId: string): boolean {
    const idx = this._pending.findIndex((e) => e.id === entryId);
    if (idx === -1) return false;
    this._pending.splice(idx, 1);
    return true;
  }

  /** Approve every pending learning; returns the count (manager.py:419-432). */
  approveAllLearnings(): number {
    let count = 0;
    while (this._pending.length > 0) {
      if (this.approveLearning(this._pending[0].id)) count += 1;
      else break; // safety
    }
    return count;
  }

  // --------------------------------------------------------------------------
  // Prompt context (manager.py:434-492)
  // --------------------------------------------------------------------------

  /** Formatted learnings for system-prompt injection (manager.py:434-492). Threads are excluded. */
  toSystemPromptContext(): string {
    const parts: string[] = [];

    if (this._stores.has('persona')) {
      const personas = this.getPersonaContext(5);
      if (personas.length > 0) {
        parts.push('User Preferences:');
        for (const p of personas) parts.push(`- ${p}`);
      }
    }

    if (this._stores.has('insights')) {
      const insights = this.getInsightsContext(5);
      if (insights.length > 0) {
        parts.push('\nLearned Insights:');
        for (const i of insights) parts.push(`- ${i}`);
      }
    }

    const sections: Array<[string, string]> = [
      ['patterns', '\nKnown Patterns:'],
      ['decisions', '\nPast Decisions:'],
      ['feedback', '\nUser Feedback:'],
      ['improvements', '\nImprovement Areas:'],
    ];
    for (const [name, header] of sections) {
      const store = this._stores.get(name);
      if (!store) continue;
      const entries = store.listAll(3);
      if (entries.length > 0) {
        parts.push(header);
        for (const e of entries) parts.push(`- ${toLearnEntryDict(e).content}`);
      }
    }

    return parts.length > 0 ? parts.join('\n') : '';
  }

  // --------------------------------------------------------------------------
  // Automatic extraction (manager.py:494-716)
  // --------------------------------------------------------------------------

  /** manager.py:524-551 - identical prompt text. */
  private _buildExtractionPrompt(messages: LearnMessage[]): string {
    const conversationText = messages
      .map((m) => `${m.role ?? 'unknown'}: ${m.content ?? ''}`)
      .join('\n');
    return `Analyze this conversation and extract learnings.

CONVERSATION:
${conversationText}

Extract the following (if present):
1. USER PREFERENCES: Things the user likes, dislikes, prefers, or their style
2. INSIGHTS: Observations about the user's domain, work, or context
3. PATTERNS: Recurring behaviors or request patterns
4. IMPROVEMENTS: Concrete proposals to improve future responses

Return JSON:
{
    "persona": ["preference 1", "preference 2"],
    "insights": ["insight 1", "insight 2"],
    "patterns": ["pattern 1", "pattern 2"],
    "improvements": ["improvement 1", "improvement 2"]
}

Only include items that are clearly evident from the conversation.
Return empty arrays if nothing is found for a category.`;
  }

  /** Call the model (manager.py:558-563 `LLM(model).get_response(prompt, output_json=True)`). */
  private async _extract(prompt: string, llm?: string | LearnExtractor | null): Promise<Record<string, unknown>> {
    let response: unknown;
    if (typeof llm === 'function') {
      response = await llm(prompt);
    } else {
      const model = llm || this.config.llm || 'gpt-4o-mini';
      const client = new BaseLLM({ model, responseFormat: { type: 'json_object' } });
      response = (await client.generate(prompt)).text;
    }
    // manager.py:565-571
    if (typeof response === 'string') return JSON.parse(response);
    if (response && typeof response === 'object') return response as Record<string, unknown>;
    return { persona: [], insights: [], patterns: [], improvements: [] };
  }

  private _asList(value: unknown): string[] {
    return Array.isArray(value) ? value.map((v) => (typeof v === 'string' ? v : String(v ?? ''))) : [];
  }

  /**
   * Process a conversation to extract learnings automatically (manager.py:494-608).
   *
   * @param messages    `{ role, content }` messages.
   * @param llm         Model name (default `gpt-4o-mini`, manager.py:558) or a {@link LearnExtractor}.
   * @param extractOnly Extract without storing (used by PROPOSE mode, memory_mixin.py:731-735).
   */
  async processConversation(
    messages: LearnMessage[],
    llm?: string | LearnExtractor | null,
    extractOnly: boolean = false,
  ): Promise<ProcessConversationResult> {
    if (!messages || messages.length === 0) return EMPTY_RESULT();

    try {
      const extracted = await this._extract(this._buildExtractionPrompt(messages), llm);
      const persona = this._asList(extracted.persona);
      const insights = this._asList(extracted.insights);
      const patterns = this._asList(extracted.patterns);
      const improvements = this._asList(extracted.improvements);

      // manager.py:573-595
      const stored: Record<string, number> = { persona: 0, insights: 0, patterns: 0, improvements: 0 };
      if (!extractOnly) {
        for (const p of persona) {
          if (p && this._stores.has('persona')) {
            this.capturePersona(p);
            stored.persona += 1;
          }
        }
        for (const i of insights) {
          if (i && this._stores.has('insights')) {
            this.captureInsight(i, 'auto_extraction');
            stored.insights += 1;
          }
        }
        for (const pt of patterns) {
          if (pt && this._stores.has('patterns')) {
            this.capturePattern(pt, 'auto_extracted');
            stored.patterns += 1;
          }
        }
        for (const imp of improvements) {
          if (imp && this._stores.has('improvements')) {
            this.captureImprovement(imp, 'auto_extraction');
            stored.improvements += 1;
          }
        }
      }

      return { persona, insights, patterns, improvements, stored };
    } catch (err) {
      const message = (err as Error)?.message ?? String(err);
      void Logger.warn(`Failed to extract learnings: ${message}`);
      return { ...EMPTY_RESULT(), error: message };
    }
  }

  /**
   * Async version of `processConversation` (manager.py:610-716). Always stores
   * (Python's async variant has no `extract_only` parameter).
   */
  async aprocessConversation(
    messages: LearnMessage[],
    llm?: string | LearnExtractor | null,
  ): Promise<ProcessConversationResult> {
    return this.processConversation(messages, llm, false);
  }

  /**
   * Apply `config.mode` to a finished exchange.
   * Python parity: praisonaiagents/agent/memory_mixin.py:704-772 (`_process_auto_learning`)
   *
   * - DISABLED (or unknown): no-op, returns `null` (memory_mixin.py:751-754).
   * - PROPOSE: extract only, then queue persona / insights / patterns as
   *   pending (memory_mixin.py:721-749). Improvements are not queued - Python
   *   does not queue them either.
   * - AGENTIC: extract and store (memory_mixin.py:756-772).
   *
   * `llm` falls back to `config.llm` (memory_mixin.py:733, :770). Errors are
   * swallowed and logged like Python's `logging.debug`.
   */
  async processAutoLearning(
    messages: LearnMessage[],
    llm?: string | LearnExtractor | null,
  ): Promise<ProcessConversationResult | null> {
    const mode = String(this.config.mode);
    const extractor = llm ?? this.config.llm ?? null;

    if (mode === LearnMode.PROPOSE) {
      try {
        if (!messages || messages.length === 0) return null;
        const result = await this.processConversation(messages, extractor, true);
        if (result) {
          for (const p of result.persona) if (p) this.addPending(p, 'persona');
          for (const i of result.insights) if (i) this.addPending(i, 'insights');
          for (const pt of result.patterns) if (pt) this.addPending(pt, 'patterns');
        }
        return result;
      } catch (err) {
        void Logger.debug(`PROPOSE mode learning extraction failed: ${(err as Error)?.message ?? err}`);
        return null;
      }
    }

    if (mode !== LearnMode.AGENTIC) return null;

    try {
      if (!messages || messages.length === 0) return null;
      return await this.processConversation(messages, extractor);
    } catch (err) {
      void Logger.debug(`Auto-learning extraction failed: ${(err as Error)?.message ?? err}`);
      return null;
    }
  }
}
