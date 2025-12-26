/**
 * Session command - Manage agent sessions
 */

import { Session, SessionManager, getSessionManager } from '../../session';
import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface SessionOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
}

export async function execute(args: string[], options: SessionOptions): Promise<void> {
  const action = args[0] || 'list';
  const actionArgs = args.slice(1);
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    const manager = getSessionManager();

    switch (action) {
      case 'list':
        await listSessions(manager, outputFormat);
        break;
      case 'create':
        await createSession(manager, actionArgs, outputFormat);
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

async function listSessions(manager: SessionManager, outputFormat: string): Promise<void> {
  const sessions = manager.list();
  
  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      sessions: sessions.map((s: Session) => ({
        id: s.id,
        messageCount: s.messages.length,
        createdAt: s.createdAt
      })),
      count: sessions.length
    }));
  } else {
    await pretty.heading('Sessions');
    if (sessions.length === 0) {
      await pretty.info('No sessions found');
    } else {
      for (const session of sessions) {
        await pretty.plain(`  • ${session.id}`);
        await pretty.dim(`    Messages: ${session.messages.length}`);
      }
    }
    await pretty.newline();
    await pretty.info(`Total: ${sessions.length} sessions`);
  }
}

async function createSession(manager: SessionManager, args: string[], outputFormat: string): Promise<void> {
  const sessionId = args[0];
  const session = manager.create({ id: sessionId });
  
  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      created: true,
      sessionId: session.id
    }));
  } else {
    await pretty.success(`Session created: ${session.id}`);
  }
}

async function getSession(manager: SessionManager, args: string[], outputFormat: string): Promise<void> {
  const sessionId = args[0];
  if (!sessionId) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a session ID'));
    } else {
      await pretty.error('Please provide a session ID');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const session = manager.get(sessionId);
  if (!session) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.UNKNOWN, `Session not found: ${sessionId}`));
    } else {
      await pretty.error(`Session not found: ${sessionId}`);
    }
    process.exit(EXIT_CODES.RUNTIME_ERROR);
  }

  const messages = session.messages;
  
  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      id: session.id,
      messages,
      messageCount: messages.length
    }));
  } else {
    await pretty.heading(`Session: ${session.id}`);
    await pretty.plain(`Messages: ${messages.length}`);
    await pretty.newline();
    for (const msg of messages.slice(-10)) {
      const content = msg.content || '';
      await pretty.plain(`  [${msg.role}] ${content.substring(0, 80)}${content.length > 80 ? '...' : ''}`);
    }
  }
}

async function deleteSession(manager: SessionManager, args: string[], outputFormat: string): Promise<void> {
  const sessionId = args[0];
  if (!sessionId) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a session ID'));
    } else {
      await pretty.error('Please provide a session ID');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const deleted = manager.delete(sessionId);
  
  if (outputFormat === 'json') {
    outputJson(formatSuccess({ deleted, sessionId }));
  } else {
    if (deleted) {
      await pretty.success(`Session deleted: ${sessionId}`);
    } else {
      await pretty.warn(`Session not found: ${sessionId}`);
    }
  }
}

async function exportSession(manager: SessionManager, args: string[], outputFormat: string): Promise<void> {
  const sessionId = args[0];
  if (!sessionId) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a session ID'));
    } else {
      await pretty.error('Please provide a session ID');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const session = manager.get(sessionId);
  if (!session) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.UNKNOWN, `Session not found: ${sessionId}`));
    } else {
      await pretty.error(`Session not found: ${sessionId}`);
    }
    process.exit(EXIT_CODES.RUNTIME_ERROR);
  }

  const exported = session.toJSON();
  
  if (outputFormat === 'json') {
    outputJson(formatSuccess(exported));
  } else {
    console.log(JSON.stringify(exported, null, 2));
  }
}

async function showHelp(outputFormat: string): Promise<void> {
  const help = {
    command: 'session',
    subcommands: [
      { name: 'list', description: 'List all sessions' },
      { name: 'create [id]', description: 'Create a new session' },
      { name: 'get <id>', description: 'Get session details' },
      { name: 'delete <id>', description: 'Delete a session' },
      { name: 'export <id>', description: 'Export session data' },
      { name: 'help', description: 'Show this help' }
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
  }
}
