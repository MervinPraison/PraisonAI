/**
 * AI SDK Basic Chat Example
 * 
 * Demonstrates basic text generation using the AI SDK backend.
 * 
 * Usage:
 *   npx ts-node examples/ai-sdk/basic-chat.ts
 * 
 * Required environment variables:
 *   OPENAI_API_KEY - Your OpenAI API key
 */

import { createAISDKBackend } from '../../src/llm/providers/ai-sdk';

async function main() {
  console.log('AI SDK Basic Chat Example\n');

  // Create a backend for OpenAI
  const backend = createAISDKBackend('openai/gpt-4o-mini', {
    timeout: 30000,
    maxRetries: 2,
  });

  console.log(`Provider: ${backend.providerId}`);
  console.log(`Model: ${backend.modelId}\n`);

  // Generate text
  const result = await backend.generateText({
    messages: [
      { role: 'system', content: 'You are a helpful assistant.' },
      { role: 'user', content: 'What is the capital of France? Answer in one sentence.' }
    ],
    temperature: 0.7,
    maxTokens: 100,
  });

  console.log('Response:', result.text);
  console.log('\nUsage:', result.usage);
  console.log('Finish Reason:', result.finishReason);
}

main().catch(console.error);
