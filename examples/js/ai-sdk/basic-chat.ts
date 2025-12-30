/**
 * AI SDK Basic Chat Example
 * 
 * Demonstrates simple text generation using the AI SDK backend.
 * 
 * Usage:
 *   npx ts-node basic-chat.ts
 * 
 * Environment:
 *   OPENAI_API_KEY - Your OpenAI API key
 */

import { createAISDKBackend } from 'praisonai';

async function main() {
  // Create backend with model string
  const backend = createAISDKBackend('openai/gpt-4o-mini');

  console.log('Sending message to OpenAI...\n');

  // Generate text
  const result = await backend.generateText({
    messages: [
      { role: 'system', content: 'You are a helpful assistant.' },
      { role: 'user', content: 'What are the three primary colors?' }
    ],
    maxTokens: 200,
    temperature: 0.7,
  });

  console.log('Response:', result.text);
  console.log('\nFinish reason:', result.finishReason);
  
  if (result.usage) {
    console.log('Token usage:', result.usage);
  }
}

main().catch(console.error);
