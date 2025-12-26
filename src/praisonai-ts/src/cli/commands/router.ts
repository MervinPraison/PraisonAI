/**
 * Router command - Route requests to appropriate agents
 */

import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface RouterOptions {
  model?: string;
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
  routes?: string;
}

export async function execute(args: string[], options: RouterOptions): Promise<void> {
  const action = args[0] || 'help';
  const actionArgs = args.slice(1);
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    switch (action) {
      case 'analyze':
        await analyzeInput(actionArgs, outputFormat);
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

async function analyzeInput(args: string[], outputFormat: string): Promise<void> {
  const input = args.join(' ');
  if (!input) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide input to analyze'));
    } else {
      await pretty.error('Please provide input to analyze');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const startTime = Date.now();

  if (outputFormat !== 'json') {
    await pretty.info(`Analyzing routing for: "${input}"`);
  }

  // Simple rule-based routing analysis
  const routes = [
    { name: 'greeting', pattern: /\b(hello|hi|hey|greetings)\b/i, priority: 1 },
    { name: 'question', pattern: /\?$/, priority: 2 },
    { name: 'code', pattern: /\b(code|function|class|implement|debug)\b/i, priority: 3 },
    { name: 'research', pattern: /\b(research|analyze|investigate|study)\b/i, priority: 3 },
    { name: 'creative', pattern: /\b(write|create|generate|compose)\b/i, priority: 2 },
    { name: 'general', pattern: /.*/, priority: 0 }
  ];

  const matches = routes
    .filter(r => r.pattern.test(input))
    .sort((a, b) => b.priority - a.priority);

  const selectedRoute = matches[0]?.name || 'general';
  const confidence = matches[0]?.priority ? Math.min(0.5 + matches[0].priority * 0.15, 0.95) : 0.5;

  const duration = Date.now() - startTime;

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      input,
      selectedRoute,
      confidence,
      matchedRoutes: matches.map(m => m.name)
    }, {
      duration_ms: duration
    }));
  } else {
    await pretty.heading('Routing Analysis');
    await pretty.plain(`Input: "${input}"`);
    await pretty.plain(`Selected Route: ${selectedRoute}`);
    await pretty.plain(`Confidence: ${(confidence * 100).toFixed(1)}%`);
    await pretty.plain(`Matched Routes: ${matches.map(m => m.name).join(', ')}`);
    await pretty.newline();
    await pretty.success(`Analyzed in ${duration}ms`);
  }
}

async function showHelp(outputFormat: string): Promise<void> {
  const help = {
    command: 'router',
    description: 'Route requests to appropriate agents based on content analysis',
    subcommands: [
      { name: 'analyze <input>', description: 'Analyze input and suggest routing' },
      { name: 'help', description: 'Show this help' }
    ],
    usage: 'For programmatic routing with actual agents, use the RouterAgent SDK class'
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(help));
  } else {
    await pretty.heading('Router Command');
    await pretty.plain('Route requests to appropriate agents\n');
    await pretty.plain('Subcommands:');
    for (const cmd of help.subcommands) {
      await pretty.plain(`  ${cmd.name.padEnd(25)} ${cmd.description}`);
    }
    await pretty.newline();
    await pretty.dim('Note: For full routing with agents, use the RouterAgent SDK class');
  }
}
