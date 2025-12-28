/**
 * Agent command - Run a single agent with instructions
 * 
 * Usage:
 *   praisonai-ts agent chat "Hello, how are you?"
 *   praisonai-ts agent run --instructions "You are helpful" "Tell me a joke"
 */

import { Agent } from '../../agent';
import { resolveConfig } from '../config/resolve';
import { printSuccess, printError, outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES, normalizeError } from '../output/errors';

export interface AgentOptions {
  instructions?: string;
  model?: string;
  stream?: boolean;
  verbose?: boolean;
  profile?: string;
  config?: string;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
  sessionId?: string;
}

/**
 * Execute agent chat subcommand
 */
export async function executeChat(args: string[], options: AgentOptions): Promise<void> {
  const prompt = args[0];
  
  if (!prompt) {
    if (options.json || options.output === 'json') {
      printError(ERROR_CODES.MISSING_ARG, 'Please provide a prompt');
    } else {
      await pretty.error('Please provide a prompt');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const config = resolveConfig({
    configPath: options.config,
    profile: options.profile,
    model: options.model,
    verbose: options.verbose,
    stream: options.stream
  });

  const startTime = Date.now();
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    const agent = new Agent({
      instructions: options.instructions || 'You are a helpful AI assistant.',
      llm: config.model,
      stream: config.stream && outputFormat !== 'json',
      verbose: config.verbose,
      sessionId: options.sessionId
    });

    const response = await agent.chat(prompt);
    const duration = Date.now() - startTime;

    if (outputFormat === 'json') {
      outputJson(formatSuccess(
        { 
          response,
          agent: agent.name,
          sessionId: agent.getSessionId()
        },
        {
          duration_ms: duration,
          model: config.model
        }
      ));
    } else if (outputFormat === 'text') {
      console.log(response);
    } else {
      // Pretty output - response already printed if streaming
      if (!config.stream) {
        console.log(response);
      }
      console.log(); // Newline
      await pretty.dim(`Completed in ${duration}ms`);
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
 * Execute agent run subcommand (same as chat but requires instructions)
 */
export async function executeRun(args: string[], options: AgentOptions): Promise<void> {
  if (!options.instructions) {
    if (options.json || options.output === 'json') {
      printError(ERROR_CODES.MISSING_ARG, 'Please provide --instructions');
    } else {
      await pretty.error('Please provide --instructions');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }
  
  return executeChat(args, options);
}

/**
 * Main execute function - routes to subcommands
 */
export async function execute(args: string[], options: AgentOptions): Promise<void> {
  const subcommand = args[0];
  const subArgs = args.slice(1);
  
  switch (subcommand) {
    case 'chat':
      return executeChat(subArgs, options);
    case 'run':
      return executeRun(subArgs, options);
    default:
      // If no subcommand, treat the first arg as a prompt for chat
      if (subcommand) {
        return executeChat(args, options);
      }
      
      if (options.json || options.output === 'json') {
        printError(ERROR_CODES.MISSING_ARG, 'Please provide a subcommand (chat, run) or a prompt');
      } else {
        await pretty.error('Usage: praisonai-ts agent [chat|run] <prompt>');
        await pretty.info('  agent chat "Hello"           - Chat with default agent');
        await pretty.info('  agent run --instructions "..." "Hello" - Run with custom instructions');
      }
      process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }
}
