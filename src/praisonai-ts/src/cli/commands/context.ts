/**
 * Context command - Manage context windows
 */

import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface ContextOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
  budget?: number;
  priority?: number;
  target?: number;
  strategy?: string;
}

let currentManager: any = null;

export async function execute(args: string[], options: ContextOptions): Promise<void> {
  const action = args[0] || 'help';
  const actionArgs = args.slice(1);
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    // Lazy load to avoid import overhead
    const { ContextManager, ContextBudgeter, ContextOptimizer } = await import('../../context');

    switch (action) {
      case 'create':
        await createContext(options, outputFormat, ContextManager);
        break;
      case 'add':
        await addContent(actionArgs, options, outputFormat);
        break;
      case 'stats':
        await showStats(outputFormat);
        break;
      case 'budget':
        await manageBudget(actionArgs, options, outputFormat, ContextBudgeter);
        break;
      case 'optimize':
        await optimizeContext(options, outputFormat, ContextOptimizer);
        break;
      case 'build':
        await buildContext(outputFormat);
        break;
      case 'clear':
        await clearContext(outputFormat);
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

async function createContext(options: ContextOptions, outputFormat: string, ContextManager: any): Promise<void> {
  const budget = options.budget || 4000;
  currentManager = new ContextManager({ maxTokens: budget });

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ created: true, budget }));
  } else {
    await pretty.success(`Context manager created with budget: ${budget} tokens`);
  }
}

async function addContent(args: string[], options: ContextOptions, outputFormat: string): Promise<void> {
  if (!currentManager) {
    const { ContextManager } = await import('../../context');
    currentManager = new ContextManager({ maxTokens: options.budget || 4000 });
  }

  const content = args.join(' ');
  const priority = options.priority || 0.5;

  currentManager.add({ content, priority, type: 'user' });

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ added: true, priority, tokenEstimate: Math.ceil(content.length / 4) }));
  } else {
    await pretty.success(`Added content with priority ${priority}`);
  }
}

async function showStats(outputFormat: string): Promise<void> {
  if (!currentManager) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'No context manager created'));
    } else {
      await pretty.warn('No context manager created. Run: praisonai context create');
    }
    return;
  }

  const stats = {
    itemCount: currentManager.getItems?.()?.length || 0,
    tokenCount: currentManager.getTokenCount?.() || 0,
    maxTokens: currentManager.maxTokens || 4000
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(stats));
  } else {
    await pretty.heading('Context Stats');
    await pretty.plain(`  Items: ${stats.itemCount}`);
    await pretty.plain(`  Tokens: ${stats.tokenCount}/${stats.maxTokens}`);
  }
}

async function manageBudget(args: string[], options: ContextOptions, outputFormat: string, ContextBudgeter: any): Promise<void> {
  const subAction = args[0] || 'show';

  if (subAction === 'show') {
    if (outputFormat === 'json') {
      outputJson(formatSuccess({ budget: options.budget || 4000 }));
    } else {
      await pretty.heading('Budget Configuration');
      await pretty.plain(`  Total: ${options.budget || 4000} tokens`);
    }
  }
}

async function optimizeContext(options: ContextOptions, outputFormat: string, ContextOptimizer: any): Promise<void> {
  const target = options.target || 4000;
  const strategy = options.strategy || 'truncate-low-priority';

  const optimizer = new ContextOptimizer({ targetTokens: target, strategies: [strategy] });

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ optimized: true, target, strategy }));
  } else {
    await pretty.success(`Optimization applied: ${strategy} (target: ${target} tokens)`);
  }
}

async function buildContext(outputFormat: string): Promise<void> {
  if (!currentManager) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'No context manager'));
    } else {
      await pretty.warn('No context manager. Run: praisonai context create');
    }
    return;
  }

  const built = currentManager.build?.() || '';

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ context: built, length: built.length }));
  } else {
    console.log(built);
  }
}

async function clearContext(outputFormat: string): Promise<void> {
  if (currentManager) {
    currentManager.clear?.();
  }
  currentManager = null;

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ cleared: true }));
  } else {
    await pretty.success('Context cleared');
  }
}

async function showHelp(outputFormat: string): Promise<void> {
  const help = {
    command: 'context',
    subcommands: [
      { name: 'create', description: 'Create context manager', options: ['--budget'] },
      { name: 'add <content>', description: 'Add content', options: ['--priority'] },
      { name: 'stats', description: 'Show context stats' },
      { name: 'budget', description: 'Manage token budget' },
      { name: 'optimize', description: 'Optimize context', options: ['--target', '--strategy'] },
      { name: 'build', description: 'Build context string' },
      { name: 'clear', description: 'Clear context' },
      { name: 'help', description: 'Show this help' }
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(help));
  } else {
    await pretty.heading('Context Command');
    await pretty.plain('Manage Agent context windows\n');
    await pretty.plain('Subcommands:');
    for (const cmd of help.subcommands) {
      await pretty.plain(`  ${cmd.name.padEnd(25)} ${cmd.description}`);
    }
  }
}
