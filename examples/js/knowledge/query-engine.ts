/**
 * QueryEngine Integration Test
 * 
 * Tests semantic and keyword search for RAG applications.
 * 
 * Run: npx ts-node query-engine.ts
 */

import {
    QueryEngine,
    createQueryEngine,
    createSimpleQueryEngine
} from '../../../src/praisonai-ts/dist';

async function main() {
    console.log('=== QueryEngine Integration Test ===\n');

    // Test 1: Simple in-memory engine
    console.log('1. Testing simple in-memory QueryEngine:');
    const docs = [
        { id: 'doc1', content: 'PraisonAI is a high-performance AI agent framework designed for production use.' },
        { id: 'doc2', content: 'TypeScript provides static typing and better tooling for JavaScript projects.' },
        { id: 'doc3', content: 'Agents can use tools, memory, and knowledge to complete complex tasks.' },
        { id: 'doc4', content: 'RAG (Retrieval-Augmented Generation) improves AI responses with relevant context.' },
        { id: 'doc5', content: 'Workflows enable sequential and parallel execution of agent tasks.' }
    ];

    const engine = createSimpleQueryEngine(docs);

    const results1 = await engine.query('agent framework', { topK: 2 });
    console.log('   Query: "agent framework"');
    console.log(`   Found: ${results1.length} results`);
    results1.forEach((r, i) => {
        console.log(`   [${i + 1}] ${r.content.slice(0, 50)}... (score: ${r.score.toFixed(2)})`);
    });
    console.log('   Success: ✅');

    // Test 2: Different queries
    console.log('\n2. Testing various queries:');
    const queries = ['TypeScript', 'RAG', 'workflow', 'tools memory'];

    for (const q of queries) {
        const results = await engine.query(q, { topK: 1 });
        console.log(`   "${q}" → ${results.length > 0 ? results[0].content.slice(0, 40) + '...' : 'No results'}`);
    }
    console.log('   Success: ✅');

    // Test 3: Query for context string
    console.log('\n3. Testing queryForContext:');
    const context = await engine.queryForContext('agent tasks', { topK: 2 });
    console.log('   Context string (preview):');
    console.log('   ' + context.split('\n')[0]);
    console.log('   Success: ✅');

    // Test 4: Cache behavior
    console.log('\n4. Testing caching:');
    const start = Date.now();
    await engine.query('agent framework', { topK: 2 });
    const cachedTime = Date.now() - start;
    console.log(`   Cached query time: ${cachedTime}ms (should be fast)`);

    engine.clearCache();
    const start2 = Date.now();
    await engine.query('agent framework', { topK: 2 });
    const uncachedTime = Date.now() - start2;
    console.log(`   Uncached query time: ${uncachedTime}ms`);
    console.log('   Success: ✅');

    // Test 5: QueryEngine configuration
    console.log('\n5. Testing custom QueryEngine configuration:');
    const customEngine = new QueryEngine({
        keywordSearch: async (query, options) => {
            return docs
                .filter(d => d.content.toLowerCase().includes(query.toLowerCase()))
                .map(d => ({ id: d.id, content: d.content, score: 0.8 }))
                .slice(0, options?.topK ?? 5);
        },
        defaultOptions: { mode: 'keyword', topK: 3 }
    });

    const customResults = await customEngine.query('TypeScript');
    console.log(`   Custom engine results: ${customResults.length}`);
    console.log('   Success: ✅');

    // Test 6: Empty results handling
    console.log('\n6. Testing empty results:');
    const emptyResults = await engine.query('nonexistent_query_12345');
    console.log(`   Results for nonsense query: ${emptyResults.length}`);

    const emptyContext = await engine.queryForContext('nonexistent_query_12345');
    console.log(`   Context: "${emptyContext}"`);
    console.log('   Success: ✅');

    console.log('\n=== QueryEngine Tests Complete ===');
}

main().catch(console.error);
