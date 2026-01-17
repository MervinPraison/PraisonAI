/**
 * Memory command - Manage agent memory with optional persistence
 */

import { Memory, createMemory, MemoryEntry, SearchResult } from '../../memory/memory';
import { db } from '../../db';
import { ENV_VARS } from '../spec/cli-spec';
import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface MemoryOptions {
  userId?: string;
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
  db?: string;
}

// Get database URL from option or env var
function getDbUrl(options: MemoryOptions): string | undefined {
  return options.db || process.env[ENV_VARS.PRAISONAI_DB];
}

// Persistent memory storage using db adapter
class PersistentMemory {
  private adapter: any;
  private sessionId: string;

  constructor(dbUrl: string, userId?: string) {
    this.adapter = db(dbUrl);
    this.sessionId = userId || 'default-memory';
  }

  async initialize(): Promise<void> {
    if (this.adapter.initialize) {
      await this.adapter.initialize();
    }
    // Create session if doesn't exist
    if (this.adapter.createSession) {
      try {
        await this.adapter.createSession(this.sessionId, { type: 'memory' });
      } catch (e) {
        // Session might already exist
      }
    }
  }

  async add(content: string, role: string = 'user'): Promise<void> {
    await this.initialize();
    const id = `mem_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    if (this.adapter.addMessage) {
      await this.adapter.addMessage({
        id,
        sessionId: this.sessionId,
        role: role as any,
        content,
        createdAt: Date.now()
      });
    }
  }

  async getAll(): Promise<MemoryEntry[]> {
    await this.initialize();
    if (this.adapter.getMessages) {
      const messages = await this.adapter.getMessages(this.sessionId);
      return messages.map((m: any) => ({
        id: m.id,
        content: m.content,
        role: m.role,
        timestamp: m.createdAt,
        metadata: m.metadata ? JSON.parse(m.metadata) : undefined
      }));
    }
    return [];
  }

  async search(query: string): Promise<SearchResult[]> {
    const all = await this.getAll();
    const queryLower = query.toLowerCase();
    return all
      .filter(e => e.content.toLowerCase().includes(queryLower))
      .map(entry => ({ entry, score: 1.0 }));
  }

  async clear(): Promise<void> {
    await this.initialize();
    if (this.adapter.clear) {
      await this.adapter.clear();
    }
  }
}

export async function execute(args: string[], options: MemoryOptions): Promise<void> {
  const action = args[0] || 'list';
  const actionArgs = args.slice(1);
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');
  const dbUrl = getDbUrl(options);

  try {
    // Use persistent or in-memory based on --db flag
    const memory = dbUrl
      ? new PersistentMemory(dbUrl, options.userId)
      : createMemory();

    switch (action) {
      case 'list':
        await listMemories(memory, outputFormat, !!dbUrl);
        break;
      case 'add':
        await addMemory(memory, actionArgs, outputFormat, !!dbUrl);
        break;
      case 'search':
        await searchMemory(memory, actionArgs, outputFormat);
        break;
      case 'clear':
        await clearMemory(memory, outputFormat);
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

async function listMemories(memory: Memory | PersistentMemory, outputFormat: string, isPersistent: boolean): Promise<void> {
  const entries = await memory.getAll();

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      memories: entries,
      count: entries.length,
      persistent: isPersistent
    }));
  } else {
    await pretty.heading('Memory Entries');
    if (isPersistent) {
      await pretty.dim('(persistent storage)');
    }
    if (entries.length === 0) {
      await pretty.info('No memories stored');
    } else {
      for (const entry of entries) {
        await pretty.plain(`  • ${entry.content.substring(0, 100)}${entry.content.length > 100 ? '...' : ''}`);
        if (entry.timestamp) {
          await pretty.dim(`    Created: ${new Date(entry.timestamp).toISOString()}`);
        }
      }
    }
    await pretty.newline();
    await pretty.info(`Total: ${entries.length} memories`);
  }
}

async function addMemory(memory: Memory | PersistentMemory, args: string[], outputFormat: string, isPersistent: boolean): Promise<void> {
  const content = args.join(' ');
  if (!content) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide content to add'));
    } else {
      await pretty.error('Please provide content to add');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  await memory.add(content, 'user');

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ added: content, persistent: isPersistent }));
  } else {
    await pretty.success(`Memory added${isPersistent ? ' (persistent)' : ''}`);
  }
}

async function searchMemory(memory: Memory | PersistentMemory, args: string[], outputFormat: string): Promise<void> {
  const query = args.join(' ');
  if (!query) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a search query'));
    } else {
      await pretty.error('Please provide a search query');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const results = await memory.search(query);

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      query,
      results,
      count: results.length
    }));
  } else {
    await pretty.heading(`Search Results for: "${query}"`);
    if (results.length === 0) {
      await pretty.info('No matching memories found');
    } else {
      for (const result of results) {
        const content = result.entry.content;
        await pretty.plain(`  • ${content.substring(0, 100)}${content.length > 100 ? '...' : ''}`);
        await pretty.dim(`    Score: ${result.score.toFixed(3)}`);
      }
    }
    await pretty.newline();
    await pretty.info(`Found: ${results.length} results`);
  }
}

async function clearMemory(memory: Memory | PersistentMemory, outputFormat: string): Promise<void> {
  await memory.clear();

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ cleared: true }));
  } else {
    await pretty.success('Memory cleared successfully');
  }
}

async function showHelp(outputFormat: string): Promise<void> {
  const help = {
    command: 'memory',
    subcommands: [
      { name: 'list', description: 'List all memories' },
      { name: 'add <content>', description: 'Add a new memory' },
      { name: 'search <query>', description: 'Search memories' },
      { name: 'clear', description: 'Clear all memories' },
      { name: 'help', description: 'Show this help' }
    ],
    options: [
      { name: '--db <url>', description: 'Database URL for persistence (sqlite:./data.db)' },
      { name: '--user-id', description: 'User ID for memory isolation' }
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(help));
  } else {
    await pretty.heading('Memory Command');
    await pretty.plain('Manage agent memory storage\n');
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
    await pretty.dim('  praisonai-ts memory add "Remember this" --db sqlite:./data.db');
    await pretty.dim('  praisonai-ts memory list --db sqlite:./data.db');
  }
}
