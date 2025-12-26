/**
 * Config resolution with profiles and CLI overrides
 */

import { loadConfig } from './load';
import { loadEnvConfig } from '../runtime/env';
import { FullConfig, ProfileConfig, DEFAULT_CONFIG } from './schema';

export interface ResolvedConfig {
  model: string;
  verbose: boolean;
  stream: boolean;
}

export interface ResolveOptions {
  configPath?: string;
  profile?: string;
  model?: string;
  verbose?: boolean;
  stream?: boolean;
}

/**
 * Resolve final config with precedence:
 * 1. CLI flags (highest)
 * 2. Environment variables
 * 3. Profile settings
 * 4. Config file
 * 5. Defaults (lowest)
 */
export function resolveConfig(options: ResolveOptions = {}): ResolvedConfig {
  // Load base config from files
  const fileConfig = loadConfig({ configPath: options.configPath });
  
  // Load env config
  const envConfig = loadEnvConfig();
  
  // Get profile config if specified
  let profileConfig: ProfileConfig = {};
  const profileName = options.profile || envConfig.profile;
  if (profileName && fileConfig.profiles?.[profileName]) {
    profileConfig = fileConfig.profiles[profileName];
  }
  
  // Resolve with precedence
  const resolved: ResolvedConfig = {
    model: DEFAULT_CONFIG.model!,
    verbose: DEFAULT_CONFIG.verbose!,
    stream: DEFAULT_CONFIG.stream!
  };
  
  // Apply file config
  if (fileConfig.model !== undefined) resolved.model = fileConfig.model;
  if (fileConfig.verbose !== undefined) resolved.verbose = fileConfig.verbose;
  if (fileConfig.stream !== undefined) resolved.stream = fileConfig.stream;
  
  // Apply profile config
  if (profileConfig.model !== undefined) resolved.model = profileConfig.model;
  if (profileConfig.verbose !== undefined) resolved.verbose = profileConfig.verbose;
  if (profileConfig.stream !== undefined) resolved.stream = profileConfig.stream;
  
  // Apply env config
  if (envConfig.model !== undefined) resolved.model = envConfig.model;
  if (envConfig.verbose !== undefined) resolved.verbose = envConfig.verbose;
  
  // Apply CLI flags (highest precedence)
  if (options.model !== undefined) resolved.model = options.model;
  if (options.verbose !== undefined) resolved.verbose = options.verbose;
  if (options.stream !== undefined) resolved.stream = options.stream;
  
  return resolved;
}

/**
 * Get available profile names
 */
export function getAvailableProfiles(configPath?: string): string[] {
  const config = loadConfig({ configPath });
  return Object.keys(config.profiles || {});
}
