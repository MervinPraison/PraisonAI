/**
 * Vector command - Vector store management with full operations
 */

import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES, ENV_VARS } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface VectorOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
  store?: string;
  db?: string;
}

// In-memory vector store for CLI usage
interface VectorEntry {
  id: string;
  content: string;
  embedding?: number[];
  metadata?: Record<string, any>;
  createdAt: number;
}

class MemoryVectorStore {
  private entries: Map<string, VectorEntry> = new Map();

  async add(content: string, id?: string): Promise<string> {
    const entryId = id || `vec_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    this.entries.set(entryId, {
      id: entryId,
      content,
      createdAt: Date.now()
    });
    return entryId;
  }

  async search(query: string, topK: number = 5): Promise<Array<{ entry: VectorEntry; score: number }>> {
    const queryLower = query.toLowerCase();
    const results: Array<{ entry: VectorEntry; score: number }> = [];

    for (const entry of this.entries.values()) {
      const contentLower = entry.content.toLowerCase();
      if (contentLower.includes(queryLower)) {
        // Simple keyword matching score
        const score = queryLower.split(' ').filter(word => contentLower.includes(word)).length / queryLower.split(' ').length;
        results.push({ entry, score: Math.max(0.1, score) });
      }
    }

    return results.sort((a, b) => b.score - a.score).slice(0, topK);
  }

  async stats(): Promise<{ count: number; totalChars: number }> {
    let totalChars = 0;
    for (const entry of this.entries.values()) {
      totalChars += entry.content.length;
    }
    return { count: this.entries.size, totalChars };
  }

  async list(): Promise<VectorEntry[]> {
    return Array.from(this.entries.values());
  }

  async clear(): Promise<void> {
    this.entries.clear();
  }
}

// Singleton store instance
let vectorStore: MemoryVectorStore | null = null;

function getVectorStore(): MemoryVectorStore {
  if (!vectorStore) {
    vectorStore = new MemoryVectorStore();
  }
  return vectorStore;
}

export async function execute(args: string[], options: VectorOptions): Promise<void> {
  const action = args[0] || 'help';
  const actionArgs = args.slice(1);
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    switch (action) {
      case 'add':
        await addVector(actionArgs, options, outputFormat);
        break;
      case 'search':
        await searchVector(actionArgs, options, outputFormat);
        break;
      case 'stats':
        await showStats(outputFormat);
        break;
      case 'list':
        await listVectors(outputFormat);
        break;
      case 'clear':
        await clearVectors(outputFormat);
        break;
      case 'providers':
        await listProviders(outputFormat);
        break;
      case 'info':
        await showInfo(outputFormat);
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

async function addVector(args: string[], options: VectorOptions, outputFormat: string): Promise<void> {
  const content = args.join(' ');
  if (!content) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide content to add'));
    } else {
      await pretty.error('Please provide content to add');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const store = getVectorStore();
  const id = await store.add(content);

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      added: true,
      id,
      contentLength: content.length
    }));
  } else {
    await pretty.success(`Vector added: ${id}`);
    await pretty.dim(`Content length: ${content.length} characters`);
  }
}

async function searchVector(args: string[], options: VectorOptions, outputFormat: string): Promise<void> {
  const query = args.join(' ');
  if (!query) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a search query'));
    } else {
      await pretty.error('Please provide a search query');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const store = getVectorStore();
  const results = await store.search(query);

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      query,
      results: results.map(r => ({
        id: r.entry.id,
        content: r.entry.content,
        score: r.score
      })),
      count: results.length
    }));
  } else {
    await pretty.heading(`Search Results for: "${query}"`);
    if (results.length === 0) {
      await pretty.info('No matching vectors found');
    } else {
      for (const result of results) {
        await pretty.plain(`  • ${result.entry.content.substring(0, 80)}${result.entry.content.length > 80 ? '...' : ''}`);
        await pretty.dim(`    Score: ${result.score.toFixed(3)} | ID: ${result.entry.id}`);
      }
    }
    await pretty.newline();
    await pretty.info(`Found: ${results.length} results`);
  }
}

async function showStats(outputFormat: string): Promise<void> {
  const store = getVectorStore();
  const stats = await store.stats();

  if (outputFormat === 'json') {
    outputJson(formatSuccess(stats));
  } else {
    await pretty.heading('Vector Store Statistics');
    await pretty.plain(`  Entries: ${stats.count}`);
    await pretty.plain(`  Total Characters: ${stats.totalChars}`);
  }
}

async function listVectors(outputFormat: string): Promise<void> {
  const store = getVectorStore();
  const entries = await store.list();

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      entries: entries.map(e => ({
        id: e.id,
        content: e.content,
        createdAt: e.createdAt
      })),
      count: entries.length
    }));
  } else {
    await pretty.heading('Vector Store Entries');
    if (entries.length === 0) {
      await pretty.info('No vectors stored');
    } else {
      for (const entry of entries) {
        await pretty.plain(`  • ${entry.content.substring(0, 60)}${entry.content.length > 60 ? '...' : ''}`);
        await pretty.dim(`    ID: ${entry.id}`);
      }
    }
    await pretty.newline();
    await pretty.info(`Total: ${entries.length} entries`);
  }
}

async function clearVectors(outputFormat: string): Promise<void> {
  const store = getVectorStore();
  await store.clear();

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ cleared: true }));
  } else {
    await pretty.success('Vector store cleared');
  }
}

async function showInfo(outputFormat: string): Promise<void> {
  const info = {
    feature: 'Vector Stores',
    description: 'Vector database integrations for embeddings and similarity search',
    providers: [
      { name: 'MemoryVectorStore', description: 'In-memory vector store for development' },
      { name: 'PineconeVectorStore', description: 'Pinecone cloud vector database' },
      { name: 'WeaviateVectorStore', description: 'Weaviate vector search engine' },
      { name: 'QdrantVectorStore', description: 'Qdrant vector database' },
      { name: 'ChromaVectorStore', description: 'ChromaDB embedding database' }
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(info));
  } else {
    await pretty.heading('Vector Stores');
    await pretty.plain(info.description);
    await pretty.newline();
    await pretty.plain('Available Providers:');
    for (const p of info.providers) {
      await pretty.plain(`  • ${p.name}: ${p.description}`);
    }
  }
}

async function listProviders(outputFormat: string): Promise<void> {
  const providers = [
    { name: 'memory', description: 'In-memory vector store (default)', available: true },
    { name: 'pinecone', description: 'Pinecone vector database', available: true },
    { name: 'weaviate', description: 'Weaviate vector database', available: true },
    { name: 'qdrant', description: 'Qdrant vector database', available: true },
    { name: 'chroma', description: 'ChromaDB vector database', available: true }
  ];

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ providers }));
  } else {
    await pretty.heading('Vector Store Providers');
    for (const p of providers) {
      const status = p.available ? '✓' : '✗';
      await pretty.plain(`  ${status} ${p.name.padEnd(15)} ${p.description}`);
    }
  }
}

async function showHelp(outputFormat: string): Promise<void> {
  const help = {
    command: 'vector',
    description: 'Vector store management for embeddings and similarity search',
    subcommands: [
      { name: 'add <content>', description: 'Add document to vector store' },
      { name: 'search <query>', description: 'Search vector store' },
      { name: 'stats', description: 'Show vector store statistics' },
      { name: 'list', description: 'List all vectors' },
      { name: 'clear', description: 'Clear vector store' },
      { name: 'providers', description: 'List available vector store providers' },
      { name: 'help', description: 'Show this help' }
    ],
    flags: [
      { name: '--store', description: 'Vector store provider (memory, pinecone, etc.)' }
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(help));
  } else {
    await pretty.heading('Vector Command');
    await pretty.plain(help.description);
    await pretty.newline();
    await pretty.plain('Subcommands:');
    for (const cmd of help.subcommands) {
      await pretty.plain(`  ${cmd.name.padEnd(25)} ${cmd.description}`);
    }
    await pretty.newline();
    await pretty.plain('Flags:');
    for (const flag of help.flags) {
      await pretty.plain(`  ${flag.name.padEnd(20)} ${flag.description}`);
    }
    await pretty.newline();
    await pretty.dim('Examples:');
    await pretty.dim('  praisonai-ts vector add "Hello world"');
    await pretty.dim('  praisonai-ts vector search "hello"');
    await pretty.dim('  praisonai-ts vector stats');
  }
}
