/**
 * Cache command - Caching management
 */

import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface CacheOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
}

export async function execute(args: string[], options: CacheOptions): Promise<void> {
  const action = args[0] || 'help';
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    switch (action) {
      case 'info':
        await showInfo(outputFormat);
        break;
      case 'providers':
        await listProviders(outputFormat);
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
    feature: 'Cache',
    description: 'Caching system for LLM responses and computations',
    providers: [
      { name: 'MemoryCache', description: 'In-memory cache (default)' },
      { name: 'FileCache', description: 'File-based persistent cache' }
    ],
    capabilities: [
      'Cache LLM responses',
      'Reduce API costs',
      'Improve response times',
      'TTL-based expiration',
      'Configurable cache keys'
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(info));
  } else {
    await pretty.heading('Cache');
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
    { name: 'memory', description: 'In-memory cache', available: true },
    { name: 'file', description: 'File-based cache', available: true }
  ];

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ providers }));
  } else {
    await pretty.heading('Cache Providers');
    for (const p of providers) {
      const status = p.available ? '✓' : '✗';
      await pretty.plain(`  ${status} ${p.name.padEnd(15)} ${p.description}`);
    }
  }
}

async function showHelp(outputFormat: string): Promise<void> {
  const help = {
    command: 'cache',
    description: 'Caching management for LLM responses',
    subcommands: [
      { name: 'info', description: 'Show cache feature information' },
      { name: 'providers', description: 'List available cache providers' },
      { name: 'help', description: 'Show this help' }
    ]
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(help));
  } else {
    await pretty.heading('Cache Command');
    await pretty.plain(help.description);
    await pretty.newline();
    await pretty.plain('Subcommands:');
    for (const cmd of help.subcommands) {
      await pretty.plain(`  ${cmd.name.padEnd(20)} ${cmd.description}`);
    }
  }
}
