/**
 * Multi-Agent Example
 * Demonstrates multiple agents working together
 */

import { Agent, PraisonAIAgents, Task } from 'praisonai';

async function main() {
  // Create specialized agents
  const researcher = new Agent({
    name: 'Researcher',
    role: 'Research Specialist',
    goal: 'Find accurate information on topics',
    instructions: 'You research topics thoroughly and provide factual information.'
  });

  const writer = new Agent({
    name: 'Writer',
    role: 'Content Writer',
    goal: 'Create engaging content from research',
    instructions: 'You write clear, engaging content based on provided research.'
  });

  // Create tasks
  const researchTask = new Task({
    description: 'Research the benefits of TypeScript over JavaScript',
    expectedOutput: 'A list of key benefits with explanations',
    agent: researcher
  });

  const writeTask = new Task({
    description: 'Write a short article about TypeScript benefits',
    expectedOutput: 'A 200-word article',
    agent: writer
  });

  // Run agents
  const agents = new PraisonAIAgents({
    agents: [researcher, writer],
    tasks: [researchTask, writeTask],
    process: 'sequential'
  });

  const result = await agents.start();
  console.log('Result:', result);
}

main().catch(console.error);
