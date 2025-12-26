/**
 * Handoff command - Agent handoff management
 */

import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface HandoffOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
}

export async function execute(args: string[], options: HandoffOptions): Promise<void> {
  const action = args[0] || 'help';
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    switch (action) {
      case 'info':
        await showInfo(outputFormat);
        break;
      case 'help':
      default:
        await showHelp(outputFormat);
        break;
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

async function showInfo(outputFormat: string): Promise<void> {
  const info = {
    feature: 'Handoff',
    description: 'Agent handoff allows seamless transfer of conversation context between agents',
    capabilities: [
      'Transfer conversation to specialized agents',
      'Preserve context during handoff',
      'Filter handoffs based on conditions',
      'Chain multiple agent handoffs'
    ],
    sdkUsage: `
import { Handoff, handoff, handoffFilters } from 'praisonai';

// Create a handoff
const myHandoff = handoff({
  target: specialistAgent,
  condition: (ctx) => ctx.input.includes('technical'),
  onHandoff: (ctx) => console.log('Handing off...')
});

// Use with an agent
const agent = new Agent({
  handoffs: [myHandoff]
});
`
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(info));
  } else {
    await pretty.heading('Handoff Feature');
    await pretty.plain(info.description);
    await pretty.newline();
    await pretty.plain('Capabilities:');
    for (const cap of info.capabilities) {
      await pretty.plain(`  • ${cap}`);
    }
    await pretty.newline();
    await pretty.dim('Use the SDK for programmatic handoff configuration');
  }
}

async function showHelp(outputFormat: string): Promise<void> {
  const help = {
    command: 'handoff',
    description: 'Agent handoff management - transfer conversations between agents',
    subcommands: [
      { name: 'info', description: 'Show handoff feature information' },
      { name: 'help', description: 'Show this help' }
    ],
    note: 'Handoff is primarily a programmatic SDK feature. Use the SDK for full functionality.'
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(help));
  } else {
    await pretty.heading('Handoff Command');
    await pretty.plain(help.description);
    await pretty.newline();
    await pretty.plain('Subcommands:');
    for (const cmd of help.subcommands) {
      await pretty.plain(`  ${cmd.name.padEnd(20)} ${cmd.description}`);
    }
    await pretty.newline();
    await pretty.dim(help.note);
  }
}
