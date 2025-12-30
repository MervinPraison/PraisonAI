/**
 * AI SDK Streaming Example
 * 
 * Demonstrates streaming text generation with real-time output.
 * 
 * Usage:
 *   npx ts-node streaming.ts
 * 
 * Environment:
 *   OPENAI_API_KEY - Your OpenAI API key
 */

import { createAISDKBackend } from 'praisonai';

async function main() {
  const backend = createAISDKBackend('openai/gpt-4o-mini');

  console.log('Streaming response from OpenAI...\n');

  const stream = await backend.streamText({
    messages: [
      { role: 'user', content: 'Write a short poem about coding.' }
    ],
    maxTokens: 200,
  });

  // Stream chunks as they arrive
  for await (const chunk of stream) {
    if (chunk.text) {
      process.stdout.write(chunk.text);
    }
    
    if (chunk.finishReason) {
      console.log('\n\nFinish reason:', chunk.finishReason);
    }
  }
}

main().catch(console.error);
