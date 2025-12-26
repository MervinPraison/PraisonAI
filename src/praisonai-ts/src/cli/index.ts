#!/usr/bin/env node
/**
 * PraisonAI TypeScript CLI
 * Implements CLI Spec v1.0.0
 * 
 * Binary: praisonai-ts
 * Package: praisonai (npm)
 */

import { validateCommand, COMMANDS, GLOBAL_FLAGS, EXIT_CODES, CLI_SPEC_VERSION } from './spec/cli-spec';
import { exitInvalidArgs, exitError } from './runtime/exit';
import { outputJson, formatError } from './output/json';
import { ERROR_CODES, normalizeError } from './output/errors';

export interface ParsedArgs {
  command: string;
  subcommand?: string;
  args: string[];
  options: Record<string, unknown>;
}

/**
 * Parse command line arguments according to CLI spec
 */
function parseArgs(argv: string[]): ParsedArgs {
  const result: ParsedArgs = {
    command: 'help',
    args: [],
    options: {}
  };

  let i = 0;
  let foundCommand = false;

  while (i < argv.length) {
    const arg = argv[i];

    if (arg.startsWith('--')) {
      // Long flag
      const flagName = arg.slice(2);
      const nextArg = argv[i + 1];
      
      // Check if it's a boolean flag or has a value
      if (!nextArg || nextArg.startsWith('-')) {
        result.options[flagName] = true;
      } else {
        result.options[flagName] = nextArg;
        i++;
      }
    } else if (arg.startsWith('-') && arg.length === 2) {
      // Short flag
      const shortFlag = arg.slice(1);
      const nextArg = argv[i + 1];
      
      // Find the corresponding long flag name from global flags and command-specific flags
      const globalFlag = GLOBAL_FLAGS.find(f => f.short === shortFlag);
      // Also check command-specific flags (e.g., -m for model in chat command)
      const commandShortFlags: Record<string, string> = {
        'm': 'model',
        's': 'stream',
        'a': 'agent',
        't': 'tools'
      };
      const flagName = globalFlag?.name || commandShortFlags[shortFlag] || shortFlag;
      
      if (!nextArg || nextArg.startsWith('-')) {
        result.options[flagName] = true;
      } else {
        result.options[flagName] = nextArg;
        i++;
      }
    } else if (!foundCommand) {
      // First non-flag argument is the command
      result.command = arg;
      foundCommand = true;
    } else if (!result.subcommand && COMMANDS[result.command]?.subcommands) {
      // Check if this is a subcommand
      const cmdSpec = COMMANDS[result.command];
      if (cmdSpec.subcommands && arg in cmdSpec.subcommands) {
        result.subcommand = arg;
      } else {
        result.args.push(arg);
      }
    } else {
      // Positional argument
      result.args.push(arg);
    }
    i++;
  }

  // Handle --json shorthand
  if (result.options.json) {
    result.options.output = 'json';
  }

  return result;
}

/**
 * Load and execute a command (lazy loading)
 */
async function executeCommand(parsed: ParsedArgs): Promise<void> {
  const { command, subcommand, args, options } = parsed;

  // Validate command exists
  if (!validateCommand(command)) {
    const isJson = options.output === 'json' || options.json;
    if (isJson) {
      outputJson(formatError(ERROR_CODES.INVALID_ARGS, `Unknown command: ${command}`));
    } else {
      console.error(`Error: Unknown command '${command}'`);
      console.error('Run "praisonai-ts help" for available commands');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  // Lazy load the command module
  try {
    const commandModule = await import(`./commands/${command}`);
    
    // Pass subcommand as first arg if present
    const commandArgs = subcommand ? [subcommand, ...args] : args;
    
    await commandModule.execute(commandArgs, options);
  } catch (error: unknown) {
    const cliError = normalizeError(error);
    const isJson = options.output === 'json' || options.json;
    
    if (isJson) {
      outputJson(formatError(cliError.code, cliError.message, cliError.details));
    } else {
      console.error(`Error: ${cliError.message}`);
      if (options.verbose && error instanceof Error && error.stack) {
        console.error(error.stack);
      }
    }
    
    process.exit(cliError.exitCode);
  }
}

/**
 * Main CLI entry point
 */
async function main(): Promise<void> {
  const argv = process.argv.slice(2);
  
  // Fast path for version
  if (argv.length === 0 || argv[0] === '--help' || argv[0] === '-h') {
    const helpModule = await import('./commands/help');
    await helpModule.execute([], {});
    return;
  }
  
  if (argv[0] === '--version') {
    const versionModule = await import('./commands/version');
    await versionModule.execute([], {});
    return;
  }

  const parsed = parseArgs(argv);
  await executeCommand(parsed);
}

// Export for programmatic use
export { parseArgs, executeCommand, CLI_SPEC_VERSION };

// Run CLI if executed directly
if (require.main === module) {
  main().catch((error) => {
    console.error('Fatal error:', error.message);
    process.exit(EXIT_CODES.RUNTIME_ERROR);
  });
}
