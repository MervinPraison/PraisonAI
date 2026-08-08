/**
 * Pretty output formatting for CLI
 * Uses optional dependencies (chalk, boxen, ora) with fallbacks
 */

import { tryLoadOptional } from '../runtime/lazy';

type ChalkInstance = {
  green: (s: string) => string;
  red: (s: string) => string;
  yellow: (s: string) => string;
  blue: (s: string) => string;
  cyan: (s: string) => string;
  gray: (s: string) => string;
  bold: (s: string) => string;
};

let chalkInstance: ChalkInstance | null = null;
let chalkLoaded = false;

async function getChalk(): Promise<ChalkInstance | null> {
  if (chalkLoaded) return chalkInstance;
  chalkLoaded = true;
  
  try {
    const chalk = await tryLoadOptional<{ default: ChalkInstance }>('chalk');
    chalkInstance = chalk?.default || null;
  } catch {
    chalkInstance = null;
  }
  return chalkInstance;
}

// Fallback functions when chalk is not available
const noColor = (s: string) => s;

export async function success(message: string): Promise<void> {
  const chalk = await getChalk();
  const prefix = chalk ? chalk.green('✓') : '✓';
  console.log(`${prefix} ${message}`);
}

export async function error(message: string): Promise<void> {
  const chalk = await getChalk();
  const prefix = chalk ? chalk.red('✗') : '✗';
  console.error(`${prefix} ${message}`);
}

export async function warn(message: string): Promise<void> {
  const chalk = await getChalk();
  const prefix = chalk ? chalk.yellow('⚠') : '⚠';
  console.warn(`${prefix} ${message}`);
}

export async function info(message: string): Promise<void> {
  const chalk = await getChalk();
  const prefix = chalk ? chalk.blue('ℹ') : 'ℹ';
  console.log(`${prefix} ${message}`);
}

export async function heading(message: string): Promise<void> {
  const chalk = await getChalk();
  const text = chalk ? chalk.bold(message) : message;
  console.log(`\n${text}\n`);
}

export async function dim(message: string): Promise<void> {
  const chalk = await getChalk();
  const text = chalk ? chalk.gray(message) : message;
  console.log(text);
}

export async function highlight(message: string): Promise<void> {
  const chalk = await getChalk();
  const text = chalk ? chalk.cyan(message) : message;
  console.log(text);
}

export function plain(message: string): void {
  console.log(message);
}

export function newline(): void {
  console.log();
}

/**
 * Print a table (simple ASCII fallback)
 */
export function table(headers: string[], rows: string[][]): void {
  // Calculate column widths
  const widths = headers.map((h, i) => {
    const maxRowWidth = Math.max(...rows.map(r => (r[i] || '').length));
    return Math.max(h.length, maxRowWidth);
  });

  // Print header
  const headerLine = headers.map((h, i) => h.padEnd(widths[i])).join('  ');
  console.log(headerLine);
  console.log('-'.repeat(headerLine.length));

  // Print rows
  for (const row of rows) {
    const line = row.map((cell, i) => (cell || '').padEnd(widths[i])).join('  ');
    console.log(line);
  }
}

/**
 * Print a key-value list
 */
export async function keyValue(items: Record<string, string | number | boolean>): Promise<void> {
  const chalk = await getChalk();
  const maxKeyLen = Math.max(...Object.keys(items).map(k => k.length));
  
  for (const [key, value] of Object.entries(items)) {
    const keyStr = chalk ? chalk.cyan(key.padEnd(maxKeyLen)) : key.padEnd(maxKeyLen);
    console.log(`  ${keyStr}  ${value}`);
  }
}
