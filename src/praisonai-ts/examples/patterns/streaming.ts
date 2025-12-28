/**
 * Streaming Pattern - Real-time response streaming
 * 
 * Run: npx ts-node examples/patterns/streaming.ts
 */

import { Agent } from '../../src';

// Create an agent with streaming enabled
const agent = new Agent({
  instructions: "You are a creative storyteller. Write engaging, detailed stories.",
  name: "Storyteller",
  stream: true,  // Enable streaming (default is true)
  verbose: true
});

// The response will stream to stdout as it's generated
console.log("=== Streaming Story ===\n");
agent.chat("Write a short story about a robot learning to paint.").then(() => {
  console.log("\n\n=== Story Complete ===");
});
