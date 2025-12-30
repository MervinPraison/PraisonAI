/**
 * AI SDK Multi-Agent Example
 * 
 * Demonstrates multi-agent safety with attribution context.
 * Each agent has its own ID and the context is propagated to LLM calls.
 * 
 * Usage:
 *   npx ts-node examples/ai-sdk/multi-agent.ts
 * 
 * Required environment variables:
 *   OPENAI_API_KEY - Your OpenAI API key
 */

import { createAISDKBackend } from '../../src/llm/providers/ai-sdk';
import type { AttributionContext } from '../../src/llm/providers/ai-sdk/types';

// Simulate multiple agents running in parallel
async function runAgent(
  agentId: string,
  task: string,
  attribution: AttributionContext
): Promise<{ agentId: string; result: string; duration: number }> {
  console.log(`[${agentId}] Starting task: "${task}"`);
  
  // Create backend with attribution context
  const backend = createAISDKBackend('openai/gpt-4o-mini', {
    timeout: 30000,
    attribution,
  });

  const startTime = Date.now();
  
  const result = await backend.generateText({
    messages: [
      { role: 'system', content: `You are agent ${agentId}. Be concise.` },
      { role: 'user', content: task }
    ],
    temperature: 0.7,
    maxTokens: 100,
  });

  const duration = Date.now() - startTime;
  
  console.log(`[${agentId}] Completed in ${duration}ms`);
  
  return {
    agentId,
    result: result.text,
    duration
  };
}

async function main() {
  console.log('AI SDK Multi-Agent Example\n');
  console.log('Running multiple agents in parallel with attribution tracking...\n');

  // Shared run context
  const runId = `run-${Date.now()}`;
  const traceId = `trace-${Math.random().toString(36).slice(2, 10)}`;
  const sessionId = 'session-demo';

  console.log(`Run ID: ${runId}`);
  console.log(`Trace ID: ${traceId}`);
  console.log(`Session ID: ${sessionId}\n`);
  console.log('---\n');

  // Define agents with their tasks
  const agents = [
    {
      id: 'researcher',
      task: 'What is the population of Tokyo? Just the number.',
      attribution: {
        agentId: 'researcher',
        runId,
        traceId,
        sessionId,
      }
    },
    {
      id: 'analyst',
      task: 'What is 15% of 1000? Just the number.',
      attribution: {
        agentId: 'analyst',
        runId,
        traceId,
        sessionId,
      }
    },
    {
      id: 'writer',
      task: 'Write a one-sentence tagline for a coffee shop.',
      attribution: {
        agentId: 'writer',
        runId,
        traceId,
        sessionId,
      }
    }
  ];

  // Run all agents in parallel
  const startTime = Date.now();
  const results = await Promise.all(
    agents.map(agent => runAgent(agent.id, agent.task, agent.attribution))
  );
  const totalDuration = Date.now() - startTime;

  console.log('\n---\n');
  console.log('Results:\n');

  for (const result of results) {
    console.log(`[${result.agentId}] (${result.duration}ms)`);
    console.log(`  ${result.result.trim()}\n`);
  }

  console.log('---');
  console.log(`Total parallel execution time: ${totalDuration}ms`);
  console.log(`Sum of individual times: ${results.reduce((sum, r) => sum + r.duration, 0)}ms`);
  console.log('\nNote: Attribution headers (X-Agent-Id, X-Run-Id, X-Trace-Id, X-Session-Id)');
  console.log('are automatically injected into each LLM request for tracing and debugging.');
}

main().catch(console.error);
