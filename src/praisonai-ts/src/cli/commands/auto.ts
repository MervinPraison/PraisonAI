/**
 * Auto command - AutoAgents for automatic agent generation
 */

import { AutoAgents, createAutoAgents } from '../../auto';
import { resolveConfig } from '../config/resolve';
import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface AutoOptions {
  model?: string;
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
  pattern?: string;
  agents?: number;
}

export async function execute(args: string[], options: AutoOptions): Promise<void> {
  const topic = args.join(' ');
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');
  const config = resolveConfig(options);

  if (!topic) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Please provide a topic for auto-generation'));
    } else {
      await pretty.error('Please provide a topic for auto-generation');
      await pretty.dim('Usage: praisonai-ts auto "Create a research team"');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const startTime = Date.now();

  try {
    if (outputFormat !== 'json') {
      await pretty.info(`Generating agents for: "${topic}"`);
    }

    const autoAgents = createAutoAgents({
      llm: config.model,
      pattern: options.pattern as any,
      verbose: options.verbose
    });

    const result = await autoAgents.generate(topic);

    const duration = Date.now() - startTime;

    if (outputFormat === 'json') {
      outputJson(formatSuccess({
        topic,
        agents: result.agents,
        tasks: result.tasks,
        pattern: result.pattern
      }, {
        duration_ms: duration,
        model: config.model
      }));
    } else {
      await pretty.heading('Generated Team');
      await pretty.plain(`Pattern: ${result.pattern}`);
      await pretty.newline();
      
      await pretty.plain('Agents:');
      for (const agent of result.agents) {
        await pretty.plain(`  • ${agent.name}: ${agent.role}`);
      }
      
      await pretty.newline();
      await pretty.plain('Tasks:');
      for (const task of result.tasks) {
        await pretty.plain(`  • ${task.description?.substring(0, 60)}...`);
      }
      
      await pretty.newline();
      await pretty.success(`Generated in ${duration}ms`);
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
