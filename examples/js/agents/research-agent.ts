/**
 * Deep Research Agent Example
 * Demonstrates comprehensive research with citations
 */

import { DeepResearchAgent, createDeepResearchAgent } from 'praisonai';

async function main() {
  const agent = createDeepResearchAgent({
    name: 'Scholar',
    llm: 'openai/gpt-4o-mini',
    maxIterations: 5,
    verbose: true
  });

  console.log('Research Agent:', agent.name);

  // Conduct research
  const result = await agent.research('What are the key benefits of TypeScript?');

  console.log('\n=== Research Results ===');
  console.log('Answer:', result.answer.substring(0, 500) + '...');
  console.log('\nConfidence:', result.confidence);
  console.log('Reasoning steps:', result.reasoning.length);

  // Show reasoning
  console.log('\n=== Reasoning Process ===');
  result.reasoning.forEach(step => {
    console.log(`Step ${step.step}: ${step.thought}`);
  });
}

main().catch(console.error);
