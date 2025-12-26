/**
 * Memory command - Manage agent memory
 */

import { Memory, createMemory, MemoryEntry, SearchResult } from '../../memory/memory';
import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface MemoryOptions {
  userId?: string;
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
}

export async function execute(args: string[], options: MemoryOptions): Promise<void> {
  const action = args[0] || 'list';
  const actionArgs = args.slice(1);
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    const memory = createMemory();

    switch (action) {
      case 'list':
        await listMemories(memory, outputFormat);
        break;
      case 'add':
        await addMemory(memory, actionArgs, outputFormat);
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

async function listMemories(memory: Memory, outputFormat: string): Promise<void> {
  const entries = memory.getAll();
  
  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      memories: entries,
      count: entries.length
    }));
  } else {
    await pretty.heading('Memory Entries');
    if (entries.length === 0) {
      await pretty.info('No memories stored');
    } else {
      for (const entry of entries) {
        await pretty.plain(`  • ${entry.content.substring(0, 100)}${entry.content.length > 100 ? '...' : ''}`);
        if (entry.metadata) {
          await pretty.dim(`    Created: ${new Date(entry.timestamp).toISOString()}`);
        }
      }
    }
    await pretty.newline();
    await pretty.info(`Total: ${entries.length} memories`);
  }
}

async function addMemory(memory: Memory, args: string[], outputFormat: string): Promise<void> {
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
    outputJson(formatSuccess({ added: content }));
  } else {
    await pretty.success('Memory added successfully');
  }
}

async function searchMemory(memory: Memory, args: string[], outputFormat: string): Promise<void> {
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

async function clearMemory(memory: Memory, outputFormat: string): Promise<void> {
  memory.clear();
  
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
  }
}
