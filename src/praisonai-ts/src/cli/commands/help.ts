/**
 * Help command - Show help information
 */

import { COMMANDS, GLOBAL_FLAGS, CLI_SPEC_VERSION, getCommandSpec } from '../spec/cli-spec';
import { outputJson, formatSuccess } from '../output/json';
import * as pretty from '../output/pretty';

export interface HelpOptions {
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
}

export async function execute(args: string[], options: HelpOptions): Promise<void> {
  const command = args[0];
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  if (command) {
    await showCommandHelp(command, outputFormat);
  } else {
    await showGeneralHelp(outputFormat);
  }
}

async function showGeneralHelp(outputFormat: string): Promise<void> {
  const commands = Object.entries(COMMANDS).map(([name, spec]) => ({
    name,
    description: spec.description
  }));

  const flags = GLOBAL_FLAGS.map(f => ({
    name: f.short ? `-${f.short}, --${f.name}` : `--${f.name}`,
    description: f.description,
    default: f.default
  }));

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      cli_spec_version: CLI_SPEC_VERSION,
      commands,
      global_flags: flags
    }));
  } else {
    await pretty.plain(`
PraisonAI TypeScript CLI v${CLI_SPEC_VERSION}

Usage:
  praisonai-ts <command> [options]

Commands:`);

    for (const cmd of commands) {
      await pretty.plain(`  ${cmd.name.padEnd(12)} ${cmd.description}`);
    }

    await pretty.plain(`
Global Options:`);

    for (const flag of flags) {
      const defaultStr = flag.default !== undefined ? ` (default: ${flag.default})` : '';
      await pretty.plain(`  ${flag.name.padEnd(20)} ${flag.description}${defaultStr}`);
    }

    await pretty.plain(`
Environment Variables:
  OPENAI_API_KEY       OpenAI API key
  ANTHROPIC_API_KEY    Anthropic API key
  GOOGLE_API_KEY       Google API key
  PRAISONAI_MODEL      Default model

Examples:
  praisonai-ts chat "Hello, how are you?"
  praisonai-ts chat "Write a poem" --stream
  praisonai-ts run "Analyze this data" --agent my-agent.yaml
  praisonai-ts providers
  praisonai-ts help chat
`);
  }
}

async function showCommandHelp(command: string, outputFormat: string): Promise<void> {
  const spec = getCommandSpec(command);

  if (!spec) {
    await pretty.error(`Unknown command: ${command}`);
    await pretty.info('Run "praisonai-ts help" to see available commands');
    return;
  }

  const args = spec.args || [];
  const flags = [...GLOBAL_FLAGS, ...(spec.flags || [])];
  const subcommands = spec.subcommands ? Object.entries(spec.subcommands) : [];

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      command,
      description: spec.description,
      args: args.map(a => ({
        name: a.name,
        type: a.type,
        required: a.required,
        description: a.description
      })),
      flags: flags.map(f => ({
        name: f.name,
        short: f.short,
        type: f.type,
        default: f.default,
        description: f.description
      })),
      subcommands: subcommands.map(([name, sub]) => ({
        name,
        description: sub.description
      }))
    }));
  } else {
    await pretty.plain(`
Command: ${command}
${spec.description}

Usage:
  praisonai-ts ${command}${args.length ? ' ' + args.map(a => a.required ? `<${a.name}>` : `[${a.name}]`).join(' ') : ''} [options]`);

    if (args.length > 0) {
      await pretty.plain(`
Arguments:`);
      for (const arg of args) {
        const reqStr = arg.required ? ' (required)' : '';
        await pretty.plain(`  ${arg.name.padEnd(15)} ${arg.description || arg.type}${reqStr}`);
      }
    }

    if (subcommands.length > 0) {
      await pretty.plain(`
Subcommands:`);
      for (const [name, sub] of subcommands) {
        await pretty.plain(`  ${name.padEnd(15)} ${sub.description}`);
      }
    }

    await pretty.plain(`
Options:`);
    for (const flag of flags) {
      const shortStr = flag.short ? `-${flag.short}, ` : '    ';
      const defaultStr = flag.default !== undefined ? ` (default: ${flag.default})` : '';
      await pretty.plain(`  ${shortStr}--${flag.name.padEnd(14)} ${flag.description || ''}${defaultStr}`);
    }

    await pretty.plain('');
  }
}
