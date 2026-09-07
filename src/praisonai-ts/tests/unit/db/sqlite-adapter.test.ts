/**
 * Does `db("sqlite:./data.db")` actually persist?
 *
 * The whole point of this suite is the process boundary: every durability
 * assertion reads back through a SECOND adapter instance opened on the same
 * file, never through the instance that did the writing. An adapter that had
 * quietly degraded to in-process Maps would pass a single-instance test and
 * fail every one of these.
 *
 * If no SQLite driver can be loaded the durability tests are SKIPPED, and the
 * skip is made impossible to read as a pass: the suite name says so, a banner
 * naming the driver failure is printed, and `PRAISONAI_REQUIRE_SQLITE=1` turns
 * the skip into a hard failure for CI.
 */

import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import { db } from '../../../src/db';
import { MemoryDbAdapter } from '../../../src/db/memory-adapter';
import {
  SqliteDbAdapter,
  createSqliteDbAdapter,
  SQLITE_SCHEMA_VERSION,
} from '../../../src/db/sqlite-adapter';
import type { DbMessage, DbRun, DbSession } from '../../../src/db/types';

// ---------------------------------------------------------------------------
// Driver probe -- decides whether the durability tests can run at all
// ---------------------------------------------------------------------------

interface Probe {
  available: boolean;
  driver?: 'better-sqlite3' | 'node:sqlite';
  failures: string[];
}

function firstLines(error: unknown): string {
  return error instanceof Error
    ? error.message.split('\n').slice(0, 2).join(' ')
    : String(error);
}

function probeDrivers(): Probe {
  const failures: string[] = [];
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const Database = require('better-sqlite3');
    // The ABI mismatch surfaces here, not at require().
    new Database(':memory:').close();
    return { available: true, driver: 'better-sqlite3', failures };
  } catch (error) {
    failures.push(`better-sqlite3: ${firstLines(error)}`);
  }
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { DatabaseSync } = require('node:sqlite');
    new DatabaseSync(':memory:').close();
    return { available: true, driver: 'node:sqlite', failures };
  } catch (error) {
    failures.push(`node:sqlite: ${firstLines(error)}`);
  }
  return { available: false, failures };
}

const probe = probeDrivers();

if (!probe.available) {
  const banner =
    '\n' +
    '='.repeat(78) +
    '\nSQLITE DURABILITY TESTS SKIPPED -- THIS IS NOT A PASS.\n' +
    'No SQLite driver could open a database on this machine:\n' +
    probe.failures.map((f) => `  - ${f}`).join('\n') +
    '\nA NODE_MODULE_VERSION / ERR_DLOPEN_FAILED message above means the\n' +
    "better-sqlite3 native binding was built for a different Node ABI:\n" +
    'run `npm rebuild better-sqlite3` under the Node version in use, or run\n' +
    'Node >= 22.5 so the built-in node:sqlite can take over.\n' +
    'Set PRAISONAI_REQUIRE_SQLITE=1 to make this a hard failure instead.\n' +
    '='.repeat(78) +
    '\n';
  // eslint-disable-next-line no-console
  console.warn(banner);
  if (process.env.PRAISONAI_REQUIRE_SQLITE === '1') {
    throw new Error(
      `PRAISONAI_REQUIRE_SQLITE=1 but no SQLite driver is usable: ${probe.failures.join(' | ')}`,
    );
  }
}

const describeSqlite = probe.available ? describe : describe.skip;
const sqliteSuiteName = probe.available
  ? `SqliteDbAdapter durability (driver: ${probe.driver})`
  : 'SqliteDbAdapter durability -- SKIPPED, NOT PASSED (no usable SQLite driver)';

/** Open the file directly, bypassing the adapter, to inspect the real schema. */
function openRaw(file: string): { all(sql: string): any[]; close(): void } {
  if (probe.driver === 'better-sqlite3') {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const Database = require('better-sqlite3');
    const handle = new Database(file);
    return { all: (sql: string) => handle.prepare(sql).all(), close: () => handle.close() };
  }
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { DatabaseSync } = require('node:sqlite');
  const handle = new DatabaseSync(file);
  return { all: (sql: string) => handle.prepare(sql).all(), close: () => handle.close() };
}

function execRaw(file: string, sql: string): void {
  if (probe.driver === 'better-sqlite3') {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const Database = require('better-sqlite3');
    const handle = new Database(file);
    handle.exec(sql);
    handle.close();
    return;
  }
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { DatabaseSync } = require('node:sqlite');
  const handle = new DatabaseSync(file);
  handle.exec(sql);
  handle.close();
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

let tmpDir: string;
let fileCounter = 0;

function tmpFile(name = 'data'): string {
  fileCounter += 1;
  return path.join(tmpDir, `${name}-${fileCounter}.db`);
}

function message(overrides: Partial<DbMessage> & Pick<DbMessage, 'id' | 'sessionId'>): DbMessage {
  return {
    role: 'user',
    content: 'hello',
    createdAt: Date.now(),
    ...overrides,
  } as DbMessage;
}

beforeAll(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'praisonai-sqlite-db-'));
});

afterAll(() => {
  if (tmpDir) fs.rmSync(tmpDir, { recursive: true, force: true });
});

// ---------------------------------------------------------------------------
// The real thing
// ---------------------------------------------------------------------------

describeSqlite(sqliteSuiteName, () => {
  it('a session and its messages survive into a NEW adapter on the same file', async () => {
    const file = tmpFile('roundtrip');
    const sessionId = 'session-round-trip';

    const writer = new SqliteDbAdapter({ filename: file });
    await writer.connect();
    const session: DbSession = {
      id: sessionId,
      createdAt: 1_700_000_000_000,
      updatedAt: 1_700_000_000_000,
      metadata: { user: 'ada', tags: ['a', 'b'] },
    };
    await writer.createSession(session);
    await writer.saveMessage(
      message({ id: 'm1', sessionId, role: 'system', content: 'You are helpful', createdAt: 1 }),
    );
    await writer.saveMessage(
      message({ id: 'm2', sessionId, role: 'user', content: 'Hello!', createdAt: 2 }),
    );
    await writer.saveMessage(
      message({
        id: 'm3',
        sessionId,
        role: 'assistant',
        content: 'Hi there',
        createdAt: 3,
        runId: 'run-1',
        metadata: { finish: 'stop' },
      }),
    );
    await writer.disconnect();

    // Everything below reads through a different instance. Nothing is shared
    // in process; if the file were not real, this would come back empty.
    const reader = new SqliteDbAdapter({ filename: file });
    const restoredSession = await reader.getSession(sessionId);
    expect(restoredSession).toEqual(session);

    const messages = await reader.getMessages(sessionId);
    expect(messages.map((m) => [m.role, m.content])).toEqual([
      ['system', 'You are helpful'],
      ['user', 'Hello!'],
      ['assistant', 'Hi there'],
    ]);
    expect(messages[2].runId).toBe('run-1');
    expect(messages[2].metadata).toEqual({ finish: 'stop' });
    // Fields that were never set come back undefined, not null.
    expect(messages[0].runId).toBeUndefined();
    expect(messages[0].metadata).toBeUndefined();
    await reader.disconnect();
  });

  it('records a run, updates it, and lists it back from a new instance', async () => {
    const file = tmpFile('runs');
    const sessionId = 'session-runs';

    const writer = new SqliteDbAdapter({ filename: file });
    const run: DbRun = {
      id: 'run-a',
      sessionId,
      agentName: 'researcher',
      status: 'running',
      startedAt: 10,
    };
    await writer.createRun(run);
    await writer.createRun({ id: 'run-b', sessionId, status: 'pending', startedAt: 20 });
    await writer.createRun({ id: 'other', sessionId: 'elsewhere', status: 'pending', startedAt: 30 });
    await writer.updateRun('run-a', {
      status: 'completed',
      completedAt: 15,
      tokenUsage: { promptTokens: 11, completionTokens: 22, totalTokens: 33 },
      metadata: { model: 'gpt-4o-mini' },
    });
    await writer.saveToolCall({
      id: 'tc-1',
      runId: 'run-a',
      name: 'get_weather',
      arguments: '{"city":"Paris"}',
      result: '20C',
      status: 'completed',
      startedAt: 11,
      completedAt: 12,
    });
    await writer.disconnect();

    const reader = new SqliteDbAdapter({ filename: file });
    const runs = await reader.listRuns(sessionId);
    expect(runs.map((r) => r.id)).toEqual(['run-a', 'run-b']); // other session excluded
    const reloaded = await reader.getRun('run-a');
    expect(reloaded).toEqual({
      id: 'run-a',
      sessionId,
      agentName: 'researcher',
      status: 'completed',
      startedAt: 10,
      completedAt: 15,
      error: undefined,
      metadata: { model: 'gpt-4o-mini' },
      tokenUsage: { promptTokens: 11, completionTokens: 22, totalTokens: 33 },
    });

    const toolCalls = await reader.getToolCalls('run-a');
    expect(toolCalls).toHaveLength(1);
    expect(toolCalls[0].name).toBe('get_weather');
    expect(toolCalls[0].result).toBe('20C');
    await reader.disconnect();
  });

  it('persists traces and spans across instances', async () => {
    const file = tmpFile('traces');
    const writer = new SqliteDbAdapter({ filename: file });
    await writer.createTrace({
      id: 'trace-1',
      sessionId: 'session-trace',
      runId: 'run-1',
      status: 'running',
      startedAt: 5,
    });
    await writer.createSpan({
      id: 'span-1',
      traceId: 'trace-1',
      name: 'llm.call',
      status: 'running',
      startedAt: 6,
      attributes: { model: 'gpt-4o-mini' },
    });
    await writer.updateSpan('span-1', { status: 'completed', completedAt: 7 });
    await writer.updateTrace('trace-1', { status: 'completed', completedAt: 8 });
    await writer.disconnect();

    const reader = new SqliteDbAdapter({ filename: file });
    const trace = await reader.getTrace('trace-1');
    expect(trace?.status).toBe('completed');
    expect(trace?.completedAt).toBe(8);
    const spans = await reader.getSpans('trace-1');
    expect(spans).toHaveLength(1);
    expect(spans[0].status).toBe('completed');
    expect(spans[0].attributes).toEqual({ model: 'gpt-4o-mini' });
    await reader.disconnect();
  });

  it('getMessages(limit) returns the LAST n in chronological order, like MemoryDbAdapter', async () => {
    const file = tmpFile('limit');
    const sessionId = 's';
    const sqlite = new SqliteDbAdapter({ filename: file });
    const memory = new MemoryDbAdapter();
    for (let i = 1; i <= 5; i += 1) {
      const m = message({ id: `m${i}`, sessionId, content: `msg-${i}`, createdAt: i });
      await sqlite.saveMessage(m);
      await memory.saveMessage(m);
    }
    const fromSqlite = (await sqlite.getMessages(sessionId, 2)).map((m) => m.content);
    const fromMemory = (await memory.getMessages(sessionId, 2)).map((m) => m.content);
    expect(fromSqlite).toEqual(['msg-4', 'msg-5']);
    expect(fromSqlite).toEqual(fromMemory);
    await sqlite.disconnect();
  });

  it('orders messages written in the same millisecond by insertion, not at random', async () => {
    const file = tmpFile('sameclock');
    const sessionId = 's';
    const adapter = new SqliteDbAdapter({ filename: file });
    const stamp = 1_700_000_000_000;
    for (const id of ['a', 'b', 'c', 'd']) {
      await adapter.saveMessage(message({ id, sessionId, content: id, createdAt: stamp }));
    }
    await adapter.disconnect();

    const reader = new SqliteDbAdapter({ filename: file });
    expect((await reader.getMessages(sessionId)).map((m) => m.content)).toEqual([
      'a',
      'b',
      'c',
      'd',
    ]);
    expect((await reader.getMessages(sessionId, 2)).map((m) => m.content)).toEqual(['c', 'd']);
    await reader.disconnect();
  });

  it('deletes messages and sessions durably', async () => {
    const file = tmpFile('delete');
    const writer = new SqliteDbAdapter({ filename: file });
    await writer.createSession({ id: 's1', createdAt: 1, updatedAt: 1 });
    await writer.createSession({ id: 's2', createdAt: 2, updatedAt: 2 });
    await writer.saveMessage(message({ id: 'm1', sessionId: 's1', createdAt: 1 }));
    await writer.saveMessage(message({ id: 'm2', sessionId: 's2', createdAt: 2 }));
    await writer.deleteMessages('s1');
    await writer.deleteSession('s2');
    await writer.disconnect();

    const reader = new SqliteDbAdapter({ filename: file });
    expect(await reader.getMessages('s1')).toEqual([]);
    expect(await reader.getSession('s1')).not.toBeNull();
    expect(await reader.getSession('s2')).toBeNull();
    expect(await reader.getMessages('s2')).toEqual([]);
    expect((await reader.listSessions()).map((s) => s.id)).toEqual(['s1']);
    await reader.disconnect();
  });

  it('updateSession stamps updatedAt and keeps createdAt, as MemoryDbAdapter does', async () => {
    const file = tmpFile('update-session');
    const adapter = new SqliteDbAdapter({ filename: file });
    await adapter.createSession({ id: 's', createdAt: 100, updatedAt: 100 });
    await adapter.updateSession('s', { metadata: { title: 'renamed' } });
    const session = await adapter.getSession('s');
    expect(session?.createdAt).toBe(100);
    expect(session?.metadata).toEqual({ title: 'renamed' });
    expect(session!.updatedAt).toBeGreaterThan(100);
    await adapter.disconnect();
  });

  it('writes the documented schema to the file', async () => {
    const file = tmpFile('schema');
    const adapter = new SqliteDbAdapter({ filename: file });
    await adapter.connect();
    expect(await adapter.getSchemaVersion()).toBe(SQLITE_SCHEMA_VERSION);
    await adapter.disconnect();

    const raw = openRaw(file);
    try {
      const tables = raw
        .all("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")
        .map((r: any) => String(r.name))
        .sort();
      expect(tables).toEqual([
        'messages',
        'praisonai_meta',
        'runs',
        'sessions',
        'spans',
        'tool_calls',
        'traces',
      ]);

      const columns = (table: string) =>
        raw.all(`PRAGMA table_info(${table})`).map((r: any) => String(r.name));
      expect(columns('sessions')).toEqual(['id', 'created_at', 'updated_at', 'metadata']);
      expect(columns('messages')).toEqual([
        'id',
        'session_id',
        'run_id',
        'role',
        'content',
        'name',
        'tool_call_id',
        'tool_calls',
        'created_at',
        'metadata',
      ]);
      expect(columns('runs')).toEqual([
        'id',
        'session_id',
        'agent_name',
        'status',
        'started_at',
        'completed_at',
        'error',
        'metadata',
        'prompt_tokens',
        'completion_tokens',
        'total_tokens',
      ]);
      expect(columns('tool_calls')).toEqual([
        'id',
        'run_id',
        'name',
        'arguments',
        'result',
        'status',
        'started_at',
        'completed_at',
        'error',
      ]);
      expect(columns('traces')).toEqual([
        'id',
        'session_id',
        'run_id',
        'agent_name',
        'started_at',
        'completed_at',
        'status',
        'metadata',
      ]);
      expect(columns('spans')).toEqual([
        'id',
        'trace_id',
        'parent_id',
        'name',
        'started_at',
        'completed_at',
        'status',
        'attributes',
      ]);
    } finally {
      raw.close();
    }
  });

  it('diagnoses a file whose tables were written with an incompatible shape', async () => {
    const file = tmpFile('legacy');
    // The shape the low-level SQLiteAdapter in src/db/sqlite.ts writes: `runs`
    // has agent_id, not agent_name. CREATE TABLE IF NOT EXISTS would leave it
    // alone and the first INSERT would explode inside the driver.
    execRaw(
      file,
      'CREATE TABLE runs (id TEXT PRIMARY KEY, session_id TEXT, agent_id TEXT, status TEXT, ' +
        'input TEXT, output TEXT, error TEXT, started_at INTEGER, completed_at INTEGER, metadata TEXT);',
    );
    const adapter = new SqliteDbAdapter({ filename: file });
    await expect(adapter.connect()).rejects.toThrow(/incompatible shape.*agent_name/s);
    expect(adapter.isConnected()).toBe(false);
  });

  it('diagnoses a partial schema missing a column only an INSERT touches', async () => {
    const file = tmpFile('partial');
    // A `spans` table with the NOT NULL core but no `attributes` column. The
    // core-only check used to pass this file, then the first saveSpan() would
    // fail deep in the driver on "table spans has no column named attributes".
    // The full-column check must catch it at open().
    execRaw(
      file,
      'CREATE TABLE spans (id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, ' +
        'parent_id TEXT, name TEXT NOT NULL, started_at INTEGER NOT NULL, ' +
        'completed_at INTEGER, status TEXT NOT NULL);',
    );
    const adapter = new SqliteDbAdapter({ filename: file });
    await expect(adapter.connect()).rejects.toThrow(/incompatible shape.*attributes/s);
    expect(adapter.isConnected()).toBe(false);
  });

  it('db("sqlite:<file>") is the durable adapter, end to end', async () => {
    const file = tmpFile('factory');
    const writing = db(`sqlite:${file}`);
    expect(writing).toBeInstanceOf(SqliteDbAdapter);
    await writing.saveMessage(message({ id: 'm1', sessionId: 'via-factory', content: 'kept' }));
    await writing.disconnect();

    const reading = db(`sqlite:${file}`);
    const messages = await reading.getMessages('via-factory');
    expect(messages.map((m) => m.content)).toEqual(['kept']);
    await reading.disconnect();
  });

  it('sqlite ":memory:" is real SQLite but, like memory:, is process-local', async () => {
    const a = createSqliteDbAdapter(':memory:');
    await a.saveMessage(message({ id: 'm1', sessionId: 's', content: 'ephemeral' }));
    expect((await a.getMessages('s')).map((m) => m.content)).toEqual(['ephemeral']);

    const b = createSqliteDbAdapter(':memory:');
    expect(await b.getMessages('s')).toEqual([]);
    await a.disconnect();
    await b.disconnect();
  });
});

// ---------------------------------------------------------------------------
// Controls -- these run on every machine, driver or not
// ---------------------------------------------------------------------------

describe('db() controls', () => {
  it('db("memory:") still works and is NOT persistent across instances', async () => {
    const first = db('memory:');
    expect(first).toBeInstanceOf(MemoryDbAdapter);
    await first.createSession({ id: 's', createdAt: 1, updatedAt: 1 });
    await first.saveMessage(message({ id: 'm1', sessionId: 's', content: 'gone soon' }));
    expect((await first.getMessages('s')).map((m) => m.content)).toEqual(['gone soon']);

    // A second adapter is a second set of Maps: nothing crosses between them,
    // which is exactly why sqlite had to exist.
    const second = db('memory:');
    expect(await second.getSession('s')).toBeNull();
    expect(await second.getMessages('s')).toEqual([]);
  });

  it('postgres:// and redis:// still throw, naming what to use instead', () => {
    expect(() => db('postgres://user:pass@localhost:5432/app')).toThrow(
      /not yet wired to the DbAdapter contract/,
    );
    expect(() => db('postgres://user:pass@localhost:5432/app')).toThrow(/db\("sqlite:\.\/data\.db"\)/);
    expect(() => db('redis://localhost:6379')).toThrow(/not yet wired to the DbAdapter contract/);
  });

  it('an unusable driver produces a clear error and NEVER a silent memory fallback', async () => {
    const file = path.join(tmpDir, 'never-created.db');
    const adapter = new SqliteDbAdapter({
      filename: file,
      // Exactly what better-sqlite3 throws when its prebuilt binding was
      // compiled against a different Node ABI.
      driverLoader: async () => {
        throw new Error(
          "The module '/x/better_sqlite3.node' was compiled against a different Node.js " +
            'version using NODE_MODULE_VERSION 141. This version of Node.js requires ' +
            'NODE_MODULE_VERSION 127. (ERR_DLOPEN_FAILED)',
        );
      },
    });

    await expect(adapter.connect()).rejects.toThrow(/NODE_MODULE_VERSION/);
    await expect(adapter.connect()).rejects.toThrow(/npm rebuild better-sqlite3/);

    // A write must FAIL, not appear to succeed against memory...
    await expect(
      adapter.saveMessage(message({ id: 'm1', sessionId: 's', content: 'must not vanish' })),
    ).rejects.toThrow(/SQLite persistence is unavailable/);
    // ...and a read must FAIL rather than return a confident empty list.
    await expect(adapter.getMessages('s')).rejects.toThrow(/SQLite persistence is unavailable/);

    expect(adapter.isConnected()).toBe(false);
    expect(fs.existsSync(file)).toBe(false);
  });

  it('better-sqlite3, pinned, either works or explains how to fix its native binding', async () => {
    const file = path.join(tmpDir, 'pinned-better.db');
    const adapter = new SqliteDbAdapter({ filename: file, driver: 'better-sqlite3' });
    let failure: Error | null = null;
    try {
      await adapter.connect();
    } catch (error) {
      failure = error as Error;
    }

    if (failure) {
      // This is the state of this checkout today: the prebuilt binding does not
      // match the running Node ABI. The contract is that the message says so
      // and says what to do, instead of the adapter pretending to persist.
      expect(failure.message).toMatch(/better-sqlite3/);
      expect(failure.message).toMatch(/npm rebuild better-sqlite3|Install the driver/);
      expect(failure.message).toMatch(/does not survive the process/);
      expect(adapter.isConnected()).toBe(false);
    } else {
      expect(adapter.getDriverName()).toBe('better-sqlite3');
      await adapter.saveMessage(message({ id: 'm1', sessionId: 's', content: 'ok' }));
      expect((await adapter.getMessages('s')).map((m) => m.content)).toEqual(['ok']);
    }
    await adapter.disconnect();
  });
});
