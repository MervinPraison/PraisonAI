/**
 * Basic Embedding Example
 * 
 * Demonstrates using Agent.embed() for text embeddings
 * 
 * Run: npx ts-node examples/js/embeddings/embed-basic.ts
 */

import { Agent } from '../../../src/praisonai-ts/dist/agent/simple';
import { embed, embedMany, cosineSimilarity } from '../../../src/praisonai-ts/dist/llm/embeddings';

async function main() {
  console.log('=== Basic Embedding Example ===\n');

  // Method 1: Using Agent.embed()
  console.log('1. Agent.embed() - Single text');
  const agent = new Agent({
    instructions: 'You are a helpful assistant',
    llm: 'openai/gpt-4o-mini',
    verbose: false
  });

  const singleEmbedding = await agent.embed('Hello world');
  console.log(`   Dimensions: ${(singleEmbedding as number[]).length}`);
  console.log(`   First 5 values: [${(singleEmbedding as number[]).slice(0, 5).map(v => v.toFixed(4)).join(', ')}...]`);

  // Method 2: Using Agent.embed() with multiple texts
  console.log('\n2. Agent.embed() - Multiple texts');
  const multiEmbeddings = await agent.embed(['Hello', 'World', 'How are you?']);
  console.log(`   Count: ${(multiEmbeddings as number[][]).length}`);
  console.log(`   Each has ${(multiEmbeddings as number[][])[0].length} dimensions`);

  // Method 3: Direct embed function
  console.log('\n3. Direct embed() function');
  const result = await embed('PraisonAI is an AI agent framework');
  console.log(`   Dimensions: ${result.embedding.length}`);
  console.log(`   Tokens used: ${result.usage?.tokens || 'N/A'}`);

  // Method 4: Batch embeddings
  console.log('\n4. Batch embedMany() function');
  const texts = [
    'Machine learning is a subset of AI',
    'Deep learning uses neural networks',
    'Natural language processing handles text'
  ];
  const batchResult = await embedMany(texts);
  console.log(`   Embedded ${batchResult.embeddings.length} texts`);
  console.log(`   Total tokens: ${batchResult.usage?.tokens || 'N/A'}`);

  // Method 5: Similarity comparison
  console.log('\n5. Cosine Similarity');
  const emb1 = await embed('I love programming');
  const emb2 = await embed('Coding is my passion');
  const emb3 = await embed('The weather is nice today');

  const sim12 = cosineSimilarity(emb1.embedding, emb2.embedding);
  const sim13 = cosineSimilarity(emb1.embedding, emb3.embedding);

  console.log(`   "I love programming" vs "Coding is my passion": ${(sim12 * 100).toFixed(1)}%`);
  console.log(`   "I love programming" vs "The weather is nice": ${(sim13 * 100).toFixed(1)}%`);

  console.log('\n=== Complete ===');
}

main().catch(console.error);
