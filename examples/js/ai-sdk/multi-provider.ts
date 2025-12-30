/**
 * AI SDK Multi-Provider Example
 * 
 * Demonstrates using multiple LLM providers with the same interface.
 * 
 * Usage:
 *   npx ts-node multi-provider.ts
 * 
 * Environment:
 *   OPENAI_API_KEY - Your OpenAI API key
 *   ANTHROPIC_API_KEY - Your Anthropic API key
 *   GOOGLE_API_KEY - Your Google API key
 */

import { createAISDKBackend } from 'praisonai';

const PROMPT = 'Explain what an API is in one sentence.';

async function testProvider(modelString: string) {
  try {
    const backend = createAISDKBackend(modelString, {
      timeout: 30000,
    });

    const startTime = Date.now();
    const result = await backend.generateText({
      messages: [{ role: 'user', content: PROMPT }],
      maxTokens: 100,
    });
    const duration = Date.now() - startTime;

    console.log(`\n${modelString}:`);
    console.log(`  Response: ${result.text}`);
    console.log(`  Duration: ${duration}ms`);
    return true;
  } catch (error: any) {
    console.log(`\n${modelString}:`);
    console.log(`  Error: ${error.message}`);
    return false;
  }
}

async function main() {
  console.log('Testing multiple providers with the same prompt...');
  console.log(`Prompt: "${PROMPT}"`);

  const providers = [
    'openai/gpt-4o-mini',
    'anthropic/claude-3-haiku-20240307',
    'google/gemini-1.5-flash',
  ];

  const results = await Promise.all(providers.map(testProvider));
  
  const successful = results.filter(Boolean).length;
  console.log(`\n\nSummary: ${successful}/${providers.length} providers succeeded`);
}

main().catch(console.error);
