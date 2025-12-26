/**
 * Config schema definitions
 */

import { ConfigSchema } from '../spec/cli-spec';

export interface ProfileConfig {
  model?: string;
  verbose?: boolean;
  stream?: boolean;
}

export interface FullConfig extends ConfigSchema {
  profiles?: Record<string, ProfileConfig>;
}

export const DEFAULT_CONFIG: FullConfig = {
  model: 'openai/gpt-4o-mini',
  verbose: false,
  stream: false,
  profiles: {}
};

export function validateConfig(config: unknown): config is FullConfig {
  if (typeof config !== 'object' || config === null) {
    return false;
  }

  const c = config as Record<string, unknown>;

  if (c.model !== undefined && typeof c.model !== 'string') {
    return false;
  }

  if (c.verbose !== undefined && typeof c.verbose !== 'boolean') {
    return false;
  }

  if (c.stream !== undefined && typeof c.stream !== 'boolean') {
    return false;
  }

  if (c.profiles !== undefined) {
    if (typeof c.profiles !== 'object' || c.profiles === null) {
      return false;
    }
    for (const profile of Object.values(c.profiles as Record<string, unknown>)) {
      if (typeof profile !== 'object' || profile === null) {
        return false;
      }
      const p = profile as Record<string, unknown>;
      if (p.model !== undefined && typeof p.model !== 'string') {
        return false;
      }
      if (p.verbose !== undefined && typeof p.verbose !== 'boolean') {
        return false;
      }
      if (p.stream !== undefined && typeof p.stream !== 'boolean') {
        return false;
      }
    }
  }

  return true;
}

export function mergeConfigs(...configs: Partial<FullConfig>[]): FullConfig {
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
