/**
 * Basic RAG Agent Example
 * 
 * Demonstrates building a RAG agent with context injection.
 * 
 * Prerequisites:
 *   npm install praisonai-ts
 *   export OPENAI_API_KEY=your-api-key
 * 
 * Run:
 *   npx ts-node basic-rag.ts
 */

import { Agent } from '../../../src/praisonai-ts/src';

// Simulated knowledge base (in production, use a vector store)
const knowledgeBase = [
  { id: '1', content: 'PraisonAI is an AI agent framework for building intelligent applications.' },
  { id: '2', content: 'Agents can use tools to accomplish tasks like web search and calculations.' },
  { id: '3', content: 'RAG combines retrieval with generation for accurate, grounded responses.' },
];

// Simple search function (in production, use vector similarity)
function searchKnowledge(query: string): string[] {
  const queryLower = query.toLowerCase();
  return knowledgeBase
    .filter(doc => doc.content.toLowerCase().includes(queryLower.split(' ')[0]))
    .map(doc => doc.content);
}

async function main() {
  console.log('=== Basic RAG Agent Example ===\n');

  // Create an agent with RAG-style instructions
  const agent = new Agent({
    name: 'RAGAgent',
    instructions: `You are a helpful assistant that answers questions using provided context.
Always base your answers on the context provided.
If the context doesn't contain relevant information, say so.`,
  });

  // Query with context injection
  const query = 'What is PraisonAI?';
  console.log(`Q: ${query}`);
  
  // Retrieve relevant context
  const context = searchKnowledge(query).join('\n\n');
  
  // Ask the agent with context
  const response = await agent.chat(
    `Context:\n${context}\n\nQuestion: ${query}`
  );
  
  console.log(`A: ${response}\n`);
}

main().catch(console.error);
