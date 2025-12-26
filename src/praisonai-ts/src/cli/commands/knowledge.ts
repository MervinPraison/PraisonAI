/**
 * Knowledge command - Manage knowledge base
 */

import { BaseKnowledgeBase, Knowledge } from '../../knowledge';
import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';
import * as fs from 'fs';
import * as path from 'path';
import { randomUUID } from 'crypto';

export interface KnowledgeOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
}

// Singleton knowledge base instance
let kbInstance: BaseKnowledgeBase | null = null;
function getKnowledgeBase(): BaseKnowledgeBase {
  if (!kbInstance) {
    kbInstance = new BaseKnowledgeBase();
  }
  return kbInstance;
}

export async function execute(args: string[], options: KnowledgeOptions): Promise<void> {
  const action = args[0] || 'help';
  const actionArgs = args.slice(1);
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    const kb = getKnowledgeBase();

    switch (action) {
      case 'add':
        await addKnowledge(kb, actionArgs, outputFormat);
        break;
      case 'search':
        await searchKnowledge(kb, actionArgs, outputFormat);
        break;
      case 'list':
        await listKnowledge(kb, outputFormat);
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

async function addKnowledge(kb: BaseKnowledgeBase, args: string[], outputFormat: string): Promise<void> {
  const source = args[0];
  if (!source) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a file path or text content'));
    } else {
      await pretty.error('Please provide a file path or text content');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  let content: string;
  let sourceName: string;

  // Check if it's a file path
  if (fs.existsSync(source)) {
    content = fs.readFileSync(source, 'utf-8');
    sourceName = path.basename(source);
  } else {
    // Treat as direct text content
    content = args.join(' ');
    sourceName = 'text-input';
  }

  const knowledge: Knowledge = {
    id: randomUUID(),
    type: 'text',
    content,
    metadata: { source: sourceName, addedAt: new Date().toISOString() }
  };
  
  kb.addKnowledge(knowledge);
  
  if (outputFormat === 'json') {
    outputJson(formatSuccess({ 
      added: true, 
      id: knowledge.id,
      source: sourceName,
      contentLength: content.length 
    }));
  } else {
    await pretty.success(`Knowledge added from: ${sourceName}`);
    await pretty.dim(`Content length: ${content.length} characters`);
  }
}

async function searchKnowledge(kb: BaseKnowledgeBase, args: string[], outputFormat: string): Promise<void> {
  const query = args.join(' ');
  if (!query) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a search query'));
    } else {
      await pretty.error('Please provide a search query');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const results = kb.searchKnowledge(query);
  
  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      query,
      results: results.map(r => ({
        id: r.id,
        content: r.content,
        metadata: r.metadata
      })),
      count: results.length
    }));
  } else {
    await pretty.heading(`Search Results for: "${query}"`);
    if (results.length === 0) {
      await pretty.info('No matching knowledge found');
    } else {
      for (const result of results) {
        const contentStr = typeof result.content === 'string' ? result.content : JSON.stringify(result.content);
        await pretty.plain(`  • ${contentStr.substring(0, 100)}${contentStr.length > 100 ? '...' : ''}`);
        if (result.metadata?.source) {
          await pretty.dim(`    Source: ${result.metadata.source}`);
        }
      }
    }
    await pretty.newline();
    await pretty.info(`Found: ${results.length} results`);
  }
}

async function listKnowledge(kb: BaseKnowledgeBase, outputFormat: string): Promise<void> {
  // Search with empty string to get all
  const entries = kb.searchKnowledge('');
  
  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      entries: entries.map((e: Knowledge) => ({
        id: e.id,
        type: e.type,
        contentPreview: typeof e.content === 'string' ? e.content.substring(0, 100) : JSON.stringify(e.content).substring(0, 100),
        source: e.metadata?.source
      })),
      count: entries.length
    }));
  } else {
    await pretty.heading('Knowledge Base Entries');
    if (entries.length === 0) {
      await pretty.info('No knowledge entries found');
    } else {
      for (const entry of entries) {
        const contentStr = typeof entry.content === 'string' ? entry.content : JSON.stringify(entry.content);
        await pretty.plain(`  • ${contentStr.substring(0, 80)}${contentStr.length > 80 ? '...' : ''}`);
        if (entry.metadata?.source) {
          await pretty.dim(`    Source: ${entry.metadata.source}`);
        }
      }
    }
    await pretty.newline();
    await pretty.info(`Total: ${entries.length} entries`);
  }
}

async function showHelp(outputFormat: string): Promise<void> {
  const help = {
    command: 'knowledge',
    subcommands: [
      { name: 'add <file|text>', description: 'Add knowledge from file or text' },
      { name: 'search <query>', description: 'Search knowledge base' },
      { name: 'list', description: 'List all knowledge entries' },
      { name: 'clear', description: 'Clear all knowledge' },
      { name: 'help', description: 'Show this help' }
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(help));
  } else {
    await pretty.heading('Knowledge Command');
    await pretty.plain('Manage knowledge base for RAG\n');
    await pretty.plain('Subcommands:');
    for (const cmd of help.subcommands) {
      await pretty.plain(`  ${cmd.name.padEnd(25)} ${cmd.description}`);
    }
  }
}
