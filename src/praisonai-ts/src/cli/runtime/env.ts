/**
 * Environment variable handling for CLI
 */

import { ENV_VARS } from '../spec/cli-spec';

export interface EnvConfig {
  model?: string;
  profile?: string;
  verbose?: boolean;
  configPath?: string;
}

export function loadEnvConfig(): EnvConfig {
  const config: EnvConfig = {};

  const model = process.env[ENV_VARS.PRAISONAI_MODEL];
  if (model) config.model = model;

  const profile = process.env[ENV_VARS.PRAISONAI_PROFILE];
  if (profile) config.profile = profile;

  const verbose = process.env[ENV_VARS.PRAISONAI_VERBOSE];
  if (verbose) config.verbose = verbose.toLowerCase() === 'true';

  const configPath = process.env[ENV_VARS.PRAISONAI_CONFIG];
  if (configPath) config.configPath = configPath;

  return config;
}

export function hasApiKey(provider: string): boolean {
  const normalizedProvider = provider.toLowerCase();
  switch (normalizedProvider) {
    case 'openai':
    case 'oai':
      return !!process.env[ENV_VARS.OPENAI_API_KEY];
    case 'anthropic':
    case 'claude':
      return !!process.env[ENV_VARS.ANTHROPIC_API_KEY];
    case 'google':
    case 'gemini':
      return !!process.env[ENV_VARS.GOOGLE_API_KEY];
    default:
      // For custom providers, check for provider-specific env var
      const envVarName = `${normalizedProvider.toUpperCase()}_API_KEY`;
      return !!process.env[envVarName];
  }
}

export function getApiKey(provider: 'openai' | 'anthropic' | 'google'): string | undefined {
  switch (provider) {
    case 'openai':
      return process.env[ENV_VARS.OPENAI_API_KEY];
    case 'anthropic':
      return process.env[ENV_VARS.ANTHROPIC_API_KEY];
    case 'google':
      return process.env[ENV_VARS.GOOGLE_API_KEY];
    default:
      return undefined;
  }
}
