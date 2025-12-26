/**
 * Context Agent Example
 * Demonstrates RAG-enabled agent with knowledge base
 */

import { ContextAgent, createContextAgent, KnowledgeBase } from 'praisonai';

async function main() {
  // Create knowledge base
  const kb = new KnowledgeBase();
  
  // Add documents
  await kb.add({
    id: 'doc1',
    content: 'TypeScript is a strongly typed programming language that builds on JavaScript.',
    metadata: { topic: 'typescript' }
  });
  
  await kb.add({
    id: 'doc2',
    content: 'TypeScript adds optional static typing and class-based object-oriented programming.',
    metadata: { topic: 'typescript' }
  });

  await kb.add({
    id: 'doc3',
    content: 'PraisonAI is a framework for building AI agents in TypeScript and Python.',
    metadata: { topic: 'praisonai' }
  });

  // Create context agent with knowledge base
  const agent = createContextAgent({
    name: 'KnowledgeAgent',
    llm: 'openai/gpt-4o-mini',
    knowledgeBase: kb,
    maxContextDocs: 3
  });

  // Query with context
  const response = await agent.chat('What is TypeScript?');
  console.log('Response:', response.text);

  // Check conversation history
  console.log('\nConversation history:', agent.getHistory().length, 'messages');
}

main().catch(console.error);
