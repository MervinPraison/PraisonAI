/**
 * Memory Example - Using memory for agent context
 * 
 * Run: npx ts-node examples/features/memory.ts
 */

import { Agent, Memory } from '../../src';

async function main() {
  // Create a memory instance
  const memory = new Memory({
    maxEntries: 100,
    maxTokens: 50000
  });

  // Add some context to memory
  await memory.add("User prefers concise answers", "system", { priority: "high" });
  await memory.add("User is working on a TypeScript project", "system", { topic: "programming" });

  // Search memory
  const results = await memory.search("TypeScript");
  console.log("Memory search results:", results);

  // Get recent entries
  const recent = memory.getRecent(5);
  console.log("Recent entries:", recent);

  // Create agent
  const agent = new Agent({
    instructions: "You are a helpful assistant. Use context from memory.",
    verbose: true
  });

  await agent.chat("Help me with my project");
}

main().catch(console.error);
