/**
 * Prompt Expand command - Expand prompts with more detail
 */

import { createPromptExpanderAgent } from '../../agent/prompt-expander';
import { resolveConfig } from '../config/resolve';
import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface PromptExpandOptions {
  model?: string;
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
  strategy?: string;
}

export async function execute(args: string[], options: PromptExpandOptions): Promise<void> {
  const prompt = args.join(' ');
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');
  const config = resolveConfig(options);

  if (!prompt) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a prompt to expand'));
    } else {
      await pretty.error('Please provide a prompt to expand');
      await pretty.dim('Usage: praisonai-ts prompt-expand "your prompt"');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const startTime = Date.now();

  try {
    if (outputFormat !== 'json') {
      await pretty.info(`Expanding prompt: "${prompt}"`);
    }

    const agent = createPromptExpanderAgent({
      llm: config.model,
      verbose: options.verbose,
      defaultStrategy: options.strategy as any
    });

    const result = await agent.expand(prompt);

    const duration = Date.now() - startTime;

    if (outputFormat === 'json') {
      outputJson(formatSuccess({
        originalPrompt: prompt,
        expandedPrompt: result.expanded,
        strategy: result.strategy,
        additions: result.additions
      }, {
        duration_ms: duration,
        model: config.model
      }));
    } else {
      await pretty.heading('Expanded Prompt');
      await pretty.plain(result.expanded);
      await pretty.newline();
      await pretty.dim(`Strategy: ${result.strategy}`);
      await pretty.success(`Completed in ${duration}ms`);
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
