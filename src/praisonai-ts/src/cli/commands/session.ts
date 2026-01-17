/**
 * Session command - Manage agent sessions with optional persistence
 */

import { Session, SessionManager, getSessionManager } from '../../session';
import { db } from '../../db';
import { ENV_VARS } from '../spec/cli-spec';
import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface SessionOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
  db?: string;
}

// Get database URL from option or env var
function getDbUrl(options: SessionOptions): string | undefined {
  return options.db || process.env[ENV_VARS.PRAISONAI_DB];
}

// Persistent session manager using db adapter
class PersistentSessionManager {
  private adapter: any;
  private sessions: Map<string, any> = new Map();

  constructor(dbUrl: string) {
    this.adapter = db(dbUrl);
  }

  async initialize(): Promise<void> {
    if (this.adapter.initialize) {
      await this.adapter.initialize();
    }
  }

  async create(options?: { id?: string }): Promise<any> {
    await this.initialize();
    const id = options?.id || `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const now = Date.now();

    if (this.adapter.createSession) {
      await this.adapter.createSession(id, { createdAt: now });
    }

    const session = { id, messages: [], createdAt: now };
    this.sessions.set(id, session);
    return session;
  }

  async list(): Promise<any[]> {
    await this.initialize();
    // For SQLite, we need to query sessions table
    if (this.adapter.db?.prepare) {
      try {
        const stmt = this.adapter.db.prepare('SELECT * FROM sessions ORDER BY created_at DESC');
        const rows = stmt.all();
        return rows.map((row: any) => ({
          id: row.id,
          messages: [],
          createdAt: row.created_at
        }));
      } catch (e) {
        return [];
      }
    }
    return Array.from(this.sessions.values());
  }

  async get(id: string): Promise<any | null> {
    await this.initialize();
    if (this.adapter.getSession) {
      const session = await this.adapter.getSession(id);
      if (session) {
        // Get messages for this session
        let messages: any[] = [];
        if (this.adapter.getMessages) {
          messages = await this.adapter.getMessages(id);
        }
        return { ...session, messages };
      }
    }
    return this.sessions.get(id) || null;
  }

  async delete(id: string): Promise<boolean> {
    await this.initialize();
    // SQLite delete
    if (this.adapter.db?.prepare) {
      try {
        this.adapter.db.prepare('DELETE FROM sessions WHERE id = ?').run(id);
        this.adapter.db.prepare('DELETE FROM messages WHERE session_id = ?').run(id);
        return true;
      } catch (e) {
        return false;
      }
    }
    return this.sessions.delete(id);
  }
}

export async function execute(args: string[], options: SessionOptions): Promise<void> {
  const action = args[0] || 'list';
  const actionArgs = args.slice(1);
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');
  const dbUrl = getDbUrl(options);

  try {
    const manager = dbUrl
      ? new PersistentSessionManager(dbUrl)
      : getSessionManager();
    const isPersistent = !!dbUrl;

    switch (action) {
      case 'list':
        await listSessions(manager, outputFormat, isPersistent);
        break;
      case 'create':
        await createSession(manager, actionArgs, outputFormat, isPersistent);
        break;
      case 'get':
        await getSession(manager, actionArgs, outputFormat);
        break;
      case 'delete':
        await deleteSession(manager, actionArgs, outputFormat);
        break;
      case 'export':
        await exportSession(manager, actionArgs, outputFormat);
        break;
      case 'help':
      default:
        await showHelp(outputFormat);
        break;
    }
  } catch (error) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.UNKNOWN, error instanceof Error ? error.message : String(error)));
    } else {
      await pretty.error(error instanceof Error ? error.message : String(error));
    }
    process.exit(EXIT_CODES.RUNTIME_ERROR);
  }
}

async function listSessions(manager: SessionManager | PersistentSessionManager, outputFormat: string, isPersistent: boolean): Promise<void> {
  const sessions = await manager.list();

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      sessions: sessions.map((s: any) => ({
        id: s.id,
        messageCount: s.messages?.length || 0,
        createdAt: s.createdAt
      })),
      count: sessions.length,
      persistent: isPersistent
    }));
  } else {
    await pretty.heading('Sessions');
    if (isPersistent) {
      await pretty.dim('(persistent storage)');
    }
    if (sessions.length === 0) {
      await pretty.info('No sessions found');
    } else {
      for (const session of sessions) {
        await pretty.plain(`  • ${session.id}`);
        await pretty.dim(`    Messages: ${session.messages?.length || 0}`);
      }
    }
    await pretty.newline();
    await pretty.info(`Total: ${sessions.length} sessions`);
  }
}

async function createSession(manager: SessionManager | PersistentSessionManager, args: string[], outputFormat: string, isPersistent: boolean): Promise<void> {
  const sessionId = args[0];
  const session = await manager.create({ id: sessionId });

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      created: true,
      sessionId: session.id,
      persistent: isPersistent
    }));
  } else {
    await pretty.success(`Session created: ${session.id}${isPersistent ? ' (persistent)' : ''}`);
  }
}

async function getSession(manager: SessionManager | PersistentSessionManager, args: string[], outputFormat: string): Promise<void> {
  const sessionId = args[0];
  if (!sessionId) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a session ID'));
    } else {
      await pretty.error('Please provide a session ID');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const session = await manager.get(sessionId);
  if (!session) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.UNKNOWN, `Session not found: ${sessionId}`));
    } else {
      await pretty.error(`Session not found: ${sessionId}`);
    }
    process.exit(EXIT_CODES.RUNTIME_ERROR);
  }

  const messages = session.messages || [];

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      id: session.id,
      messages: messages.map((m: any) => ({
        role: m.role,
        content: m.content
      })),
      messageCount: messages.length,
      createdAt: session.createdAt
    }));
  } else {
    await pretty.heading(`Session: ${session.id}`);
    await pretty.plain(`Messages: ${messages.length}`);
    await pretty.newline();
    for (const msg of messages.slice(-10)) {
      const role = msg.role.toUpperCase();
      await pretty.plain(`  [${role}] ${msg.content?.substring(0, 100)}...`);
    }
  }
}

async function deleteSession(manager: SessionManager | PersistentSessionManager, args: string[], outputFormat: string): Promise<void> {
  const sessionId = args[0];
  if (!sessionId) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a session ID'));
    } else {
      await pretty.error('Please provide a session ID');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const deleted = await manager.delete(sessionId);

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ deleted, sessionId }));
  } else {
    if (deleted) {
      await pretty.success(`Session deleted: ${sessionId}`);
    } else {
      await pretty.error(`Session not found: ${sessionId}`);
    }
  }
}

async function exportSession(manager: SessionManager | PersistentSessionManager, args: string[], outputFormat: string): Promise<void> {
  const sessionId = args[0];
  if (!sessionId) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a session ID'));
    } else {
      await pretty.error('Please provide a session ID');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const session = await manager.get(sessionId);
  if (!session) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.UNKNOWN, `Session not found: ${sessionId}`));
    } else {
      await pretty.error(`Session not found: ${sessionId}`);
    }
    process.exit(EXIT_CODES.RUNTIME_ERROR);
  }

  // Output as JSON regardless of format
  outputJson(formatSuccess({
    id: session.id,
    messages: session.messages || [],
    createdAt: session.createdAt
  }));
}

async function showHelp(outputFormat: string): Promise<void> {
  const help = {
    command: 'session',
    subcommands: [
      { name: 'list', description: 'List all sessions' },
      { name: 'create [id]', description: 'Create a new session' },
      { name: 'get <id>', description: 'Get session details' },
      { name: 'delete <id>', description: 'Delete a session' },
      { name: 'export <id>', description: 'Export session as JSON' },
      { name: 'help', description: 'Show this help' }
    ],
    options: [
      { name: '--db <url>', description: 'Database URL for persistence (sqlite:./data.db)' }
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(help));
  } else {
    await pretty.heading('Session Command');
    await pretty.plain('Manage agent sessions\n');
    await pretty.plain('Subcommands:');
    for (const cmd of help.subcommands) {
      await pretty.plain(`  ${cmd.name.padEnd(20)} ${cmd.description}`);
    }
    await pretty.newline();
    await pretty.plain('Options:');
    for (const opt of help.options) {
      await pretty.plain(`  ${opt.name.padEnd(20)} ${opt.description}`);
    }
    await pretty.newline();
    await pretty.dim('Examples:');
    await pretty.dim('  praisonai-ts session create my-session --db sqlite:./data.db');
    await pretty.dim('  praisonai-ts session list --db sqlite:./data.db');
  }
}
