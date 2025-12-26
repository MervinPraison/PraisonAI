/**
 * Research command - Deep research agent
 */

import { createDeepResearchAgent } from '../../agent/research';
import { resolveConfig } from '../config/resolve';
import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface ResearchOptions {
  model?: string;
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
  depth?: number;
  maxSources?: number;
}

export async function execute(args: string[], options: ResearchOptions): Promise<void> {
  const query = args.join(' ');
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');
  const config = resolveConfig(options);

  if (!query) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a research query'));
    } else {
      await pretty.error('Please provide a research query');
      await pretty.dim('Usage: praisonai-ts research "What are the latest AI trends?"');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const startTime = Date.now();

  try {
    if (outputFormat !== 'json') {
      await pretty.info(`Researching: "${query}"`);
    }

    const agent = createDeepResearchAgent({
      llm: config.model,
      verbose: options.verbose,
      maxIterations: options.depth
    });

    const result = await agent.research(query);

    const duration = Date.now() - startTime;

    if (outputFormat === 'json') {
      outputJson(formatSuccess({
        query,
        answer: result.answer,
        citations: result.citations,
        reasoning: result.reasoning,
        confidence: result.confidence
      }, {
        duration_ms: duration,
        model: config.model
      }));
    } else {
      await pretty.heading('Research Results');
      await pretty.newline();
      await pretty.plain(result.answer);
      
      if (result.citations && result.citations.length > 0) {
        await pretty.newline();
        await pretty.plain('Citations:');
        for (const citation of result.citations) {
          await pretty.dim(`  • ${citation.title || citation.url}`);
        }
      }
      
      await pretty.newline();
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
