/**
 * Observability Example - Tracing and monitoring agents
 * 
 * Run: npx ts-node examples/features/observability.ts
 */

import { Agent, setObservabilityAdapter, ConsoleObservabilityAdapter } from '../../src';

async function main() {
  // Set up console observability (logs all traces)
  const adapter = new ConsoleObservabilityAdapter();
  setObservabilityAdapter(adapter);

  console.log("=== Observability Enabled ===");
  console.log("All agent operations will be traced to console.\n");

  // Create agent
  const agent = new Agent({
    instructions: "You are a helpful assistant.",
    verbose: true
  });

  // Run some operations - they will be traced
  console.log("=== Running Agent ===");
  await agent.chat("Hello! Tell me a joke.");

  console.log("\n=== Trace Complete ===");
  console.log("Check console output above for trace information.");
}

main().catch(console.error);
