/**
 * DB command - Database adapter management
 */

import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface DbOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
}

export async function execute(args: string[], options: DbOptions): Promise<void> {
  const action = args[0] || 'help';
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    switch (action) {
      case 'info':
        await showInfo(outputFormat);
        break;
      case 'adapters':
        await listAdapters(outputFormat);
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

async function showInfo(outputFormat: string): Promise<void> {
  const info = {
    feature: 'Database Adapters',
    description: 'Database adapters for persistence and session storage',
    adapters: [
      { name: 'SQLiteAdapter', description: 'SQLite database adapter' },
      { name: 'UpstashRedisAdapter', description: 'Upstash Redis adapter' },
      { name: 'MemoryRedisAdapter', description: 'In-memory Redis-compatible adapter' },
      { name: 'NeonPostgresAdapter', description: 'Neon PostgreSQL adapter' },
      { name: 'MemoryPostgresAdapter', description: 'In-memory PostgreSQL-compatible adapter' },
      { name: 'PostgresSessionStorage', description: 'PostgreSQL session storage' }
    ],
    capabilities: [
      'Store conversation history',
      'Persist agent state',
      'Session management',
      'Message storage and retrieval',
      'Trace logging'
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(info));
  } else {
    await pretty.heading('Database Adapters');
    await pretty.plain(info.description);
    await pretty.newline();
    await pretty.plain('Available Adapters:');
    for (const a of info.adapters) {
      await pretty.plain(`  • ${a.name}: ${a.description}`);
    }
    await pretty.newline();
    await pretty.plain('Capabilities:');
    for (const cap of info.capabilities) {
      await pretty.plain(`  • ${cap}`);
    }
  }
}

async function listAdapters(outputFormat: string): Promise<void> {
  const adapters = [
    { name: 'sqlite', description: 'SQLite database', available: true },
    { name: 'redis', description: 'Redis (Upstash)', available: true },
    { name: 'postgres', description: 'PostgreSQL (Neon)', available: true },
    { name: 'memory', description: 'In-memory adapters', available: true }
  ];

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ adapters }));
  } else {
    await pretty.heading('Database Adapters');
    for (const a of adapters) {
      const status = a.available ? '✓' : '✗';
      await pretty.plain(`  ${status} ${a.name.padEnd(15)} ${a.description}`);
    }
  }
}

async function showHelp(outputFormat: string): Promise<void> {
  const help = {
    command: 'db',
    description: 'Database adapter management',
    subcommands: [
      { name: 'info', description: 'Show database adapter information' },
      { name: 'adapters', description: 'List available database adapters' },
      { name: 'help', description: 'Show this help' }
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(help));
  } else {
    await pretty.heading('Database Command');
    await pretty.plain(help.description);
    await pretty.newline();
    await pretty.plain('Subcommands:');
    for (const cmd of help.subcommands) {
      await pretty.plain(`  ${cmd.name.padEnd(20)} ${cmd.description}`);
    }
  }
}
