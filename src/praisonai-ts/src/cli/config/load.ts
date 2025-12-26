/**
 * Config file loading
 */

import * as fs from 'fs';
import * as path from 'path';
import { CONFIG_FILES } from '../spec/cli-spec';
import { FullConfig, validateConfig, DEFAULT_CONFIG } from './schema';

export interface LoadConfigOptions {
  configPath?: string;
  cwd?: string;
}

/**
 * Find config file in directory hierarchy
 */
function findConfigFile(startDir: string): string | null {
  let currentDir = startDir;
  
  while (true) {
    for (const filename of CONFIG_FILES) {
      const filePath = path.join(currentDir, filename);
      if (fs.existsSync(filePath)) {
        return filePath;
      }
    }
    
    const parentDir = path.dirname(currentDir);
    if (parentDir === currentDir) {
      break; // Reached root
    }
    currentDir = parentDir;
  }
  
  return null;
}

/**
 * Find user config file
 */
function findUserConfigFile(): string | null {
  const homeDir = process.env.HOME || process.env.USERPROFILE;
  if (!homeDir) return null;
  
  for (const filename of CONFIG_FILES) {
    const filePath = path.join(homeDir, filename);
    if (fs.existsSync(filePath)) {
      return filePath;
    }
  }
  
  return null;
}

/**
 * Parse config file content
 */
function parseConfigFile(filePath: string): unknown {
  const content = fs.readFileSync(filePath, 'utf-8');
  const ext = path.extname(filePath).toLowerCase();
  
  if (ext === '.json') {
    return JSON.parse(content);
  }
  
  if (ext === '.yaml' || ext === '.yml') {
    // Simple YAML parsing for basic config
    // For complex YAML, we'd need a proper parser
    return parseSimpleYaml(content);
  }
  
  throw new Error(`Unsupported config file format: ${ext}`);
}

/**
 * Simple YAML parser for basic key-value configs
 * Handles: strings, booleans, numbers, simple objects
 */
function parseSimpleYaml(content: string): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  const lines = content.split('\n');
  let currentObject: Record<string, unknown> | null = null;
  let currentKey: string | null = null;
  let baseIndent = 0;
  
  for (const line of lines) {
    // Skip empty lines and comments
    if (!line.trim() || line.trim().startsWith('#')) {
      continue;
    }
    
    const indent = line.search(/\S/);
    const trimmed = line.trim();
    
    // Check for key: value pattern
    const colonIndex = trimmed.indexOf(':');
    if (colonIndex === -1) continue;
    
    const key = trimmed.slice(0, colonIndex).trim();
    const value = trimmed.slice(colonIndex + 1).trim();
    
    if (indent === 0) {
      // Top-level key
      if (value === '' || value === '{}') {
        // Start of nested object
        currentObject = {};
        currentKey = key;
        baseIndent = indent;
        result[key] = currentObject;
      } else {
        result[key] = parseYamlValue(value);
        currentObject = null;
        currentKey = null;
      }
    } else if (currentObject !== null && indent > baseIndent) {
      // Nested key
      if (value === '' || value === '{}') {
        // Nested object within nested object
        const nestedObj: Record<string, unknown> = {};
        currentObject[key] = nestedObj;
        // For simplicity, we only support one level of nesting in profiles
      } else {
        currentObject[key] = parseYamlValue(value);
      }
    }
  }
  
  return result;
}

function parseYamlValue(value: string): string | number | boolean {
  // Remove quotes
  if ((value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))) {
    return value.slice(1, -1);
  }
  
  // Boolean
  if (value === 'true') return true;
  if (value === 'false') return false;
  
  // Number
  const num = Number(value);
  if (!isNaN(num) && value !== '') return num;
  
  return value;
}

/**
 * Load config from file
 */
export function loadConfigFile(filePath: string): FullConfig {
  try {
    const parsed = parseConfigFile(filePath);
    if (!validateConfig(parsed)) {
      throw new Error('Invalid config format');
    }
    return parsed;
  } catch (error) {
    throw new Error(`Failed to load config from ${filePath}: ${error instanceof Error ? error.message : String(error)}`);
  }
}

/**
 * Load config with resolution order:
 * 1. Explicit config path
 * 2. Project config (current dir and parents)
 * 3. User config (~/.praisonai.yaml)
 * 4. Defaults
 */
export function loadConfig(options: LoadConfigOptions = {}): FullConfig {
  const configs: Partial<FullConfig>[] = [DEFAULT_CONFIG];
  
  // User config
  const userConfigPath = findUserConfigFile();
  if (userConfigPath) {
    try {
      configs.push(loadConfigFile(userConfigPath));
    } catch {
      // Ignore user config errors
    }
  }
  
  // Project config
  const cwd = options.cwd || process.cwd();
  const projectConfigPath = findConfigFile(cwd);
  if (projectConfigPath) {
    try {
      configs.push(loadConfigFile(projectConfigPath));
    } catch {
      // Ignore project config errors
    }
  }
  
  // Explicit config path
  if (options.configPath) {
    configs.push(loadConfigFile(options.configPath));
  }
  
  // Merge all configs
  const result: FullConfig = { ...DEFAULT_CONFIG };
  for (const config of configs) {
    if (config.model !== undefined) result.model = config.model;
    if (config.verbose !== undefined) result.verbose = config.verbose;
    if (config.stream !== undefined) result.stream = config.stream;
    if (config.profiles !== undefined) {
      result.profiles = { ...result.profiles, ...config.profiles };
    }
  }
  
  return result;
}
