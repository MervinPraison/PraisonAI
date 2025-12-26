/**
 * Vector command - Vector store management
 */

import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface VectorOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
  store?: string;
}

export async function execute(args: string[], options: VectorOptions): Promise<void> {
  const action = args[0] || 'help';
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    switch (action) {
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
    ],
    sdkUsage: `
import { createMemoryVectorStore, createPineconeStore } from 'praisonai';

// Create a memory vector store
const store = createMemoryVectorStore('my-store');

// Create index
await store.createIndex({ indexName: 'docs', dimension: 1536 });

// Upsert vectors
await store.upsert({
  indexName: 'docs',
  vectors: [{ id: '1', vector: [...], metadata: { text: 'Hello' } }]
});

// Query
const results = await store.query({
  indexName: 'docs',
  vector: [...],
  topK: 5
});
`
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
    await pretty.newline();
    await pretty.dim('Use the SDK for full vector store functionality');
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
  }
}
