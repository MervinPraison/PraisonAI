/**
 * Unit tests for src/memory/learn (Python parity: praisonaiagents/memory/learn).
 * Every store writes under a fresh temp directory; nothing touches the network.
 */
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import {
  LearnManager,
  LearnMode,
  LearnEntry,
  PersonaStore,
  InsightStore,
  FeedbackStore,
  SQLiteLearnBackend,
  RedisLearnBackend,
  MongoDBLearnBackend,
  LearnBackendNotAvailableError,
  LearnError,
  getLearnDir,
  resolveLearnConfig,
} from '../../../../src/memory/learn';
import { PraisonAIError } from '../../../../src/errors';
import { LearnBackend, LearnScope } from '../../../../src/config/index';
import { Logger } from '../../../../src/utils/logger';

let tmpRoot: string;
const originalHome = process.env.PRAISONAI_HOME;

beforeEach(() => {
  tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'praison-learn-'));
  // Route the default store location into the temp dir (paths.py:131 PRAISONAI_HOME wins).
  process.env.PRAISONAI_HOME = tmpRoot;
});

afterEach(() => {
  if (originalHome === undefined) delete process.env.PRAISONAI_HOME;
  else process.env.PRAISONAI_HOME = originalHome;
  fs.rmSync(tmpRoot, { recursive: true, force: true });
});

function readJson(p: string): Record<string, any> {
  return JSON.parse(fs.readFileSync(p, 'utf-8'));
}

describe('LearnEntry', () => {
  it('round-trips through the snake_case dict form (stores.py:38-59)', () => {
    const entry = new LearnEntry({ id: 'x', content: 'hello', metadata: { a: 1 } });
    const dict = entry.toDict();
    expect(Object.keys(dict)).toEqual(['id', 'content', 'metadata', 'created_at', 'updated_at', 'use_count', 'last_used']);
    expect(dict.use_count).toBe(0);
    expect(dict.last_used).toBeNull();
    const back = LearnEntry.fromDict(dict);
    expect(back).toBeInstanceOf(LearnEntry);
    expect(back.toDict()).toEqual(dict);
  });
});

describe('file store: remember / recall round trip', () => {
  it('persists an added entry to JSON and finds it via search and listAll', () => {
    const store = new PersonaStore({ storePath: path.join(tmpRoot, 'persona.json') });
    const entry = store.addPreference('User prefers concise answers', 'style');

    expect(entry.id.startsWith('persona_0_')).toBe(true);
    expect(entry.metadata).toEqual({ category: 'style', type: 'preference' });

    const onDisk = readJson(path.join(tmpRoot, 'persona.json'));
    expect(onDisk[entry.id].content).toBe('User prefers concise answers');

    const hits = store.search('CONCISE');
    expect(hits.map((e) => e.id)).toEqual([entry.id]);
    // search touches usage telemetry (stores.py:177-190)
    expect(hits[0].useCount).toBe(1);
    expect(hits[0].lastUsed).not.toBeNull();

    expect(store.listAll().map((e) => e.content)).toEqual(['User prefers concise answers']);
    expect(store.get(entry.id)).toBe(entry);
    expect(store.get('missing')).toBeNull();
  });

  it('deduplicates on normalised content and merges metadata (stores.py:149-159)', () => {
    const store = new InsightStore({ storePath: path.join(tmpRoot, 'insights.json') });
    const first = store.add('Works in data science');
    const second = store.add('  works in DATA science ', { source: 'test' });
    // Python re-reads the store from disk at the top of add() (stores.py:145-148),
    // so the returned duplicate is a freshly deserialised entry, not the same object.
    expect(second).not.toBe(first);
    expect(second.id).toBe(first.id);
    expect(store.entryCount).toBe(1);
    expect(second.metadata).toEqual({ source: 'test' });
    // Control: a genuinely different content string is not deduplicated.
    const third = store.add('works in biology');
    expect(third.id).not.toBe(first.id);
    expect(store.entryCount).toBe(2);
  });

  it('update changes content and merges metadata; clear reports the count', () => {
    const store = new InsightStore({ storePath: path.join(tmpRoot, 'insights.json') });
    const e = store.add('a', { k: 1 });
    const updated = store.update(e.id, 'b', { j: 2 });
    expect(updated?.content).toBe('b');
    expect(updated?.metadata).toEqual({ k: 1, j: 2 });
    expect(store.update('nope', 'c')).toBeNull();
    store.add('second');
    expect(store.clear()).toBe(2);
    expect(readJson(path.join(tmpRoot, 'insights.json'))).toEqual({});
  });

  it('uses <learn dir>/<scope>/<userId>/<store>.json by default (stores.py:121-126)', () => {
    const store = new PersonaStore({ userId: 'alice', scope: 'shared' });
    expect(store.storePath).toBe(path.join(getLearnDir(), 'shared', 'alice', 'persona.json'));
    expect(getLearnDir()).toBe(path.join(tmpRoot, 'learn'));
    expect(fs.existsSync(path.dirname(store.storePath))).toBe(true);
  });
});

describe('forget', () => {
  it('delete removes the entry from memory and disk', () => {
    const store = new PersonaStore({ storePath: path.join(tmpRoot, 'persona.json') });
    const e = store.add('forget me');
    expect(store.delete(e.id)).toBe(true);
    expect(store.delete(e.id)).toBe(false);
    expect(store.get(e.id)).toBeNull();
    expect(readJson(path.join(tmpRoot, 'persona.json'))).toEqual({});
  });

  it('prune archives excess entries to a recoverable sidecar (stores.py:289-343)', () => {
    const store = new PersonaStore({ storePath: path.join(tmpRoot, 'persona.json'), maxEntries: 2 });
    store.add('one');
    store.add('two');
    const third = store.add('three'); // protected on add
    expect(store.entryCount).toBe(2);
    expect(store.get(third.id)).not.toBeNull();
    const archive = readJson(path.join(tmpRoot, 'persona.archive.json')) as unknown as any[];
    expect(archive).toHaveLength(1);
    expect(archive[0].content).toBe('one');
  });
});

describe('persistence across manager instances', () => {
  it('a second LearnManager on the same storePath sees the first one\'s entries', () => {
    const dir = path.join(tmpRoot, 'mgr');
    const first = new LearnManager({ persona: true, insights: true, thread: false }, 'alice', dir);
    first.capturePersona('Prefers dark mode');
    first.captureInsight('Uses TypeScript');

    const second = new LearnManager({ persona: true, insights: true, thread: false }, 'alice', dir);
    expect(second.getStats()).toEqual({ persona: 1, insights: 1 });
    expect(second.getPersonaContext()).toEqual(['Prefers dark mode']);
    expect(second.search('typescript')).toEqual({
      insights: [expect.objectContaining({ content: 'Uses TypeScript' })],
    });
    expect(fs.existsSync(path.join(dir, 'persona.json'))).toBe(true);
  });
});

describe('scope semantics (stores.py:121-126: <scope>/<userId> selects the directory)', () => {
  it('private entries are invisible to another user id', () => {
    const a = new LearnManager({ scope: LearnScope.PRIVATE, thread: false, insights: false }, 'agent-a');
    const b = new LearnManager({ scope: LearnScope.PRIVATE, thread: false, insights: false }, 'agent-b');
    a.capturePersona('secret of a');
    expect(b.getPersonaContext()).toEqual([]);
    expect(a.getPersonaContext()).toEqual(['secret of a']);
    expect(fs.existsSync(path.join(tmpRoot, 'learn', 'private', 'agent-a', 'persona.json'))).toBe(true);
    expect(fs.existsSync(path.join(tmpRoot, 'learn', 'private', 'agent-b', 'persona.json'))).toBe(false);
  });

  it('shared entries are visible to every manager that opens the shared scope for that user id', () => {
    const a = new LearnManager({ scope: 'shared', thread: false, insights: false });
    a.capturePersona('shared fact');
    // Python loads a store's entries at construction and list_all() never re-reads
    // (stores.py:207-213), so a reader opened after the write sees it.
    const b = new LearnManager({ scope: 'shared', thread: false, insights: false });
    expect(b.getPersonaContext()).toEqual(['shared fact']);
    expect(fs.existsSync(path.join(tmpRoot, 'learn', 'shared', 'default', 'persona.json'))).toBe(true);
    // Control: a private-scope reader for the same user does not see the shared entry.
    const priv = new LearnManager({ scope: 'private', thread: false, insights: false });
    expect(priv.getPersonaContext()).toEqual([]);
  });

  it('private and shared scopes for the same user are separate stores', () => {
    const priv = new LearnManager({ scope: 'private', thread: false, insights: false }, 'carol');
    const shared = new LearnManager({ scope: 'shared', thread: false, insights: false }, 'carol');
    priv.capturePersona('private only');
    expect(shared.getPersonaContext()).toEqual([]);
  });
});

describe('mode semantics (memory_mixin.py:704-772)', () => {
  const messages = [
    { role: 'user', content: 'I like short answers' },
    { role: 'assistant', content: 'Noted.' },
  ];
  const extraction = { persona: ['Likes short answers'], insights: ['Is terse'], patterns: ['Asks briefly'], improvements: ['Be shorter'] };

  it('defaults to DISABLED and processAutoLearning is then a no-op', async () => {
    const extractor = jest.fn(async () => extraction);
    const m = new LearnManager(undefined, 'u', path.join(tmpRoot, 'disabled'));
    expect(m.config.mode).toBe(LearnMode.DISABLED);
    expect(await m.processAutoLearning(messages, extractor)).toBeNull();
    expect(extractor).not.toHaveBeenCalled();
    expect(m.getStats()).toEqual({ persona: 0, insights: 0, threads: 0 });
    expect(m.pendingLearnings).toEqual([]);
  });

  it('PROPOSE queues persona/insights/patterns as pending instead of storing', async () => {
    const extractor = jest.fn(async () => JSON.stringify(extraction));
    const m = new LearnManager({ mode: 'propose', patterns: true, improvements: true, thread: false }, 'u', path.join(tmpRoot, 'propose'));
    const result = await m.processAutoLearning(messages, extractor);
    expect(extractor).toHaveBeenCalledTimes(1);
    expect(result?.stored).toEqual({ persona: 0, insights: 0, patterns: 0, improvements: 0 });
    expect(m.getStats()).toEqual({ persona: 0, insights: 0, patterns: 0, improvements: 0 });

    const pending = m.pendingLearnings;
    expect(pending.map((p) => p.metadata.category)).toEqual(['persona', 'insights', 'patterns']);
    expect(pending[0].id.startsWith('pending_persona_0_')).toBe(true);
    expect(pending[0].metadata.status).toBe('pending');

    // approve routes to the matching store; reject discards
    expect(m.approveLearning(pending[1].id)).toBe(true);
    expect(m.getStats().insights).toBe(1);
    expect(m.rejectLearning(pending[2].id)).toBe(true);
    expect(m.rejectLearning('nope')).toBe(false);
    expect(m.approveAllLearnings()).toBe(1);
    expect(m.pendingLearnings).toEqual([]);
    expect(m.getStats()).toEqual({ persona: 1, insights: 1, patterns: 0, improvements: 0 });
  });

  it('AGENTIC extracts and stores immediately', async () => {
    const extractor = jest.fn(async () => extraction);
    const m = new LearnManager({ mode: LearnMode.AGENTIC, patterns: true, improvements: true, thread: false }, 'u', path.join(tmpRoot, 'agentic'));
    const result = await m.processAutoLearning(messages, extractor);
    expect(result?.stored).toEqual({ persona: 1, insights: 1, patterns: 1, improvements: 1 });
    expect(m.pendingLearnings).toEqual([]);
    const ctx = m.getLearningContext();
    expect(ctx.insights[0].metadata).toEqual({ source: 'auto_extraction', type: 'insight' });
    expect(ctx.patterns[0].metadata).toEqual({ pattern_type: 'auto_extracted', type: 'pattern' });
    expect(ctx.improvements[0].metadata).toEqual({ area: 'auto_extraction', priority: 'medium', type: 'improvement' });
  });

  it('processConversation returns the empty shape for no messages and an error dict on failure', async () => {
    const m = new LearnManager({ thread: false }, 'u', path.join(tmpRoot, 'errs'));
    expect(await m.processConversation([])).toEqual({ persona: [], insights: [], patterns: [], improvements: [], stored: {} });
    const warn = jest.spyOn(Logger, 'warn').mockResolvedValue();
    const result = await m.processConversation(messages, async () => 'not json');
    expect(result.error).toBeDefined();
    expect(result.stored).toEqual({});
    warn.mockRestore();
  });
});

describe('unavailable backends', () => {
  it('Redis and MongoDB constructors throw a clear LearnBackendNotAvailableError', () => {
    expect(() => new RedisLearnBackend()).toThrow(LearnBackendNotAvailableError);
    expect(() => new MongoDBLearnBackend()).toThrow(/Learn backend 'mongodb' is not available/);
    try {
      new RedisLearnBackend('redis://x:1');
    } catch (err) {
      const e = err as LearnBackendNotAvailableError;
      expect(e).toBeInstanceOf(LearnError);
      expect(e).toBeInstanceOf(PraisonAIError);
      expect(e.name).toBe('LearnBackendNotAvailableError');
      expect(e.backend).toBe('redis');
      expect(e.message).toMatch(/redis/);
      expect(e.toDict().context.backend).toBe('redis');
    }
  });

  it('LearnManager falls back to FILE with a warning, like Python manager.py:197-213', () => {
    const warn = jest.spyOn(Logger, 'warn').mockResolvedValue();
    const m = new LearnManager({ backend: LearnBackend.REDIS, thread: false, insights: false }, 'u', path.join(tmpRoot, 'redis'));
    expect(warn).toHaveBeenCalledWith(expect.stringMatching(/Failed to create Redis backend.*Falling back to FILE/));
    m.capturePersona('still works');
    expect(fs.existsSync(path.join(tmpRoot, 'redis', 'persona.json'))).toBe(true);
    warn.mockRestore();
  });

  it('unknown backend names warn and fall back to FILE (manager.py:215-216)', () => {
    const warn = jest.spyOn(Logger, 'warn').mockResolvedValue();
    new LearnManager({ backend: 'bogus', thread: false, insights: false }, 'u', path.join(tmpRoot, 'bogus'));
    expect(warn).toHaveBeenCalledWith(expect.stringMatching(/Unknown learn backend 'bogus'/));
    warn.mockRestore();
  });
});

describe('sqlite backend', () => {
  // Probe by actually opening a database: `require` alone can succeed while the
  // native binding fails to load (e.g. built against a different Node ABI), in
  // which case LearnManager falls back to the FILE backend by design.
  let available = true;
  try {
    const Database = require('better-sqlite3');
    new Database(':memory:').close();
  } catch {
    available = false;
  }
  const maybe = available ? it : it.skip;

  maybe('stores entries in a learn_store table and reads them back in a new manager', () => {
    const dir = path.join(tmpRoot, 'sq');
    const dbUrl = `sqlite:///${path.join(dir, 'learn.db')}`;
    const first = new LearnManager({ backend: 'sqlite', dbUrl, thread: false, insights: false }, 'u', dir);
    first.capturePersona('lives in sqlite');
    expect(fs.existsSync(path.join(dir, 'learn.db'))).toBe(true);
    // No JSON file is written when a backend is active
    expect(fs.existsSync(path.join(dir, 'persona.json'))).toBe(false);

    const second = new LearnManager({ backend: 'sqlite', dbUrl, thread: false, insights: false }, 'u', dir);
    expect(second.getPersonaContext()).toEqual(['lives in sqlite']);

    const backend = new SQLiteLearnBackend(path.join(dir, 'learn.db'), 'learn_store');
    expect(backend.listKeys()).toEqual(['persona']);
    expect(backend.exists('persona')).toBe(true);
    expect(backend.delete('persona')).toBe(true);
    expect(backend.load('persona')).toBeNull();
    backend.close();
  });

  it('rejects unsafe table names (backends.py:191-192)', () => {
    expect(() => new SQLiteLearnBackend(path.join(tmpRoot, 'x.db'), 'bad name')).toThrow(/tableName/);
  });
});

describe('LearnManager surface', () => {
  it('applies the Python LearnConfig defaults (feature_configs.py:169-199)', () => {
    expect(resolveLearnConfig()).toEqual({
      persona: true,
      insights: true,
      thread: true,
      patterns: false,
      decisions: false,
      feedback: false,
      improvements: false,
      nudgeInterval: 0,
      nudgeMinToolIters: 3,
      proposeSkills: false,
      mode: 'disabled',
      scope: 'private',
      backend: 'file',
      dbUrl: null,
      storePath: null,
      maxEntries: 0,
      retentionDays: 0,
      llm: null,
      autoConsolidate: false,
    });
  });

  it('capture methods return null for disabled stores and route to the right store otherwise', () => {
    const m = new LearnManager(
      { persona: true, insights: true, thread: true, patterns: true, decisions: true, feedback: true, improvements: true },
      'u',
      path.join(tmpRoot, 'all'),
    );
    expect(m.capturePersona('p')?.metadata).toEqual({ category: 'general', type: 'preference' });
    expect(m.captureInsight('i')?.metadata).toEqual({ source: 'interaction', type: 'insight' });
    expect(m.captureThread('t', 'th-1')?.metadata).toEqual({ thread_id: 'th-1', type: 'summary' });
    expect(m.capturePattern('pt')?.metadata).toEqual({ pattern_type: 'general', type: 'pattern' });
    expect(m.captureDecision('d')?.metadata).toEqual({ reasoning: '', outcome: '', type: 'decision' });
    expect(m.captureFeedback('f', 5)?.metadata).toEqual({ source: 'user', type: 'feedback', rating: 5 });
    expect(m.captureFeedback('f2')?.metadata).toEqual({ source: 'user', type: 'feedback' });
    expect(m.captureImprovement('imp')?.metadata).toEqual({ area: 'general', priority: 'medium', type: 'improvement' });

    const off = new LearnManager({ persona: false, insights: false, thread: false }, 'u', path.join(tmpRoot, 'off'));
    expect(off.capturePersona('x')).toBeNull();
    expect(off.captureInsight('x')).toBeNull();
    expect(off.captureThread('x', 't')).toBeNull();
    expect(off.getStats()).toEqual({});
    expect(off.toSystemPromptContext()).toBe('');
  });

  it('toSystemPromptContext mirrors the Python section layout and excludes threads', () => {
    const m = new LearnManager({ patterns: true }, 'u', path.join(tmpRoot, 'ctx'));
    m.capturePersona('Likes tea');
    m.captureInsight('Works nights');
    m.capturePattern('Asks for lists');
    m.captureThread('thread summary', 't1');
    expect(m.toSystemPromptContext()).toBe(
      'User Preferences:\n- Likes tea\n\nLearned Insights:\n- Works nights\n\nKnown Patterns:\n- Asks for lists',
    );
  });

  it('custom stores override built-ins and appear in context/search/clearAll', () => {
    const calls: string[] = [];
    const custom = {
      add: (content: string) => {
        calls.push(`add:${content}`);
        return { id: 'c1', content, metadata: {}, created_at: '', updated_at: '', use_count: 0, last_used: null };
      },
      search: (q: string) => (q === 'hit' ? [{ id: 'c1', content: 'hit', metadata: {}, created_at: '', updated_at: '', use_count: 0, last_used: null }] : []),
      listAll: () => [{ id: 'c1', content: 'custom', metadata: {}, created_at: '', updated_at: '', use_count: 0, last_used: null }],
      get: () => null,
      update: () => null,
      delete: () => false,
      clear: () => 7,
    };
    const m = new LearnManager({ thread: false, insights: false }, 'u', path.join(tmpRoot, 'custom'), { persona: custom, domain: custom });
    expect(Array.from(m.stores.keys())).toEqual(['persona', 'domain']);
    // built-in persona was replaced, so capturePersona has nothing to route to
    expect(m.capturePersona('x')).toBeNull();
    expect(m.getLearningContext().domain[0].content).toBe('custom');
    expect(Object.keys(m.search('hit'))).toEqual(['persona', 'domain']);
    expect(m.search('miss')).toEqual({});
    expect(m.clearAll()).toEqual({ persona: 7, domain: 7 });
    expect(m.getStats()).toEqual({ persona: 0, domain: 0 });
    m.addPending('queued', 'domain');
    expect(m.approveAllLearnings()).toBe(1);
    expect(calls).toEqual(['add:queued']);
  });

  it('prune reports per-store counts and honours retention settings', () => {
    const m = new LearnManager({ thread: false, insights: false, maxEntries: 1 }, 'u', path.join(tmpRoot, 'prune'));
    m.capturePersona('a');
    m.capturePersona('b');
    expect(m.getStats()).toEqual({ persona: 1 });
    expect(m.prune()).toEqual({ persona: 0 });
    const feedback = new FeedbackStore({ storePath: path.join(tmpRoot, 'fb.json'), retentionDays: 1 });
    const old = feedback.add('stale');
    old.lastUsed = new Date(Date.now() - 3 * 86_400_000).toISOString();
    expect(feedback.prune()).toBe(1);
    expect(feedback.entryCount).toBe(0);
  });
});
