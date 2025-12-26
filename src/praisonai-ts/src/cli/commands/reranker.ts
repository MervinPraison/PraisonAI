/**
 * Reranker command - Document reranking
 */

import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface RerankerOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
  provider?: string;
}

export async function execute(args: string[], options: RerankerOptions): Promise<void> {
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
    feature: 'Reranker',
    description: 'Rerank search results for improved relevance',
    providers: [
      { name: 'CohereReranker', description: 'Cohere reranking API' },
      { name: 'CrossEncoderReranker', description: 'Cross-encoder model reranking' },
      { name: 'LLMReranker', description: 'LLM-based reranking' }
    ],
    capabilities: [
      'Rerank search results by relevance',
      'Improve RAG retrieval quality',
      'Multiple reranking strategies',
      'Configurable top-k selection'
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(info));
  } else {
    await pretty.heading('Reranker');
    await pretty.plain(info.description);
    await pretty.newline();
    await pretty.plain('Providers:');
    for (const p of info.providers) {
      await pretty.plain(`  • ${p.name}: ${p.description}`);
    }
    await pretty.newline();
    await pretty.plain('Capabilities:');
    for (const cap of info.capabilities) {
      await pretty.plain(`  • ${cap}`);
    }
  }
}

async function listProviders(outputFormat: string): Promise<void> {
  const providers = [
    { name: 'cohere', description: 'Cohere reranking API', available: true },
    { name: 'cross-encoder', description: 'Cross-encoder model', available: true },
    { name: 'llm', description: 'LLM-based reranking', available: true }
  ];

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ providers }));
  } else {
    await pretty.heading('Reranker Providers');
    for (const p of providers) {
      const status = p.available ? '✓' : '✗';
      await pretty.plain(`  ${status} ${p.name.padEnd(15)} ${p.description}`);
    }
  }
}

async function showHelp(outputFormat: string): Promise<void> {
  const help = {
    command: 'reranker',
    description: 'Document reranking for improved search relevance',
    subcommands: [
      { name: 'info', description: 'Show reranker feature information' },
      { name: 'providers', description: 'List available reranker providers' },
      { name: 'help', description: 'Show this help' }
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(help));
  } else {
    await pretty.heading('Reranker Command');
    await pretty.plain(help.description);
    await pretty.newline();
    await pretty.plain('Subcommands:');
    for (const cmd of help.subcommands) {
      await pretty.plain(`  ${cmd.name.padEnd(20)} ${cmd.description}`);
    }
  }
}
