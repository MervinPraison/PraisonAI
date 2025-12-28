/**
 * Multi-Agent Pattern - Orchestrate multiple agents
 * 
 * Run: npx ts-node examples/patterns/multi-agent.ts
 */

import { Agent, Agents } from '../../src';

// Create specialized agents
const researcher = new Agent({
  instructions: "You are a research specialist. Thoroughly research the given topic and provide detailed findings.",
  name: "Researcher"
});

const writer = new Agent({
  instructions: "You are a professional writer. Take the research provided and write a clear, engaging summary.",
  name: "Writer"
});

// Orchestrate agents - they run sequentially, passing output to the next
const agents = new Agents([researcher, writer]);

// Alternative: use config object for more control
// const agents = new Agents({
//   agents: [researcher, writer],
//   process: 'sequential',  // or 'parallel'
//   verbose: true
// });

agents.start().then(results => {
  console.log("\n=== Research Agent Output ===");
  console.log(results[0]);
  console.log("\n=== Writer Agent Output ===");
  console.log(results[1]);
});
