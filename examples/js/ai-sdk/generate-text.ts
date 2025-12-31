/**
 * Generate Text Example
 * 
 * Demonstrates basic text generation using AI SDK v6 via praisonai-ts.
 * 
 * Run: npx ts-node generate-text.ts
 * Required: OPENAI_API_KEY
 */

// Import from local praisonai-ts package
// In production: import { Agent } from 'praisonai';
import { Agent } from '../../../src/praisonai-ts/src';

async function main() {
  // Simple text generation with Agent
  const agent = new Agent({
    instructions: 'You are a helpful assistant that provides concise answers.',
    llm: 'openai/gpt-4o-mini',
  });

  console.log('=== Generate Text Example ===\n');

  // Basic chat
  const response = await agent.chat('What is the capital of France?');
  console.log('Response:', response);

  // With context
  const response2 = await agent.chat('What is its population?');
  console.log('\nFollow-up:', response2);
}

main().catch(console.error);
