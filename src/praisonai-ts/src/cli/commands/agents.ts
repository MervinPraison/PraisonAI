/**
 * Agents command - Run multi-agent orchestration
 * 
 * Usage:
 *   praisonai-ts agents run --agents "researcher,writer" "Research AI trends"
 */

import { Agent, Agents } from '../../agent';
import { resolveConfig } from '../config/resolve';
import { printSuccess, printError, outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES, normalizeError } from '../output/errors';

export interface AgentsOptions {
  agents?: string;  // Comma-separated agent instructions
  process?: 'sequential' | 'parallel';
  model?: string;
  verbose?: boolean;
  profile?: string;
  config?: string;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
}

/**
 * Parse agent definitions from comma-separated string
 */
function parseAgentDefinitions(agentsStr: string): string[] {
  return agentsStr.split(',').map(s => s.trim()).filter(s => s.length > 0);
}

/**
 * Execute agents run subcommand
 */
export async function executeRun(args: string[], options: AgentsOptions): Promise<void> {
  const prompt = args[0];
  
  if (!prompt) {
    if (options.json || options.output === 'json') {
      printError(ERROR_CODES.MISSING_ARG, 'Please provide a prompt/task');
    } else {
      await pretty.error('Please provide a prompt/task');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const config = resolveConfig({
    configPath: options.config,
    profile: options.profile,
    model: options.model,
    verbose: options.verbose
  });

  const startTime = Date.now();
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    // Create agents from definitions or use defaults
    let agentList: Agent[];
    
    if (options.agents) {
      const definitions = parseAgentDefinitions(options.agents);
      agentList = definitions.map((instructions, i) => 
        new Agent({
          instructions,
          name: `Agent_${i + 1}`,
          llm: config.model,
          verbose: config.verbose
        })
      );
    } else {
      // Default: create a researcher and writer
      agentList = [
        new Agent({
          instructions: `Research the following topic thoroughly: ${prompt}`,
          name: 'Researcher',
          llm: config.model,
          verbose: config.verbose
        }),
        new Agent({
          instructions: 'Summarize and write a clear report based on the research provided.',
          name: 'Writer',
          llm: config.model,
          verbose: config.verbose
        })
      ];
    }

    if (outputFormat !== 'json') {
      await pretty.heading(`Running ${agentList.length} agents (${options.process || 'sequential'})`);
    }

    const agents = new Agents({
      agents: agentList,
      process: options.process || 'sequential',
      verbose: config.verbose
    });

    const results = await agents.start();
    const duration = Date.now() - startTime;

    if (outputFormat === 'json') {
      outputJson(formatSuccess(
        { 
          results,
          agentCount: agentList.length,
          process: options.process || 'sequential'
        },
        {
          duration_ms: duration,
          model: config.model
        }
      ));
    } else if (outputFormat === 'text') {
      results.forEach((result, i) => {
        console.log(`\n--- Agent ${i + 1} ---\n${result}`);
      });
    } else {
      // Pretty output
      console.log();
      await pretty.success(`Completed ${agentList.length} agents in ${duration}ms`);
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

/**
 * Main execute function - routes to subcommands
 */
export async function execute(args: string[], options: AgentsOptions): Promise<void> {
  const subcommand = args[0];
  const subArgs = args.slice(1);
  
  switch (subcommand) {
    case 'run':
      return executeRun(subArgs, options);
    default:
      // If no subcommand, treat as run
      if (subcommand) {
        return executeRun(args, options);
      }
      
      if (options.json || options.output === 'json') {
        printError(ERROR_CODES.MISSING_ARG, 'Please provide a task/prompt');
      } else {
        await pretty.error('Usage: praisonai-ts agents [run] <task>');
        await pretty.info('  agents run "Research AI"     - Run with default agents');
        await pretty.info('  agents run --agents "..." "Research AI" - Run with custom agents');
        await pretty.info('  agents run --process parallel "Research AI" - Run in parallel');
      }
      process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }
}
