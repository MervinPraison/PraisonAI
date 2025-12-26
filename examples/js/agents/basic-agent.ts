/**
 * Basic Agent Example
 * Demonstrates simple agent usage with OpenAI
 */

import { Agent } from 'praisonai';

async function main() {
  const agent = new Agent({
    name: 'Assistant',
    instructions: 'You are a helpful assistant. Be concise and informative.',
    llm: 'openai/gpt-4o-mini'
  });

  const response = await agent.chat('What is TypeScript?');
  console.log('Response:', response.text);
}

main().catch(console.error);
