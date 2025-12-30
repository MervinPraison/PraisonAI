/**
 * Retrieval Example - Simple Vector Search
 * 
 * Demonstrates building a simple retrieval system with embeddings
 * 
 * Run: npx ts-node examples/js/embeddings/retrieval.ts
 */

import { embed, embedMany, cosineSimilarity } from '../../../src/praisonai-ts/dist/llm/embeddings';

interface Document {
  id: string;
  content: string;
  embedding?: number[];
}

interface SearchResult {
  document: Document;
  score: number;
}

// Simple in-memory vector store
class SimpleVectorStore {
  private documents: Document[] = [];

  async add(doc: Document): Promise<void> {
    const { embedding } = await embed(doc.content);
    this.documents.push({ ...doc, embedding });
  }

  async addBatch(docs: Document[]): Promise<void> {
    const contents = docs.map(d => d.content);
    const { embeddings } = await embedMany(contents);
    docs.forEach((doc, i) => {
      this.documents.push({ ...doc, embedding: embeddings[i] });
    });
  }

  async search(query: string, topK: number = 3): Promise<SearchResult[]> {
    const { embedding: queryEmb } = await embed(query);
    
    const results = this.documents
      .filter(doc => doc.embedding)
      .map(doc => ({
        document: doc,
        score: cosineSimilarity(queryEmb, doc.embedding!)
      }))
      .sort((a, b) => b.score - a.score)
      .slice(0, topK);
    
    return results;
  }

  get(id: string): Document | undefined {
    return this.documents.find(d => d.id === id);
  }

  delete(id: string): boolean {
    const idx = this.documents.findIndex(d => d.id === id);
    if (idx >= 0) {
      this.documents.splice(idx, 1);
      return true;
    }
    return false;
  }
}

async function main() {
  console.log('=== Simple Vector Retrieval ===\n');

  // Create vector store
  console.log('1. Creating vector store...');
  const store = new SimpleVectorStore();

  // Add documents
  console.log('2. Adding documents...');
  const docs: Document[] = [
    { id: '1', content: 'PraisonAI is an AI agent framework for building intelligent applications.' },
    { id: '2', content: 'Agents can use tools to interact with external systems and APIs.' },
    { id: '3', content: 'Workflows allow orchestrating multiple agents in sequence or parallel.' },
    { id: '4', content: 'Memory systems help agents maintain context across conversations.' },
    { id: '5', content: 'The AI SDK provides a unified interface for multiple LLM providers.' },
    { id: '6', content: 'Embeddings enable semantic search and similarity matching.' },
    { id: '7', content: 'Guardrails ensure agent outputs meet safety and quality standards.' },
    { id: '8', content: 'Sessions persist conversation state for multi-turn interactions.' }
  ];

  await store.addBatch(docs);
  console.log(`   Added ${docs.length} documents`);

  // Search queries
  console.log('\n3. Running search queries...\n');

  const queries = [
    'How do I build an AI application?',
    'Can agents call external APIs?',
    'How to maintain conversation context?',
    'What providers are supported?'
  ];

  for (const query of queries) {
    console.log(`Query: "${query}"`);
    const results = await store.search(query);
    
    if (results.length > 0) {
      console.log('Results:');
      results.forEach((r, i) => {
        console.log(`  ${i + 1}. [${(r.score * 100).toFixed(1)}%] ${r.document.content.substring(0, 60)}...`);
      });
    } else {
      console.log('  No results found');
    }
    console.log('');
  }

  // Get specific document
  console.log('4. Get document by ID...');
  const doc = store.get('5');
  if (doc) {
    console.log(`   Found: ${doc.content}`);
  }

  // Delete document
  console.log('\n5. Delete document...');
  const deleted = store.delete('8');
  console.log(`   Deleted doc 8: ${deleted}`);

  console.log('\n=== Complete ===');
}

main().catch(console.error);
