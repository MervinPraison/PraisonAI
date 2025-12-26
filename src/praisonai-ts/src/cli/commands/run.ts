/**
 * Run command - Run an agent with a task
 */

import { Agent } from '../../agent';
import { resolveConfig } from '../config/resolve';
import { printSuccess, printError, outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES, normalizeError } from '../output/errors';

export interface RunOptions {
  agent?: string;
  tools?: string;
  model?: string;
  verbose?: boolean;
  profile?: string;
  config?: string;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
}

export async function execute(args: string[], options: RunOptions): Promise<void> {
  const task = args[0];
  
  if (!task) {
    if (options.json || options.output === 'json') {
      printError(ERROR_CODES.MISSING_ARG, 'Please provide a task');
    } else {
      await pretty.error('Please provide a task');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  // Resolve config with precedence
  const config = resolveConfig({
    configPath: options.config,
    profile: options.profile,
    model: options.model,
    verbose: options.verbose
  });

  const startTime = Date.now();
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    // Parse tools if provided
    const tools: string[] = options.tools ? options.tools.split(',').map(t => t.trim()) : [];

    // Create agent
    const agent = new Agent({
      name: 'CLI Agent',
      instructions: 'You are a helpful AI assistant.',
      llm: config.model,
      verbose: config.verbose
    });

    // Execute task
    const result = await agent.start(task);

    const duration = Date.now() - startTime;

    if (outputFormat === 'json') {
      outputJson(formatSuccess(
        { 
          result: result,
          agent: 'CLI Agent',
          task: task
        },
        {
          duration_ms: duration,
          model: config.model
        }
      ));
    } else {
      if (typeof result === 'string') {
        console.log(result);
      } else {
        console.log(JSON.stringify(result, null, 2));
      }
    }

  } catch (error) {
    const cliError = normalizeError(error);
    
    if (outputFormat === 'json') {
      outputJson(formatError(cliError.code, cliError.message, cliError.details));
    } else {
      await pretty.error(cliError.message);
      if (config.verbose && error instanceof Error && error.stack) {
        await pretty.dim(error.stack);
      }
    }
    
    process.exit(cliError.exitCode);
  }
}
