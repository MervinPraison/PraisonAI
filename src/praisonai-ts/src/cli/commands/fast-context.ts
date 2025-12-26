/**
 * CLI command: fast-context
 * Fast context retrieval and summarization
 */

import { FastContext, createFastContext, getQuickContext } from '../features/fast-context';

export async function execute(args: string[], options: Record<string, unknown>): Promise<void> {
  const subcommand = args[0] || 'help';
  const isJson = Boolean(options.output === 'json' || options.json);

  switch (subcommand) {
    case 'query':
      await handleQuery(args.slice(1), options, isJson);
      break;
    case 'stats':
      await handleStats(isJson);
      break;
    case 'clear':
      await handleClear(isJson);
      break;
    case 'help':
    default:
      showHelp(isJson);
  }
}

let globalContext: FastContext | null = null;

function getContext(maxTokens?: number): FastContext {
  if (!globalContext) {
    globalContext = createFastContext({ maxTokens, cacheEnabled: true });
  }
  return globalContext;
}

async function handleQuery(args: string[], options: Record<string, unknown>, isJson: boolean): Promise<void> {
  const query = args.join(' ');
  if (!query) {
    console.error('Error: Query is required');
    process.exit(1);
  }

  const maxTokens = options['max-tokens'] as number | undefined;
  const sources = options.sources as string | undefined;
  
  const fc = getContext(maxTokens);
  
  // Add sources if provided
  if (sources) {
    const sourceList = sources.split(',').map(s => s.trim());
    fc.registerSource('cli-sources', 'custom', sourceList);
  }

  const result = await fc.getContext(query);

  if (isJson) {
    console.log(JSON.stringify({ success: true, ...result }, null, 2));
  } else {
    console.log('Fast Context Result:');
    console.log(`  Query: ${query}`);
    console.log(`  Token count: ${result.tokenCount}`);
    console.log(`  Sources used: ${result.sources.length}`);
    console.log(`  Cached: ${result.cached}`);
    console.log(`  Latency: ${result.latencyMs}ms`);
    console.log('\nContext:');
    console.log(result.context || '(empty)');
  }
}

async function handleStats(isJson: boolean): Promise<void> {
  const fc = getContext();
  const stats = fc.getCacheStats();

  if (isJson) {
    console.log(JSON.stringify({ success: true, stats }, null, 2));
  } else {
    console.log('Fast Context Cache Stats:');
    console.log(`  Cache size: ${stats.size}`);
    console.log(`  Total hits: ${stats.totalHits}`);
  }
}

async function handleClear(isJson: boolean): Promise<void> {
  const fc = getContext();
  fc.clearCache();
  fc.clearSources();

  if (isJson) {
    console.log(JSON.stringify({ success: true, message: 'Cache and sources cleared' }));
  } else {
    console.log('✓ Cache and sources cleared');
  }
}

function showHelp(isJson: boolean): void {
  const help = {
    command: 'fast-context',
    description: 'Fast context retrieval and summarization',
    subcommands: {
      query: 'Query for relevant context',
      stats: 'Show cache statistics',
      clear: 'Clear cache and sources'
    },
    flags: {
      '--max-tokens': 'Maximum tokens in context (default: 4000)',
      '--sources': 'Comma-separated source texts',
      '--json': 'Output in JSON format'
    },
    examples: [
      'praisonai-ts fast-context query "What is the main topic?"',
      'praisonai-ts fast-context query "summarize" --sources "text1,text2,text3"',
      'praisonai-ts fast-context query "find relevant" --max-tokens 2000',
      'praisonai-ts fast-context stats',
      'praisonai-ts fast-context clear'
    ]
  };

  if (isJson) {
    console.log(JSON.stringify(help, null, 2));
  } else {
    console.log('Fast Context - Fast context retrieval\n');
    console.log('Subcommands:');
    for (const [cmd, desc] of Object.entries(help.subcommands)) {
      console.log(`  ${cmd.padEnd(12)} ${desc}`);
    }
    console.log('\nFlags:');
    for (const [flag, desc] of Object.entries(help.flags)) {
      console.log(`  ${flag.padEnd(14)} ${desc}`);
    }
    console.log('\nExamples:');
    for (const ex of help.examples) {
      console.log(`  ${ex}`);
    }
  }
}
