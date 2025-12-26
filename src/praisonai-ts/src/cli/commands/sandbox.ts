/**
 * CLI command: sandbox
 * Safe command execution with restrictions
 */

import { SandboxExecutor, createSandboxExecutor, CommandValidator, type SandboxMode } from '../features/sandbox-executor';

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
    basic: 'Basic validation, blocks dangerous patterns',
    strict: 'Minimal environment, restricted PATH',
    'network-isolated': 'No network access (proxy blocked)'
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
    description: 'Safe command execution with restrictions',
    subcommands: {
      exec: 'Execute a command in sandbox',
      check: 'Check if a command would be allowed',
      mode: 'List available sandbox modes'
    },
    flags: {
      '--mode': 'Sandbox mode (disabled, basic, strict, network-isolated)',
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

  if (isJson) {
    console.log(JSON.stringify(help, null, 2));
  } else {
    console.log('Sandbox - Safe command execution\n');
    console.log('Subcommands:');
    for (const [cmd, desc] of Object.entries(help.subcommands)) {
      console.log(`  ${cmd.padEnd(12)} ${desc}`);
    }
    console.log('\nFlags:');
    for (const [flag, desc] of Object.entries(help.flags)) {
      console.log(`  ${flag.padEnd(12)} ${desc}`);
    }
    console.log('\nExamples:');
    for (const ex of help.examples) {
      console.log(`  ${ex}`);
    }
  }
}
