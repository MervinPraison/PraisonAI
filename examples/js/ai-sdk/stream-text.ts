/**
 * Stream Text Example
 * 
 * Demonstrates streaming text generation using AI SDK v6 via praisonai-ts.
 * 
 * Run: npx ts-node stream-text.ts
 * Required: OPENAI_API_KEY
 */

import { Agent } from '../../../src/praisonai-ts/src';

async function main() {
  const agent = new Agent({
    instructions: 'You are a helpful assistant that provides detailed answers.',
    llm: 'openai/gpt-4o-mini',
    stream: true,
  });

  console.log('=== Stream Text Example ===\n');
  console.log('Streaming response:\n');

  // Stream the response
  const response = await agent.chat('Explain quantum computing in 3 paragraphs.');
  console.log('\n\nFinal response:', response);
}

main().catch(console.error);
