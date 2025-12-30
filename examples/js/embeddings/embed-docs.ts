/**
 * Document Embedding Example
 * 
 * Demonstrates chunking and embedding documents for retrieval
 * 
 * Run: npx ts-node examples/js/embeddings/embed-docs.ts
 */

import { embedMany, cosineSimilarity } from '../../../src/praisonai-ts/dist/llm/embeddings';

// Sample documents
const documents = [
  {
    id: 'doc1',
    title: 'Introduction to AI',
    content: 'Artificial Intelligence (AI) is the simulation of human intelligence by machines. It includes machine learning, natural language processing, and computer vision.'
  },
  {
    id: 'doc2',
    title: 'Machine Learning Basics',
    content: 'Machine learning is a subset of AI that enables systems to learn from data. It includes supervised learning, unsupervised learning, and reinforcement learning.'
  },
  {
    id: 'doc3',
    title: 'Deep Learning',
    content: 'Deep learning uses neural networks with multiple layers. It excels at tasks like image recognition, speech processing, and natural language understanding.'
  },
  {
    id: 'doc4',
    title: 'Natural Language Processing',
    content: 'NLP enables computers to understand human language. Applications include chatbots, translation, sentiment analysis, and text summarization.'
  },
  {
    id: 'doc5',
    title: 'Computer Vision',
    content: 'Computer vision allows machines to interpret visual information. It powers applications like facial recognition, autonomous vehicles, and medical imaging.'
  }
];

interface EmbeddedDocument {
  id: string;
  title: string;
  content: string;
  embedding: number[];
}

async function main() {
  console.log('=== Document Embedding Example ===\n');

  // Step 1: Embed all documents
  console.log('1. Embedding documents...');
  const contents = documents.map(d => d.content);
  const { embeddings } = await embedMany(contents);
  
  const embeddedDocs: EmbeddedDocument[] = documents.map((doc, i) => ({
    ...doc,
    embedding: embeddings[i]
  }));
  
  console.log(`   Embedded ${embeddedDocs.length} documents`);
  console.log(`   Embedding dimensions: ${embeddings[0].length}`);

  // Step 2: Search function
  async function search(query: string, topK: number = 3): Promise<Array<{ doc: EmbeddedDocument; score: number }>> {
    const { embedding: queryEmbedding } = await (await import('../../../src/praisonai-ts/dist/llm/embeddings')).embed(query);
    
    const results = embeddedDocs.map(doc => ({
      doc,
      score: cosineSimilarity(queryEmbedding, doc.embedding)
    }));
    
    return results
      .sort((a, b) => b.score - a.score)
      .slice(0, topK);
  }

  // Step 3: Test queries
  console.log('\n2. Testing search queries...\n');

  const queries = [
    'How do machines learn from data?',
    'What is image recognition?',
    'Tell me about chatbots and translation'
  ];

  for (const query of queries) {
    console.log(`Query: "${query}"`);
    const results = await search(query);
    
    console.log('Top results:');
    results.forEach((r, i) => {
      console.log(`  ${i + 1}. [${(r.score * 100).toFixed(1)}%] ${r.doc.title}`);
    });
    console.log('');
  }

  // Step 4: Show document similarity matrix
  console.log('3. Document Similarity Matrix');
  console.log('');
  
  // Header
  process.stdout.write('         ');
  documents.forEach((_, i) => process.stdout.write(`Doc${i + 1}  `));
  console.log('');
  
  // Matrix
  for (let i = 0; i < embeddedDocs.length; i++) {
    process.stdout.write(`Doc${i + 1}     `);
    for (let j = 0; j < embeddedDocs.length; j++) {
      const sim = cosineSimilarity(embeddedDocs[i].embedding, embeddedDocs[j].embedding);
      process.stdout.write(`${(sim * 100).toFixed(0).padStart(3)}%  `);
    }
    console.log('');
  }

  console.log('\n=== Complete ===');
}

main().catch(console.error);
