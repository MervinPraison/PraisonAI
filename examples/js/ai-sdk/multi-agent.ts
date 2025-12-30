/**
 * AI SDK Multi-Agent Attribution Example
 * 
 * Demonstrates how to propagate attribution context (agentId, runId, traceId)
 * to LLM calls for multi-agent observability and safety.
 * 
 * Usage:
 *   npx ts-node multi-agent.ts
 * 
 * Environment:
 *   OPENAI_API_KEY - Your OpenAI API key
 */

import { createAISDKBackend } from 'praisonai';

// Simulate a multi-agent system with attribution
interface AgentContext {
  agentId: string;
  runId: string;
  traceId: string;
  sessionId?: string;
}

async function runAgent(name: string, task: string, context: AgentContext) {
  console.log(`\n[${name}] Starting task: ${task}`);
  console.log(`  Attribution: agentId=${context.agentId}, runId=${context.runId}`);

  const backend = createAISDKBackend('openai/gpt-4o-mini', {
    attribution: context,
    timeout: 30000,
  });

  const result = await backend.generateText({
    messages: [
      { role: 'system', content: `You are ${name}, a specialized AI agent.` },
      { role: 'user', content: task }
    ],
    maxTokens: 100,
  });

  console.log(`  Response: ${result.text.slice(0, 100)}...`);
  return result.text;
}

async function main() {
  // Create a shared trace ID for the entire workflow
  const traceId = `trace-${Date.now().toString(36)}`;
  const sessionId = 'session-user123';

  console.log('Multi-Agent Workflow with Attribution');
  console.log('=====================================');
  console.log(`Trace ID: ${traceId}`);
  console.log(`Session ID: ${sessionId}`);

  // Agent 1: Research Agent
  const researchResult = await runAgent(
    'ResearchAgent',
    'What are the key benefits of TypeScript?',
    {
      agentId: 'agent-research',
      runId: `run-${Date.now().toString(36)}-1`,
      traceId,
      sessionId,
    }
  );

  // Agent 2: Summary Agent
  const summaryResult = await runAgent(
    'SummaryAgent',
    `Summarize this in one sentence: ${researchResult}`,
    {
      agentId: 'agent-summary',
      runId: `run-${Date.now().toString(36)}-2`,
      traceId,
      sessionId,
    }
  );

  // Agent 3: Review Agent
  await runAgent(
    'ReviewAgent',
    `Review this summary for accuracy: ${summaryResult}`,
    {
      agentId: 'agent-review',
      runId: `run-${Date.now().toString(36)}-3`,
      traceId,
      sessionId,
    }
  );

  console.log('\n\nWorkflow complete!');
  console.log('All requests were tagged with the same trace ID for observability.');
  console.log('Check your LLM provider dashboard to see the correlated requests.');
}

main().catch(console.error);
