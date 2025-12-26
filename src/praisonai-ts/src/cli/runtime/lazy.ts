/**
 * Lazy loading utilities for CLI commands
 * Ensures startup time stays <100ms by only loading command code when invoked
 */

import { validateCommand } from '../spec/cli-spec';

export type CommandModule = {
  execute: (args: string[], options: Record<string, unknown>) => Promise<void>;
};

const commandCache = new Map<string, CommandModule>();

export async function loadCommand(command: string): Promise<CommandModule> {
  if (!validateCommand(command)) {
    throw new Error(`Unknown command: ${command}`);
  }

  // Check cache first
  if (commandCache.has(command)) {
    return commandCache.get(command)!;
  }

  // Lazy import the command module
  const module = await import(`../commands/${command}`);
  commandCache.set(command, module);
  return module;
}

export function clearCommandCache(): void {
  commandCache.clear();
}

/**
 * Lazy load optional dependencies
 * Returns undefined if not available
 */
export async function tryLoadOptional<T>(moduleName: string): Promise<T | undefined> {
  try {
    return await import(moduleName);
  } catch {
    return undefined;
  }
}

/**
 * Check if an optional dependency is available
 */
export async function hasOptionalDep(moduleName: string): Promise<boolean> {
  try {
    await import(moduleName);
    return true;
  } catch {
    return false;
  }
}
