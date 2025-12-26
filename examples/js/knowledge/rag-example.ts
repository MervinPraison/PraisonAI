/**
 * Knowledge Base (RAG) Example
 * Demonstrates retrieval-augmented generation
 */

import { KnowledgeBase, createKnowledgeBase, Chunking } from 'praisonai';

async function main() {
  // Create knowledge base
  const kb = createKnowledgeBase();

  // Add documents
  const documents = [
    {
      id: 'ts-intro',
      content: 'TypeScript is a strongly typed programming language that builds on JavaScript, giving you better tooling at any scale.',
      metadata: { category: 'introduction', language: 'typescript' }
    },
    {
      id: 'ts-types',
      content: 'TypeScript adds optional static typing and class-based object-oriented programming to the language.',
      metadata: { category: 'features', language: 'typescript' }
    },
    {
      id: 'ts-benefits',
      content: 'Benefits of TypeScript include catching errors early, better IDE support, and improved code maintainability.',
      metadata: { category: 'benefits', language: 'typescript' }
    },
    {
      id: 'js-intro',
      content: 'JavaScript is a lightweight, interpreted programming language with first-class functions.',
      metadata: { category: 'introduction', language: 'javascript' }
    }
  ];

  for (const doc of documents) {
    await kb.add(doc);
  }

  console.log('Documents added:', kb.size);

  // Search
  console.log('\n=== Search: "TypeScript benefits" ===');
  const results = await kb.search('TypeScript benefits', 3);
  results.forEach(r => {
    console.log(`Score: ${r.score.toFixed(2)} - ${r.document.content.substring(0, 50)}...`);
  });

  // Build context
  console.log('\n=== Context for LLM ===');
  const context = kb.buildContext(results);
  console.log(context);

  // Chunking example
  console.log('\n=== Chunking Example ===');
  const chunker = new Chunking({ chunkSize: 100, overlap: 20 });
  const longText = 'This is a long document. '.repeat(20);
  const chunks = chunker.chunk(longText);
  console.log(`Chunked into ${chunks.length} pieces`);
}

main().catch(console.error);
