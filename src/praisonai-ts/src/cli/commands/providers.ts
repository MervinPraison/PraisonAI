/**
 * Providers command - List and manage LLM providers
 * 
 * Supports:
 * - list: List all registered providers (60+ AI SDK v6 providers)
 * - doctor: Check environment variables for selected provider
 * - test: Run a small test request to verify provider works
 * - info: Show provider details
 */

import { 
  getAvailableProviders, 
  listProviders, 
  hasProvider,
  getDefaultRegistry,
  isProviderAvailable 
} from '../../llm/providers';
import { 
  AISDK_PROVIDERS, 
  PROVIDER_ALIASES,
  COMMUNITY_PROVIDERS,
  type ProviderInfo as AISDKProviderInfo
} from '../../llm/providers/ai-sdk/types';
import { hasApiKey } from '../runtime/env';
import { outputJson, formatSuccess, formatError } from '../output/json';
import * as pretty from '../output/pretty';
import { ERROR_CODES } from '../output/errors';

export interface ProvidersOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
  provider?: string;
  model?: string;
}

interface ProviderInfo {
  name: string;
  registered: boolean;
  available: boolean;
  hasApiKey: boolean;
  isBuiltin: boolean;
  models?: string[];
  modalities?: {
    text: boolean;
    chat: boolean;
    embeddings: boolean;
    image: boolean;
    audio: boolean;
    speech: boolean;
    tools: boolean;
  };
  description?: string;
  envKey?: string;
  package?: string;
}

const BUILTIN_PROVIDERS = ['openai', 'anthropic', 'google', 'gemini', 'oai', 'claude'];

const PROVIDER_MODELS: Record<string, string[]> = {
  openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-4', 'gpt-3.5-turbo', 'gpt-5', 'gpt-5-mini'],
  anthropic: ['claude-sonnet-4-20250514', 'claude-3-5-sonnet-20241022', 'claude-3-opus-20240229', 'claude-3-haiku-20240307', 'claude-opus-4-5'],
  google: ['gemini-2.0-flash', 'gemini-1.5-pro', 'gemini-1.5-flash'],
  xai: ['grok-4', 'grok-3', 'grok-3-fast', 'grok-3-mini'],
  groq: ['llama-3.3-70b-versatile', 'mixtral-8x7b-32768', 'gemma2-9b-it'],
  mistral: ['mistral-large-latest', 'mistral-medium-latest', 'mistral-small-latest'],
  deepseek: ['deepseek-chat', 'deepseek-reasoner'],
  cerebras: ['llama3.1-8b', 'llama3.3-70b'],
};

export async function execute(args: string[], options: ProvidersOptions): Promise<void> {
  const subcommand = args[0] || 'list';
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');

  switch (subcommand) {
    case 'list':
      await listProvidersCommand(options, outputFormat);
      break;
    case 'doctor':
      await doctorCommand(args[1] || options.provider, options, outputFormat);
      break;
    case 'test':
      await testCommand(args[1] || options.provider, args[2] || options.model, options, outputFormat);
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

/**
 * Doctor command - Check environment variables for a provider
 */
async function doctorCommand(providerName: string | undefined, options: ProvidersOptions, outputFormat: string): Promise<void> {
  // Get all AI SDK providers
  const allProviders = Object.entries(AISDK_PROVIDERS);
  
  if (providerName) {
    // Check specific provider
    const resolved = PROVIDER_ALIASES[providerName.toLowerCase()] || providerName.toLowerCase();
    const providerInfo = AISDK_PROVIDERS[resolved];
    
    if (!providerInfo) {
      if (outputFormat === 'json') {
        outputJson(formatError(ERROR_CODES.INVALID_ARGS, `Unknown provider: ${providerName}`));
      } else {
        await pretty.error(`Unknown provider: ${providerName}`);
        await pretty.info(`Available providers: ${Object.keys(AISDK_PROVIDERS).slice(0, 10).join(', ')}...`);
      }
      return;
    }
    
    const hasKey = !!process.env[providerInfo.envKey];
    const keyValue = process.env[providerInfo.envKey];
    const maskedKey = keyValue ? `${keyValue.slice(0, 4)}...${keyValue.slice(-4)}` : 'not set';
    
    if (outputFormat === 'json') {
      outputJson(formatSuccess({
        provider: resolved,
        env_key: providerInfo.envKey,
        has_key: hasKey,
        key_preview: hasKey ? maskedKey : null,
        package: providerInfo.package,
        description: providerInfo.description,
        modalities: providerInfo.modalities,
        status: hasKey ? 'ready' : 'missing_key'
      }));
    } else {
      await pretty.heading(`Provider Doctor: ${resolved}`);
      await pretty.plain(`  Package: ${providerInfo.package}`);
      await pretty.plain(`  Description: ${providerInfo.description || 'N/A'}`);
      await pretty.plain(`  Environment Variable: ${providerInfo.envKey}`);
      await pretty.plain(`  Status: ${hasKey ? '✅ Ready' : '❌ Missing API Key'}`);
      if (hasKey) {
        await pretty.dim(`  Key Preview: ${maskedKey}`);
      } else {
        await pretty.newline();
        await pretty.info(`Set the API key with:`);
        await pretty.dim(`  export ${providerInfo.envKey}=your-api-key`);
      }
      await pretty.newline();
      await pretty.plain('  Modalities:');
      const m = providerInfo.modalities;
      await pretty.plain(`    Text/Chat: ${m.chat ? '✅' : '❌'}  Embeddings: ${m.embeddings ? '✅' : '❌'}  Image: ${m.image ? '✅' : '❌'}`);
      await pretty.plain(`    Audio: ${m.audio ? '✅' : '❌'}  Speech: ${m.speech ? '✅' : '❌'}  Tools: ${m.tools ? '✅' : '❌'}`);
    }
  } else {
    // Check all providers
    const results = allProviders.map(([name, info]) => ({
      name,
      envKey: info.envKey,
      hasKey: !!process.env[info.envKey],
      description: info.description
    }));
    
    const ready = results.filter(r => r.hasKey);
    const missing = results.filter(r => !r.hasKey);
    
    if (outputFormat === 'json') {
      outputJson(formatSuccess({
        total: results.length,
        ready: ready.length,
        missing: missing.length,
        providers: results
      }));
    } else {
      await pretty.heading('Provider Environment Check');
      await pretty.plain(`\n  Total Providers: ${results.length}`);
      await pretty.plain(`  Ready: ${ready.length} ✅`);
      await pretty.plain(`  Missing Keys: ${missing.length} ⚠️`);
      
      if (ready.length > 0) {
        await pretty.plain('\n  Ready Providers:');
        for (const p of ready.slice(0, 10)) {
          await pretty.plain(`    ✅ ${p.name}`);
        }
        if (ready.length > 10) {
          await pretty.dim(`    ... and ${ready.length - 10} more`);
        }
      }
      
      await pretty.newline();
      await pretty.info('Run "providers doctor <name>" for detailed info on a specific provider');
    }
  }
}

/**
 * Test command - Run a small test request to verify provider works
 */
async function testCommand(providerName: string | undefined, modelName: string | undefined, options: ProvidersOptions, outputFormat: string): Promise<void> {
  if (!providerName) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, 'Provider name required. Usage: providers test <provider> [model]'));
    } else {
      await pretty.error('Provider name required. Usage: providers test <provider> [model]');
    }
    return;
  }
  
  const resolved = PROVIDER_ALIASES[providerName.toLowerCase()] || providerName.toLowerCase();
  const providerInfo = AISDK_PROVIDERS[resolved];
  
  if (!providerInfo) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.INVALID_ARGS, `Unknown provider: ${providerName}`));
    } else {
      await pretty.error(`Unknown provider: ${providerName}`);
    }
    return;
  }
  
  // Check API key
  if (!process.env[providerInfo.envKey]) {
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.MISSING_ARG, `Missing API key: ${providerInfo.envKey}`));
    } else {
      await pretty.error(`Missing API key: ${providerInfo.envKey}`);
      await pretty.info(`Set it with: export ${providerInfo.envKey}=your-api-key`);
    }
    return;
  }
  
  // Get default model
  const model = modelName || PROVIDER_MODELS[resolved]?.[0] || 'default';
  const modelString = `${resolved}/${model}`;
  
  if (outputFormat !== 'json') {
    await pretty.info(`Testing ${modelString}...`);
  }
  
  const startTime = Date.now();
  
  try {
    // Try to use the backend resolver
    const { resolveBackend } = await import('../../llm/backend-resolver');
    const { provider } = await resolveBackend(modelString);
    
    // Make a minimal test request
    const result = await provider.generateText({
      messages: [{ role: 'user', content: 'Say "test ok" and nothing else.' }],
      temperature: 0,
      maxTokens: 10
    });
    
    const latency = Date.now() - startTime;
    const responseText = result.text?.slice(0, 50) || '[no response]';
    
    if (outputFormat === 'json') {
      outputJson(formatSuccess({
        provider: resolved,
        model,
        status: 'success',
        latency_ms: latency,
        response_preview: responseText,
        usage: result.usage
      }));
    } else {
      await pretty.plain(`\n  ✅ Test Passed`);
      await pretty.plain(`  Provider: ${resolved}`);
      await pretty.plain(`  Model: ${model}`);
      await pretty.plain(`  Latency: ${latency}ms`);
      await pretty.dim(`  Response: "${responseText}"`);
      if (result.usage) {
        await pretty.dim(`  Tokens: ${result.usage.totalTokens || 'N/A'}`);
      }
    }
  } catch (error: any) {
    const latency = Date.now() - startTime;
    const errorMessage = error.message || String(error);
    
    if (outputFormat === 'json') {
      outputJson(formatError(ERROR_CODES.UNKNOWN, errorMessage, {
        provider: resolved,
        model,
        latency_ms: latency
      }));
    } else {
      await pretty.error(`Test Failed: ${errorMessage}`);
      await pretty.plain(`  Provider: ${resolved}`);
      await pretty.plain(`  Model: ${model}`);
      await pretty.plain(`  Latency: ${latency}ms`);
    }
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
