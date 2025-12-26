/**
 * Pinecone Vector Store Example
 */

import { createPineconeStore } from 'praisonai';

async function main() {
  const pinecone = createPineconeStore({
    apiKey: process.env.PINECONE_API_KEY!
  });

  const indexName = 'test-index';

  // Create index
  console.log('Creating index...');
  await pinecone.createIndex({
    indexName,
    dimension: 3,
    metric: 'cosine'
  });

  // List indexes
  const indexes = await pinecone.listIndexes();
  console.log('Indexes:', indexes);

  // Upsert vectors
  console.log('Upserting vectors...');
  await pinecone.upsert({
    indexName,
    vectors: [
      { id: 'vec-1', vector: [0.1, 0.2, 0.3], metadata: { category: 'A' } },
      { id: 'vec-2', vector: [0.4, 0.5, 0.6], metadata: { category: 'B' } },
      { id: 'vec-3', vector: [0.7, 0.8, 0.9], metadata: { category: 'A' } }
    ]
  });

  // Query
  console.log('Querying...');
  const results = await pinecone.query({
    indexName,
    vector: [0.1, 0.2, 0.3],
    topK: 2,
    includeMetadata: true
  });

  console.log('Results:');
  for (const r of results) {
    console.log(`  ${r.id}: score=${r.score.toFixed(4)}, metadata=${JSON.stringify(r.metadata)}`);
  }

  // Cleanup
  console.log('Deleting index...');
  await pinecone.deleteIndex(indexName);
  console.log('Done!');
}

main().catch(console.error);
