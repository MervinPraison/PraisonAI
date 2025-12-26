/**
 * Graph RAG command - Graph-based retrieval augmented generation
 */

import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface GraphRagOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
}

export async function execute(args: string[], options: GraphRagOptions): Promise<void> {
  const action = args[0] || 'help';
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    switch (action) {
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
    feature: 'Graph RAG',
    description: 'Graph-based retrieval augmented generation for complex knowledge queries',
    capabilities: [
      'Build knowledge graphs from documents',
      'Query relationships between entities',
      'Combine graph traversal with vector search',
      'Extract entities and relationships',
      'Support for complex multi-hop queries'
    ],
    sdkUsage: `
import { createGraphRAG, GraphStore } from 'praisonai';

// Create a graph RAG instance
const graphRag = createGraphRAG({
  llm: 'openai/gpt-4o-mini',
  graphStore: new GraphStore()
});

// Add documents
await graphRag.addDocument('Document content...');

// Query with graph context
const result = await graphRag.query('What is the relationship between X and Y?');
`
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(info));
  } else {
    await pretty.heading('Graph RAG');
    await pretty.plain(info.description);
    await pretty.newline();
    await pretty.plain('Capabilities:');
    for (const cap of info.capabilities) {
      await pretty.plain(`  • ${cap}`);
    }
    await pretty.newline();
    await pretty.dim('Use the SDK for full Graph RAG functionality');
  }
}

async function showHelp(outputFormat: string): Promise<void> {
  const help = {
    command: 'graph-rag',
    description: 'Graph-based retrieval augmented generation',
    subcommands: [
      { name: 'info', description: 'Show Graph RAG feature information' },
      { name: 'help', description: 'Show this help' }
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(help));
  } else {
    await pretty.heading('Graph RAG Command');
    await pretty.plain(help.description);
    await pretty.newline();
    await pretty.plain('Subcommands:');
    for (const cmd of help.subcommands) {
      await pretty.plain(`  ${cmd.name.padEnd(20)} ${cmd.description}`);
    }
  }
}
