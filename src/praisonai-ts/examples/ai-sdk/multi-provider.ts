/**
 * AI SDK Multi-Provider Example
 * 
 * Demonstrates using multiple AI providers with the same interface.
 * 
 * Usage:
 *   npx ts-node examples/ai-sdk/multi-provider.ts
 * 
 * Required environment variables (set at least one):
 *   OPENAI_API_KEY - Your OpenAI API key
 *   ANTHROPIC_API_KEY - Your Anthropic API key
 *   GOOGLE_API_KEY - Your Google API key
 */

import { createAISDKBackend, validateProviderApiKey } from '../../src/llm/providers/ai-sdk';

const PROVIDERS = [
  { id: 'openai', model: 'gpt-4o-mini' },
  { id: 'anthropic', model: 'claude-3-haiku-20240307' },
  { id: 'google', model: 'gemini-1.5-flash' },
];

async function main() {
  console.log('AI SDK Multi-Provider Example\n');
  console.log('Testing multiple providers with the same prompt...\n');

  const prompt = 'What is 2 + 2? Answer with just the number.';
  console.log(`Prompt: "${prompt}"\n`);
  console.log('---\n');

  for (const provider of PROVIDERS) {
    // Check if API key is available
    if (!validateProviderApiKey(provider.id)) {
      console.log(`${provider.id}: Skipped (no API key)`);
      continue;
    }

    try {
      const modelString = `${provider.id}/${provider.model}`;
      console.log(`${provider.id} (${provider.model}):`);

      const backend = createAISDKBackend(modelString, {
        timeout: 30000,
        maxRetries: 1,
      });

      const startTime = Date.now();
      const result = await backend.generateText({
        messages: [
          { role: 'user', content: prompt }
        ],
        temperature: 0,
        maxTokens: 10,
      });
      const duration = Date.now() - startTime;

      console.log(`  Response: ${result.text.trim()}`);
      console.log(`  Duration: ${duration}ms`);
      console.log(`  Tokens: ${result.usage?.totalTokens || 'N/A'}`);
      console.log();
    } catch (error) {
      console.log(`  Error: ${error instanceof Error ? error.message : 'Unknown error'}`);
      console.log();
    }
  }
}

main().catch(console.error);
