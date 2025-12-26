/**
 * Providers command - List available LLM providers
 */

import { getAvailableProviders } from '../../llm/providers';
import { hasApiKey } from '../runtime/env';
import { outputJson, formatSuccess } from '../output/json';
import * as pretty from '../output/pretty';

export interface ProvidersOptions {
  verbose?: boolean;
  output?: 'json' | 'text' | 'pretty';
  json?: boolean;
}

interface ProviderInfo {
  name: string;
  available: boolean;
  hasApiKey: boolean;
  models?: string[];
}

const PROVIDER_MODELS: Record<string, string[]> = {
  openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-4', 'gpt-3.5-turbo'],
  anthropic: ['claude-sonnet-4-20250514', 'claude-3-5-sonnet-20241022', 'claude-3-opus-20240229', 'claude-3-haiku-20240307'],
  google: ['gemini-2.0-flash', 'gemini-1.5-pro', 'gemini-1.5-flash']
};

export async function execute(args: string[], options: ProvidersOptions): Promise<void> {
  const outputFormat = options.json ? 'json' : (options.output || 'pretty');
  
  const availableProviders = getAvailableProviders();
  
  const providers: ProviderInfo[] = [
    {
      name: 'openai',
      available: availableProviders.includes('openai'),
      hasApiKey: hasApiKey('openai'),
      models: PROVIDER_MODELS.openai
    },
    {
      name: 'anthropic',
      available: availableProviders.includes('anthropic'),
      hasApiKey: hasApiKey('anthropic'),
      models: PROVIDER_MODELS.anthropic
    },
    {
      name: 'google',
      available: availableProviders.includes('google'),
      hasApiKey: hasApiKey('google'),
      models: PROVIDER_MODELS.google
    }
  ];

  if (outputFormat === 'json') {
    outputJson(formatSuccess({
      providers: providers.map(p => ({
        name: p.name,
        available: p.available,
        has_api_key: p.hasApiKey,
        models: options.verbose ? p.models : undefined
      }))
    }));
  } else {
    await pretty.heading('Available Providers');
    
    for (const provider of providers) {
      const status = provider.available ? '✅' : '❌';
      const keyStatus = provider.hasApiKey ? '🔑' : '⚠️ No API key';
      
      await pretty.plain(`  ${status} ${provider.name} ${keyStatus}`);
      
      if (options.verbose && provider.models) {
        for (const model of provider.models) {
          await pretty.dim(`      - ${model}`);
        }
      }
    }
    
    await pretty.newline();
    await pretty.info('Set API keys via environment variables:');
    await pretty.dim('  OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY');
  }
}
