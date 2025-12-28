/**
 * Knowledge Base Example - RAG with agents
 * 
 * Run: npx ts-node examples/features/knowledge.ts
 */

import { Agent, BaseKnowledgeBase, type Knowledge } from '../../src';

async function main() {
  // Create knowledge base
  const kb = new BaseKnowledgeBase();

  // Add knowledge entries
  kb.addKnowledge({
    id: "overview",
    type: "documentation",
    content: `
      PraisonAI is a TypeScript SDK for building AI agents.
      It supports multiple LLM providers including OpenAI, Anthropic, and Google.
      Key features include:
      - Simple Agent API with instructions
      - Multi-agent orchestration with Agents class
      - Workflow-based execution
      - Tool integration with auto-schema generation
      - Session persistence with db() factory
    `,
    metadata: { source: "docs", topic: "overview" }
  });

  kb.addKnowledge({
    id: "agent-usage",
    type: "documentation",
    content: `
      The Agent class is the primary entry point.
      Create an agent with: new Agent({ instructions: "..." })
      Use agent.chat("message") to interact.
      Tools can be plain functions passed in the tools array.
    `,
    metadata: { source: "docs", topic: "agent" }
  });

  // Search the knowledge base
  console.log("=== Searching Knowledge Base ===");
  const results = kb.searchKnowledge("agent");
  console.log("Found", results.length, "relevant entries");
  results.forEach((r: Knowledge, i: number) => {
    console.log(`\n[${i + 1}] ID: ${r.id}`);
    console.log(String(r.content).substring(0, 100) + "...");
  });

  // Create agent that uses knowledge
  const knowledgeContext = results.map((r: Knowledge) => r.content).join('\n\n');
  const agent = new Agent({
    instructions: `You are a helpful assistant. Use the following knowledge to answer questions:
    
${knowledgeContext}`,
    verbose: true
  });

  console.log("\n=== Agent Response ===");
  await agent.chat("How do I create an agent in PraisonAI?");
}

main().catch(console.error);
