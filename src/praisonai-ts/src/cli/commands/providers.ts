/**
 * Providers command - List and manage LLM providers
 * 
 * Supports:
 * - list: List all registered providers
 * - register: Register a custom provider (programmatic only)
 * - info: Show provider details
 */

import { 
  getAvailableProviders, 
  listProviders, 
  hasProvider,
  getDefaultRegistry,
  isProviderAvailable 
} from '../../llm/providers';
import { hasApiKey } from '../runtime/env';
import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { ERROR_CODES } from '../output/errors';

export interface ProvidersOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
}

interface ProviderInfo {
  name: string;
  registered: boolean;
  available: boolean;
  hasApiKey: boolean;
  isBuiltin: boolean;
  models?: string[];
}

const BUILTIN_PROVIDERS = ['openai', 'anthropic', 'google', 'gemini', 'oai', 'claude'];

const PROVIDER_MODELS: Record<string, string[]> = {
  openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-4', 'gpt-3.5-turbo'],
  anthropic: ['claude-sonnet-4-20250514', 'claude-3-5-sonnet-20241022', 'claude-3-opus-20240229', 'claude-3-haiku-20240307'],
  google: ['gemini-2.0-flash', 'gemini-1.5-pro', 'gemini-1.5-flash']
};

export async function execute(args: string[], options: ProvidersOptions): Promise<void> {
  const subcommand = args[0] || 'list';
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  switch (subcommand) {
    case 'list':
      await listProvidersCommand(options, outputFormat);
      break;
    case 'info':
      await providerInfoCommand(args[1], options, outputFormat);
      break;
    default:
      await listProvidersCommand(options, outputFormat);
  }
}

async function listProvidersCommand(options: ProvidersOptions, outputFormat: string): Promise<void> {
  const registry = getDefaultRegistry();
  const registeredProviders = registry.list();
  
  const providers: ProviderInfo[] = registeredProviders.map(name => {
    const isBuiltin = BUILTIN_PROVIDERS.includes(name);
    return {
      name,
      registered: true,
      available: isProviderAvailable(name),
      hasApiKey: hasApiKey(name),
      isBuiltin,
      models: PROVIDER_MODELS[name]
    };
  });

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      providers: providers.map(p => ({
        name: p.name,
        registered: p.registered,
        available: p.available,
        has_api_key: p.hasApiKey,
        is_builtin: p.isBuiltin,
        models: options.verbose ? p.models : undefined
      })),
      total: providers.length,
      builtin_count: providers.filter(p => p.isBuiltin).length,
      custom_count: providers.filter(p => !p.isBuiltin).length
    }));
  } else {
    await pretty.heading('Registered LLM Providers');
    
    // Built-in providers
    const builtinProviders = providers.filter(p => p.isBuiltin);
    if (builtinProviders.length > 0) {
      await pretty.plain('\n  Built-in:');
      for (const provider of builtinProviders) {
        const status = provider.available ? '✅' : '❌';
        const keyStatus = provider.hasApiKey ? '🔑' : '⚠️ No API key';
        await pretty.plain(`    ${status} ${provider.name} ${keyStatus}`);
        
        if (options.verbose && provider.models) {
          for (const model of provider.models) {
            await pretty.dim(`        - ${model}`);
          }
        }
      }
    }
    
    // Custom providers
    const customProviders = providers.filter(p => !p.isBuiltin);
    if (customProviders.length > 0) {
      await pretty.plain('\n  Custom:');
      for (const provider of customProviders) {
        const status = provider.available ? '✅' : '❌';
        await pretty.plain(`    ${status} ${provider.name}`);
      }
    }
    
    await pretty.newline();
    await pretty.info('Register custom providers with registerProvider():');
    await pretty.dim('  import { registerProvider } from "praisonai";');
    await pretty.dim('  registerProvider("cloudflare", CloudflareProvider);');
    await pretty.newline();
    await pretty.info('Set API keys via environment variables:');
    await pretty.dim('  OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY');
  }
}

async function providerInfoCommand(name: string | undefined, options: ProvidersOptions, outputFormat: string): Promise<void> {
  if (!name) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Provider name required'));
    } else {
      await pretty.error('Provider name required. Usage: providers info <name>');
    }
    return;
  }

  const registry = getDefaultRegistry();
  const isRegistered = registry.has(name);
  const isBuiltin = BUILTIN_PROVIDERS.includes(name.toLowerCase());
  const available = isProviderAvailable(name);
  const models = PROVIDER_MODELS[name.toLowerCase()];

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      name,
      registered: isRegistered,
      available,
      is_builtin: isBuiltin,
      has_api_key: hasApiKey(name),
      models: models || []
    }));
  } else {
    await pretty.heading(`Provider: ${name}`);
    await pretty.plain(`  Registered: ${isRegistered ? '✅ Yes' : '❌ No'}`);
    await pretty.plain(`  Available: ${available ? '✅ Yes' : '❌ No'}`);
    await pretty.plain(`  Type: ${isBuiltin ? 'Built-in' : 'Custom'}`);
    await pretty.plain(`  API Key: ${hasApiKey(name) ? '🔑 Set' : '⚠️ Not set'}`);
    
    if (models && models.length > 0) {
      await pretty.plain('\n  Models:');
      for (const model of models) {
        await pretty.dim(`    - ${model}`);
      }
    }
  }
}
