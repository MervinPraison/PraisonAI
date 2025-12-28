/**
 * Hello Agent - The simplest possible PraisonAI example (3 lines)
 * 
 * Run: npx ts-node examples/quickstart/hello-agent.ts
 */

import { Agent } from '../../src';

const agent = new Agent({ instructions: "You are a helpful assistant" });
agent.chat("Hello! Tell me a fun fact about AI.").then(console.log);
