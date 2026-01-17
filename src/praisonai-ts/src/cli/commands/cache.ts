/**
 * Cache command - Caching management with full operations
 */

import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { EXIT_CODES } from '../spec/cli-spec';
import { ERROR_CODES } from '../output/errors';

export interface CacheOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
  ttl?: number;
}

// File-based cache for persistence
const CACHE_DIR = path.join(os.homedir(), '.praisonai', 'cache');

interface CacheEntry {
  value: string;
  createdAt: number;
  expiresAt?: number;
}

function ensureCacheDir(): void {
  if (!fs.existsSync(CACHE_DIR)) {
    fs.mkdirSync(CACHE_DIR, { recursive: true });
  }
}

function getCachePath(key: string): string {
  // Sanitize key for filesystem
  const safeKey = key.replace(/[^a-zA-Z0-9_-]/g, '_');
  return path.join(CACHE_DIR, `${safeKey}.json`);
}

export async function execute(args: string[], options: CacheOptions): Promise<void> {
  const action = args[0] || 'help';
  const actionArgs = args.slice(1);
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  try {
    switch (action) {
      case 'set':
        await setCache(actionArgs, options, outputFormat);
        break;
      case 'get':
        await getCache(actionArgs, outputFormat);
        break;
      case 'delete':
        await deleteCache(actionArgs, outputFormat);
        break;
      case 'clear':
        await clearCache(outputFormat);
        break;
      case 'list':
        await listCache(outputFormat);
        break;
      case 'stats':
        await showStats(outputFormat);
        break;
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

async function setCache(args: string[], options: CacheOptions, outputFormat: string): Promise<void> {
  const key = args[0];
  const value = args.slice(1).join(' ');

  if (!key || !value) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Usage: cache set <key> <value>'));
    } else {
      await pretty.error('Usage: cache set <key> <value>');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  ensureCacheDir();
  const entry: CacheEntry = {
    value,
    createdAt: Date.now(),
    expiresAt: options.ttl ? Date.now() + (options.ttl * 1000) : undefined
  };

  fs.writeFileSync(getCachePath(key), JSON.stringify(entry));

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ key, cached: true, ttl: options.ttl }));
  } else {
    await pretty.success(`Cached: ${key}`);
    if (options.ttl) {
      await pretty.dim(`TTL: ${options.ttl} seconds`);
    }
  }
}

async function getCache(args: string[], outputFormat: string): Promise<void> {
  const key = args[0];

  if (!key) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Usage: cache get <key>'));
    } else {
      await pretty.error('Usage: cache get <key>');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const cachePath = getCachePath(key);

  if (!fs.existsSync(cachePath)) {
    if (outputFormat === 'json') {
      outputJson(formatSuccess({ key, found: false }));
    } else {
      await pretty.info(`Cache miss: ${key}`);
    }
    return;
  }

  const entry: CacheEntry = JSON.parse(fs.readFileSync(cachePath, 'utf-8'));

  // Check expiration
  if (entry.expiresAt && Date.now() > entry.expiresAt) {
    fs.unlinkSync(cachePath);
    if (outputFormat === 'json') {
      outputJson(formatSuccess({ key, found: false, expired: true }));
    } else {
      await pretty.info(`Cache expired: ${key}`);
    }
    return;
  }

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ key, value: entry.value, found: true }));
  } else {
    await pretty.success(`Cache hit: ${key}`);
    await pretty.plain(entry.value);
  }
}

async function deleteCache(args: string[], outputFormat: string): Promise<void> {
  const key = args[0];

  if (!key) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Usage: cache delete <key>'));
    } else {
      await pretty.error('Usage: cache delete <key>');
    }
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const cachePath = getCachePath(key);

  if (fs.existsSync(cachePath)) {
    fs.unlinkSync(cachePath);
    if (outputFormat === 'json') {
      outputJson(formatSuccess({ key, deleted: true }));
    } else {
      await pretty.success(`Deleted: ${key}`);
    }
  } else {
    if (outputFormat === 'json') {
      outputJson(formatSuccess({ key, deleted: false, reason: 'not found' }));
    } else {
      await pretty.info(`Not found: ${key}`);
    }
  }
}

async function clearCache(outputFormat: string): Promise<void> {
  ensureCacheDir();
  const files = fs.readdirSync(CACHE_DIR).filter(f => f.endsWith('.json'));

  for (const file of files) {
    fs.unlinkSync(path.join(CACHE_DIR, file));
  }

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ cleared: true, count: files.length }));
  } else {
    await pretty.success(`Cleared ${files.length} cache entries`);
  }
}

async function listCache(outputFormat: string): Promise<void> {
  ensureCacheDir();
  const files = fs.readdirSync(CACHE_DIR).filter(f => f.endsWith('.json'));

  const entries = files.map(file => {
    const key = file.replace('.json', '');
    const entry: CacheEntry = JSON.parse(fs.readFileSync(path.join(CACHE_DIR, file), 'utf-8'));
    return {
      key,
      createdAt: entry.createdAt,
      expiresAt: entry.expiresAt,
      size: entry.value.length
    };
  });

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ entries, count: entries.length }));
  } else {
    await pretty.heading('Cache Entries');
    if (entries.length === 0) {
      await pretty.info('No cached entries');
    } else {
      for (const e of entries) {
        await pretty.plain(`  • ${e.key} (${e.size} chars)`);
        await pretty.dim(`    Created: ${new Date(e.createdAt).toISOString()}`);
      }
    }
    await pretty.newline();
    await pretty.info(`Total: ${entries.length} entries`);
  }
}

async function showStats(outputFormat: string): Promise<void> {
  ensureCacheDir();
  const files = fs.readdirSync(CACHE_DIR).filter(f => f.endsWith('.json'));

  let totalSize = 0;
  let expired = 0;

  for (const file of files) {
    const entry: CacheEntry = JSON.parse(fs.readFileSync(path.join(CACHE_DIR, file), 'utf-8'));
    totalSize += entry.value.length;
    if (entry.expiresAt && Date.now() > entry.expiresAt) {
      expired++;
    }
  }

  const stats = {
    entries: files.length,
    totalSize,
    expired,
    cacheDir: CACHE_DIR
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(stats));
  } else {
    await pretty.heading('Cache Statistics');
    await pretty.plain(`  Entries: ${stats.entries}`);
    await pretty.plain(`  Total Size: ${stats.totalSize} characters`);
    await pretty.plain(`  Expired: ${stats.expired}`);
    await pretty.dim(`  Location: ${stats.cacheDir}`);
  }
}

async function showInfo(outputFormat: string): Promise<void> {
  const info = {
    feature: 'Cache',
    description: 'File-based caching for LLM responses',
    location: CACHE_DIR,
    capabilities: ['Persistent storage', 'TTL expiration', 'Key-value pairs']
  };

  if (outputFormat === 'json') {
    outputJson(formatSuccess(info));
  } else {
    await pretty.heading('Cache');
    await pretty.plain(info.description);
    await pretty.dim(`Location: ${info.location}`);
  }
}

async function listProviders(outputFormat: string): Promise<void> {
  const providers = [
    { name: 'file', description: 'File-based persistent cache', available: true }
  ];

  if (outputFormat === 'json') {
    outputJson(formatSuccess({ providers }));
  } else {
    await pretty.heading('Cache Providers');
    for (const p of providers) {
      await pretty.plain(`  ✓ ${p.name.padEnd(15)} ${p.description}`);
    }
  }
}

async function showHelp(outputFormat: string): Promise<void> {
  const help = {
    command: 'cache',
    description: 'File-based caching for persistence',
    subcommands: [
      { name: 'set <key> <value>', description: 'Cache a value' },
      { name: 'get <key>', description: 'Get cached value' },
      { name: 'delete <key>', description: 'Delete cached entry' },
      { name: 'list', description: 'List all cached entries' },
      { name: 'stats', description: 'Show cache statistics' },
      { name: 'clear', description: 'Clear all cache entries' },
      { name: 'help', description: 'Show this help' }
    ],
    flags: [
      { name: '--ttl <seconds>', description: 'Time-to-live for cache entry' }
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
      await pretty.plain(`  ${cmd.name.padEnd(25)} ${cmd.description}`);
    }
    await pretty.newline();
    await pretty.plain('Flags:');
    for (const flag of help.flags) {
      await pretty.plain(`  ${flag.name.padEnd(20)} ${flag.description}`);
    }
    await pretty.newline();
    await pretty.dim('Examples:');
    await pretty.dim('  praisonai-ts cache set mykey "Hello World"');
    await pretty.dim('  praisonai-ts cache get mykey');
    await pretty.dim('  praisonai-ts cache list');
  }
}
