/**
 * Guardrail command - Content validation and safety
 */

import { createLLMGuardrail } from '../../guardrails/llm-guardrail';
import { resolveConfig } from '../config/resolve';
import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface GuardrailOptions {
  model?: string;
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
  criteria?: string;
}

export async function execute(args: string[], options: GuardrailOptions): Promise<void> {
  const action = args[0] || 'help';
  const actionArgs = args.slice(1);
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');
  const config = resolveConfig(options);

  try {
    switch (action) {
      case 'check':
        await checkContent(actionArgs, options, config, outputFormat);
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

async function checkContent(args: string[], options: GuardrailOptions, config: any, outputFormat: string): Promise<void> {
  const content = args.join(' ');
  if (!content) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide content to check'));
    } else {
      await pretty.error('Please provide content to check');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const startTime = Date.now();

  if (outputFormat !== 'json') {
    await pretty.info('Checking content...');
  }

  const guardrail = createLLMGuardrail({
    name: 'cli-guardrail',
    llm: config.model,
    criteria: options.criteria || 'Content should be safe, appropriate, and helpful',
    verbose: options.verbose
  });

  const result = await guardrail.check(content);
  const duration = Date.now() - startTime;

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      content: content.substring(0, 100) + (content.length > 100 ? '...' : ''),
      status: result.status,
      score: result.score,
      message: result.message,
      reasoning: result.reasoning
    }, {
      duration_ms: duration,
      model: config.model
    }));
  } else {
    await pretty.heading('Guardrail Check');
    if (result.status === 'passed') {
      await pretty.success('Content passed guardrail check');
    } else if (result.status === 'warning') {
      await pretty.warn('Content has warnings');
    } else {
      await pretty.error('Content failed guardrail check');
    }
    await pretty.plain(`Score: ${(result.score * 10).toFixed(1)}/10`);
    if (result.message) {
      await pretty.plain(`Message: ${result.message}`);
    }
    if (result.reasoning) {
      await pretty.dim(`Reasoning: ${result.reasoning}`);
    }
    await pretty.newline();
    await pretty.dim(`Checked in ${duration}ms`);
  }
}

async function showHelp(outputFormat: string): Promise<void> {
  const help = {
    command: 'guardrail',
    subcommands: [
      { name: 'check <content>', description: 'Check content against guardrails' },
      { name: 'help', description: 'Show this help' }
    ],
    flags: [
      { name: '--criteria', description: 'Custom criteria for validation' }
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(help));
  } else {
    await pretty.heading('Guardrail Command');
    await pretty.plain('Content validation and safety checks\n');
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
