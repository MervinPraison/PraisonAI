/**
 * Agent with Persistence - Auto-save messages to database (4 lines)
 * 
 * Run: npx ts-node examples/quickstart/with-persistence.ts
 */

import { Agent, db } from '../../src';

const agent = new Agent({
  instructions: "You are a helpful assistant with memory",
  db: db("memory:"),  // Use in-memory db for demo (use "sqlite:./data.db" for file)
  sessionId: "my-session"
});

agent.chat("Remember that my favorite color is blue.").then(console.log);
