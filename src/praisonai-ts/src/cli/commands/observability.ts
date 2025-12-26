/**
 * Observability command - Monitoring and tracing
 */

import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface ObservabilityOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
}

export async function execute(args: string[], options: ObservabilityOptions): Promise<void> {
  const action = args[0] || 'help';
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    switch (action) {
      case 'providers':
        await listProviders(outputFormat);
        break;
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
    feature: 'Observability',
    description: 'Monitoring, tracing, and logging for agent operations',
    providers: [
      { name: 'ConsoleObservabilityProvider', description: 'Console-based logging' },
      { name: 'MemoryObservabilityProvider', description: 'In-memory trace storage' },
      { name: 'LangfuseObservabilityProvider', description: 'Langfuse integration' }
    ],
    capabilities: [
      'Trace agent executions',
      'Log LLM calls and responses',
      'Track tool invocations',
      'Measure performance metrics',
      'Export traces to external systems'
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(info));
  } else {
    await pretty.heading('Observability');
    await pretty.plain(info.description);
    await pretty.newline();
    await pretty.plain('Providers:');
    for (const p of info.providers) {
      await pretty.plain(`  • ${p.name}: ${p.description}`);
    }
    await pretty.newline();
    await pretty.plain('Capabilities:');
    for (const cap of info.capabilities) {
      await pretty.plain(`  • ${cap}`);
    }
  }
}

async function listProviders(outputFormat: string): Promise<void> {
  const providers = [
    { name: 'console', description: 'Console logging (default)', available: true },
    { name: 'memory', description: 'In-memory storage', available: true },
    { name: 'langfuse', description: 'Langfuse observability platform', available: true }
  ];

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ providers }));
  } else {
    await pretty.heading('Observability Providers');
    for (const p of providers) {
      const status = p.available ? '✓' : '✗';
      await pretty.plain(`  ${status} ${p.name.padEnd(15)} ${p.description}`);
    }
  }
}

async function showHelp(outputFormat: string): Promise<void> {
  const help = {
    command: 'observability',
    description: 'Monitoring and tracing for agent operations',
    subcommands: [
      { name: 'info', description: 'Show observability feature information' },
      { name: 'providers', description: 'List available observability providers' },
      { name: 'help', description: 'Show this help' }
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(help));
  } else {
    await pretty.heading('Observability Command');
    await pretty.plain(help.description);
    await pretty.newline();
    await pretty.plain('Subcommands:');
    for (const cmd of help.subcommands) {
      await pretty.plain(`  ${cmd.name.padEnd(20)} ${cmd.description}`);
    }
  }
}
