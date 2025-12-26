/**
 * Context command - Manage conversation context
 */

import { createContextAgent } from '../../agent/context';
import { resolveConfig } from '../config/resolve';
import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface ContextOptions {
  model?: string;
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
  maxMessages?: number;
}

export async function execute(args: string[], options: ContextOptions): Promise<void> {
  const action = args[0] || 'help';
  const actionArgs = args.slice(1);
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');
  const config = resolveConfig(options);

  try {
    switch (action) {
      case 'chat':
        await chatWithContext(actionArgs, options, config, outputFormat);
        break;
      case 'summarize':
        await summarizeContext(actionArgs, options, config, outputFormat);
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

async function chatWithContext(args: string[], options: ContextOptions, config: any, outputFormat: string): Promise<void> {
  const message = args.join(' ');
  if (!message) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a message'));
    } else {
      await pretty.error('Please provide a message');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const startTime = Date.now();

  if (outputFormat !== 'json') {
    await pretty.info('Processing with context...');
  }

  const agent = createContextAgent({
    llm: config.model,
    instructions: 'You are a helpful assistant with context awareness.',
    contextWindow: options.maxMessages || 10,
    verbose: options.verbose
  });

  const result = await agent.chat(message);
  const duration = Date.now() - startTime;

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      message,
      response: result.text
    }, {
      duration_ms: duration,
      model: config.model
    }));
  } else {
    await pretty.heading('Response');
    await pretty.plain(result.text);
    await pretty.newline();
    await pretty.success(`Completed in ${duration}ms`);
  }
}

async function summarizeContext(args: string[], options: ContextOptions, config: any, outputFormat: string): Promise<void> {
  const context = args.join(' ');
  if (!context) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide context to summarize'));
    } else {
      await pretty.error('Please provide context to summarize');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const startTime = Date.now();

  if (outputFormat !== 'json') {
    await pretty.info('Summarizing context...');
  }

  const agent = createContextAgent({
    llm: config.model,
    instructions: 'You are a summarization assistant. Provide concise summaries.',
    verbose: options.verbose
  });

  // Use chat to summarize
  const result = await agent.chat(`Please summarize the following text concisely:\n\n${context}`);
  const duration = Date.now() - startTime;

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      originalLength: context.length,
      summary: result.text
    }, {
      duration_ms: duration,
      model: config.model
    }));
  } else {
    await pretty.heading('Summary');
    await pretty.plain(result.text);
    await pretty.newline();
    await pretty.dim(`Original: ${context.length} chars`);
    await pretty.success(`Summarized in ${duration}ms`);
  }
}

async function showHelp(outputFormat: string): Promise<void> {
  const help = {
    command: 'context',
    subcommands: [
      { name: 'chat <message>', description: 'Chat with context management' },
      { name: 'summarize <text>', description: 'Summarize context' },
      { name: 'help', description: 'Show this help' }
    ],
    flags: [
      { name: '--max-messages', description: 'Maximum messages to keep in context' }
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(help));
  } else {
    await pretty.heading('Context Command');
    await pretty.plain('Manage conversation context\n');
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
