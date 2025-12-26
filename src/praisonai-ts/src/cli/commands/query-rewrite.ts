/**
 * Query Rewrite command - Rewrite queries for better search results
 */

import { createQueryRewriterAgent } from '../../agent/query-rewriter';
import { resolveConfig } from '../config/resolve';
import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface QueryRewriteOptions {
  model?: string;
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
  strategy?: string;
  count?: number;
}

export async function execute(args: string[], options: QueryRewriteOptions): Promise<void> {
  const query = args.join(' ');
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');
  const config = resolveConfig(options);

  if (!query) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a query to rewrite'));
    } else {
      await pretty.error('Please provide a query to rewrite');
      await pretty.dim('Usage: praisonai-ts query-rewrite "your search query"');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const startTime = Date.now();

  try {
    if (outputFormat !== 'json') {
      await pretty.info(`Rewriting query: "${query}"`);
    }

    const agent = createQueryRewriterAgent({
      llm: config.model,
      verbose: options.verbose,
      defaultStrategy: options.strategy as any
    });

    const result = await agent.rewrite(query);

    const duration = Date.now() - startTime;

    if (outputFormat === 'json') {
      outputJson(formatSuccess({
        originalQuery: query,
        rewrittenQueries: result.rewritten,
        strategy: result.strategy,
        confidence: result.confidence
      }, {
        duration_ms: duration,
        model: config.model
      }));
    } else {
      await pretty.heading('Rewritten Queries');
      for (let i = 0; i < result.rewritten.length; i++) {
        await pretty.plain(`  ${i + 1}. ${result.rewritten[i]}`);
      }
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
