/**
 * Multi-Provider Example
 * 
 * Demonstrates using multiple LLM providers in a single workflow.
 * Each agent uses a different provider optimized for its task.
 * 
 * Required env vars:
 * - OPENAI_API_KEY
 * - ANTHROPIC_API_KEY
 * - GOOGLE_API_KEY
 */

import { Agent, Agents } from 'praisonai';

async function main() {
  // Fast model for quick categorization
  const triageAgent = new Agent({
    name: 'Triage',
    instructions: 'Quickly categorize the user request into: technical, creative, or general.',
    llm: 'openai/gpt-4o-mini'  // Fast and cheap
  });

  // Powerful model for complex reasoning
  const analysisAgent = new Agent({
    name: 'Analyst',
    instructions: 'Analyze the request in depth and provide detailed insights.',
    llm: 'anthropic/claude-3-5-sonnet'  // Best reasoning
  });

  // Creative model for content generation
  const writerAgent = new Agent({
    name: 'Writer',
    instructions: 'Write a clear, engaging response based on the analysis.',
    llm: 'google/gemini-2.0-flash'  // Good for creative tasks
  });

  // Create multi-agent workflow
  const agents = new Agents({
    agents: [triageAgent, analysisAgent, writerAgent],
    tasks: [
      { agent: triageAgent, description: 'Categorize: {input}' },
      { agent: analysisAgent, description: 'Analyze the categorized request' },
      { agent: writerAgent, description: 'Write the final response' }
    ]
  });

  console.log('Starting multi-provider workflow...\n');
  
  const result = await agents.start({
    input: 'Explain how neural networks learn'
  });

  console.log('\n=== Final Result ===');
  console.log(result);
}

main().catch(console.error);
