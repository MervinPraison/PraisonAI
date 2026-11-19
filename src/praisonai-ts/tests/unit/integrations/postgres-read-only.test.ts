/**
 * NLPostgresClient: read-only mode and table lists are enforced by PostgreSQL,
 * not by reading the SQL text.
 *
 * The unit tests drive a fake pg pool and check the protocol the client speaks:
 * each statement runs alone on its own connection, inside BEGIN READ ONLY, as a
 * named prepared statement (extended protocol: PostgreSQL refuses a second
 * statement), and the table lists are checked against the relations the
 * transaction locked. The live block runs the reported payloads against a real
 * server when PRAISONAI_TEST_PG_URL is set.
 */
import * as fs from 'fs';
import * as path from 'path';
import { NLPostgresClient } from '../../../src/integrations/postgres';

type Sent = string | { name?: string; text: string };

function fakeClient(config: any, lockedTables: Array<{ schema: string; name: string }> = []) {
  const sent: Sent[] = [];
  const released: any[] = [];
  const conn = {
    query: async (q: Sent) => {
      sent.push(q);
      const text = typeof q === 'string' ? q : q.text;
      if (text.includes('pg_locks')) return { rows: lockedTables, rowCount: lockedTables.length };
      return { rows: [{ ok: 1 }], rowCount: 1, fields: [] };
    },
    release: (arg?: any) => released.push(arg),
  };
  const client = new NLPostgresClient({ connectionUrl: 'postgres://x', ...config });
  (client as any).connected = true;
  (client as any).pool = {
    connect: async () => conn,
    query: async (q: Sent) => { sent.push(q); return { rows: [], rowCount: 0, fields: [] }; },
  };
  return { client, sent, released };
}

const texts = (sent: Sent[]) => sent.map(q => (typeof q === 'string' ? q : q.text));

describe('NLPostgresClient read-only mode is enforced by the database', () => {
  const payloads = [
    '/*x*/ DROP TABLE users; SELECT 1 LIMIT 1',
    'SELECT 1; DROP TABLE users;',
    'WITH gone AS (DELETE FROM users RETURNING *) SELECT 1 LIMIT 1',
  ];

  it.each(payloads)('runs %s inside BEGIN READ ONLY as one named statement', async (sql) => {
    const { client, sent } = fakeClient({});
    await client.executeSQL(sql);
    expect(texts(sent)[0]).toBe('BEGIN READ ONLY');
    const stmt = sent[1] as { name?: string; text: string };
    expect(typeof stmt).toBe('object');
    expect(stmt.name).toMatch(/^praisonai_nlq_\d+$/);
    expect(texts(sent)[sent.length - 1]).toBe('ROLLBACK');
    // The raw SQL never goes through the simple-query protocol.
    expect(sent.filter(q => typeof q === 'string' && q.includes('users'))).toHaveLength(0);
  });

  it('gives every statement its own prepared-statement name', async () => {
    const { client, sent } = fakeClient({});
    await client.executeSQL('SELECT 1');
    await client.executeSQL('SELECT 2');
    const names = sent.filter(q => typeof q === 'object').map(q => (q as any).name);
    expect(new Set(names).size).toBe(2);
  });

  it('commits only when readOnly is false', async () => {
    const { client, sent } = fakeClient({ readOnly: false });
    await client.executeSQL('UPDATE t SET a = 1');
    expect(texts(sent)[0]).toBe('BEGIN');
    expect(texts(sent)[sent.length - 1]).toBe('COMMIT');
  });

  it('rolls back and releases the connection when the statement fails', async () => {
    const { client, sent, released } = fakeClient({});
    const pool = (client as any).pool;
    const conn = await pool.connect();
    const original = conn.query;
    conn.query = async (q: Sent) => {
      if (typeof q === 'object') { sent.push(q); throw new Error('cannot insert multiple commands into a prepared statement'); }
      return original(q);
    };
    pool.connect = async () => conn;
    await expect(client.executeSQL('SELECT 1; DROP TABLE users')).rejects.toThrow('multiple commands');
    expect(texts(sent)).toContain('ROLLBACK');
    expect(released).toHaveLength(1);
  });
});

describe('NLPostgresClient table lists are enforced on execution', () => {
  it('rejects a blocked table and returns no rows', async () => {
    const { client, sent } = fakeClient({ blockedTables: ['secret'] }, [{ schema: 'public', name: 'secret' }]);
    await expect(client.executeSQL('SELECT secret FROM secret LIMIT 1')).rejects.toThrow("Table 'secret' is not allowed");
    expect(texts(sent)).toContain('ROLLBACK');
  });

  it('rejects a table outside allowedTables, including other schemas', async () => {
    const { client } = fakeClient({ allowedTables: ['safe'] }, [{ schema: 'public', name: 'safe' }, { schema: 'hr', name: 'safe' }]);
    await expect(client.executeSQL('SELECT 1')).rejects.toThrow("Table 'hr.safe' is not allowed");
  });

  it('allows a statement that only touches allowed tables', async () => {
    const { client } = fakeClient({ allowedTables: ['safe'], blockedTables: ['secret'] }, [{ schema: 'public', name: 'safe' }]);
    await expect(client.executeSQL('SELECT * FROM safe')).resolves.toMatchObject({ rowCount: 1 });
  });

  it('skips the lock lookup when no table list is set', async () => {
    const { client, sent } = fakeClient({});
    await client.executeSQL('SELECT 1');
    expect(texts(sent).some(t => t.includes('pg_locks'))).toBe(false);
  });
});

describe('guard: model and caller SQL reaches PostgreSQL only through executeSQL', () => {
  const source = fs.readFileSync(path.join(__dirname, '../../../src/integrations/postgres.ts'), 'utf8');

  it('sends only fixed SQL through pool.query', () => {
    // connect() probe and loadSchema() catalog query; nothing else.
    const calls = source.match(/this\.pool\.query\([^,)]*/g) || [];
    expect(calls).toEqual(["this.pool.query('SELECT 1'", 'this.pool.query(schemaQuery']);
  });

  it('routes every SQL-running entry point through executeSQL', () => {
    // query(), the chat() tool and inspect() (createPostgresTool calls query()).
    expect((source.match(/this\.executeSQL\(/g) || []).length).toBe(3);
    expect(source).toMatch(/const result = await client\.query\(query\)/);
  });
});

const liveUrl = process.env.PRAISONAI_TEST_PG_URL;
(liveUrl ? describe : describe.skip)('live PostgreSQL', () => {
  let client: NLPostgresClient;
  let admin: any;

  beforeAll(async () => {
    // @ts-ignore - optional dependency
    const { Pool } = await import('pg');
    admin = new Pool({ connectionString: liveUrl });
    await admin.query('DROP TABLE IF EXISTS vj_users, vj_secret, vj_safe');
    await admin.query("CREATE TABLE vj_users(id int); INSERT INTO vj_users VALUES (1)");
    await admin.query("CREATE TABLE vj_secret(s text); INSERT INTO vj_secret VALUES ('TOP')");
    await admin.query('CREATE TABLE vj_safe(id int); INSERT INTO vj_safe VALUES (1)');
    client = new NLPostgresClient({ connectionUrl: liveUrl!, blockedTables: ['vj_secret'] });
    await client.connect();
  });

  afterAll(async () => {
    await client?.disconnect();
    await admin?.query('DROP TABLE IF EXISTS vj_users, vj_secret, vj_safe');
    await admin?.end();
  });

  it.each([
    '/*x*/ DROP TABLE vj_users; SELECT 1 LIMIT 1',
    'SELECT 1; DROP TABLE vj_users;',
    'SELECT 1; COMMIT; DROP TABLE vj_users',
    'WITH gone AS (DELETE FROM vj_users RETURNING *) SELECT 1 LIMIT 1',
    "DO $$BEGIN EXECUTE 'DROP TABLE vj_users'; END$$",
  ])('refuses %s and leaves the table intact', async (sql) => {
    await expect(client.executeSQL(sql)).rejects.toThrow();
    const r = await admin.query('SELECT count(*)::int AS n FROM vj_users');
    expect(r.rows[0].n).toBe(1);
  });

  it.each([
    'SELECT * FROM vj_secret',
    "SELECT * FROM vj_secret WHERE ctid = '(0,1)'",
    "SELECT query_to_xml('select * from vj_secret', true, true, '')",
  ])('refuses blocked-table read %s', async (sql) => {
    await expect(client.executeSQL(sql)).rejects.toThrow("Table 'vj_secret' is not allowed");
  });

  it('still answers an ordinary read', async () => {
    await expect(client.executeSQL('SELECT * FROM vj_safe;')).resolves.toMatchObject({ rowCount: 1 });
  });
});
