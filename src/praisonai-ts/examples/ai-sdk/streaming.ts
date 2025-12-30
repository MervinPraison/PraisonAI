/**
 * AI SDK Streaming Example
 * 
 * Demonstrates streaming text generation using the AI SDK backend.
 * 
 * Usage:
 *   npx ts-node examples/ai-sdk/streaming.ts
 * 
 * Required environment variables:
 *   OPENAI_API_KEY - Your OpenAI API key
 */

import { createAISDKBackend } from '../../src/llm/providers/ai-sdk';

async function main() {
  console.log('AI SDK Streaming Example\n');

  // Create a backend for OpenAI
  const backend = createAISDKBackend('openai/gpt-4o-mini', {
    timeout: 60000,
  });

  console.log(`Provider: ${backend.providerId}`);
  console.log(`Model: ${backend.modelId}\n`);
  console.log('Streaming response:\n');

  // Stream text
  const stream = await backend.streamText({
    messages: [
      { role: 'system', content: 'You are a helpful assistant.' },
      { role: 'user', content: 'Write a short poem about programming.' }
    ],
    temperature: 0.8,
    maxTokens: 200,
    onToken: (token) => {
      // This callback is called for each token
      process.stdout.write(token);
    },
  });

  // Consume the stream
  let totalTokens = 0;
  for await (const chunk of stream) {
    if (chunk.text) {
      // Text is already printed via onToken callback
    }
    if (chunk.usage) {
      totalTokens = chunk.usage.totalTokens || 0;
    }
  }

  console.log('\n\n---');
  console.log(`Total tokens: ${totalTokens}`);
}

main().catch(console.error);
