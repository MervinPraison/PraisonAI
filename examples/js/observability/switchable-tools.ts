/**
 * Switchable Observability Tools Example
 * 
 * Demonstrates switching between observability tools via environment variable.
 * Set OBS_TOOL env var to: langfuse, langsmith, console, memory, noop
 * 
 * Usage:
 *   OBS_TOOL=console npx tsx switchable-tools.ts
 *   OBS_TOOL=langfuse LANGFUSE_SECRET_KEY=sk-... npx tsx switchable-tools.ts
 */

import { Agent, createObservabilityAdapter, setObservabilityAdapter } from 'praisonai';

async function main() {
  // Get tool from environment (default to memory)
  const toolName = process.env.OBS_TOOL || 'memory';
  
  console.log(`Using observability tool: ${toolName}\n`);

  // Create adapter dynamically
  const obs = await createObservabilityAdapter(toolName as any);
  setObservabilityAdapter(obs);

  // Create agent
  const agent = new Agent({
    name: 'ObservedAgent',
    instructions: 'You are a helpful assistant.'
  });

  // Run interaction
  console.log('Running agent...\n');
  const response = await agent.chat('Hello! What is 2 + 2?');
  console.log('Response:', response);

  // Flush traces to backend
  await obs.flush();
  console.log('\nTraces flushed to', toolName);
}

main().catch(console.error);
