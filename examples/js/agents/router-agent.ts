/**
 * Router Agent Example
 * Demonstrates routing requests to specialized agents
 */

import { RouterAgent, createRouter, routeConditions, Agent } from 'praisonai';

async function main() {
  // Create specialized agents
  const mathAgent = {
    name: 'MathAgent',
    chat: async (input: string) => ({ text: `Math answer for: ${input}` })
  } as any;

  const codeAgent = {
    name: 'CodeAgent', 
    chat: async (input: string) => ({ text: `Code solution for: ${input}` })
  } as any;

  const generalAgent = {
    name: 'GeneralAgent',
    chat: async (input: string) => ({ text: `General response: ${input}` })
  } as any;

  // Create router with conditions
  const router = createRouter({
    name: 'SmartRouter',
    routes: [
      {
        agent: mathAgent,
        condition: routeConditions.keywords(['math', 'calculate', 'number', 'equation']),
        priority: 10
      },
      {
        agent: codeAgent,
        condition: routeConditions.keywords(['code', 'program', 'function', 'javascript']),
        priority: 10
      }
    ],
    defaultAgent: generalAgent
  });

  // Test routing
  const queries = [
    'Calculate 2 + 2',
    'Write a function to sort an array',
    'What is the weather today?'
  ];

  for (const query of queries) {
    const result = await router.route(query);
    console.log(`Query: "${query}"`);
    console.log(`Routed to: ${result?.agent.name || 'default'}\n`);
  }
}

main().catch(console.error);
