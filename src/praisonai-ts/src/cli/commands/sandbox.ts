/**
 * CLI command: sandbox
 * Filters a command, then runs it on the host. Not isolation (see SECURITY.md).
 */

import { SandboxExecutor, createSandboxExecutor, CommandValidator, type SandboxMode } from '../features/sandbox-executor';
import { printPlainHelp } from '../output/help';

export async function execute(args: string[], options: Record<string, unknown>): Promise<void> {
  const subcommand = args[0] || 'help';
  const isJson = Boolean(options.output === 'json' || options.json);

  switch (subcommand) {
    case 'exec':
      await handleExec(args.slice(1), options, isJson);
      break;
    case 'check':
      await handleCheck(args.slice(1), isJson);
      break;
    case 'mode':
      await handleMode(args.slice(1), isJson);
      break;
    case 'help':
    default:
      showHelp(isJson);
  }
}

async function handleExec(args: string[], options: Record<string, unknown>, isJson: boolean): Promise<void> {
  const command = args.join(' ');
  if (!command) {
    console.error('Error: Command is required');
    process.exit(1);
  }

  const mode = (options.mode as SandboxMode) || 'basic';
  const timeout = (options.timeout as number) || 30000;
  
  const executor = createSandboxExecutor({ mode, timeout });
  const result = await executor.execute(command);

  if (isJson) {
    console.log(JSON.stringify(result, null, 2));
  } else {
    if (result.success) {
      console.log('✓ Command executed successfully');
      console.log(`Duration: ${result.duration}ms`);
      if (result.stdout) {
        console.log('\nOutput:');
        console.log(result.stdout);
      }
    } else {
      console.error('✗ Command failed');
      if (result.stderr) console.error(result.stderr);
    }
  }

  if (!result.success) process.exit(result.exitCode || 1);
}

async function handleCheck(args: string[], isJson: boolean): Promise<void> {
  const command = args.join(' ');
  if (!command) {
    console.error('Error: Command is required');
    process.exit(1);
  }

  const validator = new CommandValidator();
  const result = validator.validate(command);

  if (isJson) {
    console.log(JSON.stringify({ command, ...result }, null, 2));
  } else {
    if (result.valid) {
      console.log(`✓ Command is allowed: ${command}`);
    } else {
      console.log(`✗ Command blocked: ${command}`);
      console.log(`  Reason: ${result.reason}`);
    }
  }
}

async function handleMode(args: string[], isJson: boolean): Promise<void> {
  const modes: Record<SandboxMode, string> = {
    disabled: 'No execution allowed',
    basic: 'Refuses deny-listed commands and patterns; runs on the host',
    strict: 'As basic, no shell, minimal environment; runs on the host',
    'network-isolated': 'As basic, refuses network tools, unsets proxies; runs on the host with network access'
  };

  if (isJson) {
    console.log(JSON.stringify({ success: true, modes }, null, 2));
  } else {
    console.log('Sandbox Modes:\n');
    for (const [mode, desc] of Object.entries(modes)) {
      console.log(`  ${mode.padEnd(18)} ${desc}`);
    }
  }
}

function showHelp(isJson: boolean): void {
  const help = {
    command: 'sandbox',
    description: 'Filter a command, then run it on the host (not isolation; see SECURITY.md)',
    subcommands: {
      exec: 'Filter a command, then run it on the host',
      check: 'Check if a command would be allowed',
      mode: 'List available sandbox modes'
    },
    flags: {
      '--mode': 'Filter mode (disabled, basic, strict, network-isolated)',
      '--timeout': 'Execution timeout in ms (default: 30000)',
      '--json': 'Output in JSON format'
    },
    examples: [
      'praisonai-ts sandbox exec "ls -la"',
      'praisonai-ts sandbox exec "npm install" --mode strict',
      'praisonai-ts sandbox check "rm -rf /"',
      'praisonai-ts sandbox mode'
    ]
  };

  printPlainHelp(isJson, help, 'Sandbox - command filter (runs on the host)', [
    { label: 'Subcommands:', entries: help.subcommands },
    { label: 'Flags:', entries: help.flags },
    { label: 'Examples:', items: help.examples }
  ]);
}
