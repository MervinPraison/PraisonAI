/**
 * Sessions Example - Conversation persistence with session IDs
 * 
 * Run: npx ts-node examples/features/sessions.ts
 */

import { Agent, db } from '../../src';

async function main() {
  // Create an agent with session persistence
  const agent = new Agent({
    instructions: "You are a helpful assistant that remembers our conversation.",
    db: db("sqlite:./sessions.db"),
    sessionId: "user-alice-123"
  });

  // First conversation
  console.log("=== First Conversation ===");
  await agent.chat("My name is Alice and I love programming.");
  
  // Continue the conversation - agent remembers context
  console.log("\n=== Continuing Conversation ===");
  await agent.chat("What's my name and what do I love?");
  
  // Get session info
  console.log("\n=== Session Info ===");
  console.log("Session ID:", agent.getSessionId());
  console.log("Run ID:", agent.getRunId());
}

main().catch(console.error);
