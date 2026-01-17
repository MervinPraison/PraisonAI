/**
 * Knowledge command - Manage knowledge base with optional persistence
 */

import { BaseKnowledgeBase, Knowledge } from '../../knowledge';
import { db } from '../../db';
import { ENV_VARS } from '../spec/cli-spec';
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
  db?: string;
}

// Get database URL from option or env var
function getDbUrl(options: KnowledgeOptions): string | undefined {
  return options.db || process.env[ENV_VARS.PRAISONAI_DB];
}

// Persistent knowledge base using db adapter
class PersistentKnowledgeBase {
  private adapter: any;
  private sessionId: string = 'knowledge-base';

  constructor(dbUrl: string) {
    this.adapter = db(dbUrl);
  }

  async initialize(): Promise<void> {
    if (this.adapter.initialize) {
      await this.adapter.initialize();
    }
    // Create knowledge session if doesn't exist
    if (this.adapter.createSession) {
      try {
        await this.adapter.createSession(this.sessionId, { type: 'knowledge' });
      } catch (e) {
        // Session might already exist
      }
    }
  }

  async addKnowledge(knowledge: Knowledge): Promise<void> {
    await this.initialize();
    if (this.adapter.addMessage) {
      const content = typeof knowledge.content === 'string'
        ? knowledge.content
        : JSON.stringify(knowledge.content);
      await this.adapter.addMessage({
        id: knowledge.id,
        sessionId: this.sessionId,
        role: 'system',
        content,
        createdAt: Date.now(),
        metadata: JSON.stringify({
          type: knowledge.type,
          source: knowledge.metadata?.source,
          ...knowledge.metadata
        })
      });
    }
  }

  async searchKnowledge(query: string): Promise<Knowledge[]> {
    await this.initialize();
    if (this.adapter.getMessages) {
      const messages = await this.adapter.getMessages(this.sessionId);
      const queryLower = query.toLowerCase();
      return messages
        .filter((m: any) => {
          if (!query) return true;
          return m.content.toLowerCase().includes(queryLower);
        })
        .map((m: any) => {
          let metadata = {};
          try {
            metadata = m.metadata ? JSON.parse(m.metadata) : {};
          } catch (e) { }
          return {
            id: m.id,
            type: (metadata as any).type || 'text',
            content: m.content,
            metadata
          };
        });
    }
    return [];
  }
}

// Singleton in-memory knowledge base
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
  const dbUrl = getDbUrl(options);

  try {
    const kb = dbUrl
      ? new PersistentKnowledgeBase(dbUrl)
      : getKnowledgeBase();
    const isPersistent = !!dbUrl;

    switch (action) {
      case 'add':
        await addKnowledge(kb, actionArgs, outputFormat, isPersistent);
        break;
      case 'search':
        await searchKnowledge(kb, actionArgs, outputFormat);
        break;
      case 'list':
        await listKnowledge(kb, outputFormat, isPersistent);
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

async function addKnowledge(kb: BaseKnowledgeBase | PersistentKnowledgeBase, args: string[], outputFormat: string, isPersistent: boolean): Promise<void> {
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

  await kb.addKnowledge(knowledge);

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      added: true,
      id: knowledge.id,
      source: sourceName,
      contentLength: content.length,
      persistent: isPersistent
    }));
  } else {
    await pretty.success(`Knowledge added from: ${sourceName}${isPersistent ? ' (persistent)' : ''}`);
    await pretty.dim(`Content length: ${content.length} characters`);
  }
}

async function searchKnowledge(kb: BaseKnowledgeBase | PersistentKnowledgeBase, args: string[], outputFormat: string): Promise<void> {
  const query = args.join(' ');
  if (!query) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a search query'));
    } else {
      await pretty.error('Please provide a search query');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const results = await kb.searchKnowledge(query);

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

async function listKnowledge(kb: BaseKnowledgeBase | PersistentKnowledgeBase, outputFormat: string, isPersistent: boolean): Promise<void> {
  // Search with empty string to get all
  const entries = await kb.searchKnowledge('');

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      entries: entries.map((e: Knowledge) => ({
        id: e.id,
        type: e.type,
        contentPreview: typeof e.content === 'string' ? e.content.substring(0, 100) : JSON.stringify(e.content).substring(0, 100),
        source: e.metadata?.source
      })),
      count: entries.length,
      persistent: isPersistent
    }));
  } else {
    await pretty.heading('Knowledge Base Entries');
    if (isPersistent) {
      await pretty.dim('(persistent storage)');
    }
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
      { name: 'help', description: 'Show this help' }
    ],
    options: [
      { name: '--db <url>', description: 'Database URL for persistence (sqlite:./data.db)' }
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
    await pretty.newline();
    await pretty.plain('Options:');
    for (const opt of help.options) {
      await pretty.plain(`  ${opt.name.padEnd(20)} ${opt.description}`);
    }
    await pretty.newline();
    await pretty.dim('Examples:');
    await pretty.dim('  praisonai-ts knowledge add "Important fact" --db sqlite:./data.db');
    await pretty.dim('  praisonai-ts knowledge list --db sqlite:./data.db');
  }
}
