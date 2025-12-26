/**
 * Conversation Memory Example
 * Demonstrates memory management for conversations
 */

import { Memory, createMemory } from 'praisonai';

async function main() {
  const memory = createMemory({
    maxEntries: 100,
    maxTokens: 10000
  });

  // Simulate a conversation
  await memory.add('What is TypeScript?', 'user');
  await memory.add('TypeScript is a strongly typed programming language that builds on JavaScript.', 'assistant');
  await memory.add('What are its main benefits?', 'user');
  await memory.add('Key benefits include type safety, better IDE support, and easier refactoring.', 'assistant');
  await memory.add('Can you give an example?', 'user');

  console.log('Memory size:', memory.size, 'entries\n');

  // Get recent messages
  console.log('=== Recent Messages ===');
  const recent = memory.getRecent(3);
  recent.forEach(entry => {
    console.log(`[${entry.role}]: ${entry.content.substring(0, 50)}...`);
  });

  // Search memory
  console.log('\n=== Search Results for "TypeScript" ===');
  const results = await memory.search('TypeScript');
  results.forEach(r => {
    console.log(`Score: ${r.score.toFixed(2)} - ${r.entry.content.substring(0, 40)}...`);
  });

  // Build context
  console.log('\n=== Full Context ===');
  console.log(memory.buildContext());
}

main().catch(console.error);
