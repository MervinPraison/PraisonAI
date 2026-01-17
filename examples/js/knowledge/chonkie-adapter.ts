/**
 * ChonkieAdapter Integration Test
 * 
 * Tests the ChonkieJS adapter for text chunking.
 * Works without ChonkieJS installed (uses native fallback).
 * 
 * Run: npx ts-node chonkie-adapter.ts
 */

import {
  ChonkieAdapter,
  createChonkieAdapter,
  hasChonkie,
  Chunking
} from '../../../src/praisonai-ts/dist';

async function main() {
  console.log('=== ChonkieAdapter Integration Test ===\n');

  // Test 1: Check ChonkieJS availability
  console.log('1. Checking ChonkieJS availability:');
  const chonkieAvailable = await hasChonkie();
  console.log(`   ChonkieJS installed: ${chonkieAvailable ? '✅' : '❌ (using native fallback)'}`);

  // Test 2: Create adapter with default config
  console.log('\n2. Testing ChonkieAdapter creation:');
  const adapter = new ChonkieAdapter({
    strategy: 'token',
    chunkSize: 100,
    overlap: 20
  });
  console.log('   Adapter created: ✅');
  console.log('   Info:', adapter.getInfo());

  // Test 3: Chunk text
  console.log('\n3. Testing text chunking:');
  const sampleText = `
    PraisonAI is a high-performance, agentic AI framework designed with minimal client-side API.
    It features extreme performance sensitivity, lazy loading everywhere, and optional dependencies only.
    The framework supports clean separation between Core SDK, Wrapper/integrations, and Tools/plugins.
    All features must have a relevant CLI integration and representation.
  `.trim();

  const chunks = await adapter.chunk(sampleText);
  console.log(`   Input length: ${sampleText.length} characters`);
  console.log(`   Chunks created: ${chunks.length}`);
  chunks.forEach((chunk, i) => {
    console.log(`   [${i}]: "${chunk.content.slice(0, 50)}..." (${chunk.content.length} chars)`);
  });
  console.log('   Success: ✅');

  // Test 4: Different strategies
  console.log('\n4. Testing different chunking strategies:');
  const strategies = ['size', 'sentence', 'paragraph', 'semantic'] as const;

  for (const strategy of strategies) {
    const strategyAdapter = createChonkieAdapter({ strategy, chunkSize: 80 });
    const strategyChunks = await strategyAdapter.chunk(sampleText);
    console.log(`   ${strategy}: ${strategyChunks.length} chunks`);
  }
  console.log('   Success: ✅');

  // Test 5: Native Chunking class
  console.log('\n5. Testing native Chunking class:');
  const nativeChunker = new Chunking({ chunkSize: 100, overlap: 10, strategy: 'sentence' });
  const nativeChunks = nativeChunker.chunk(sampleText);
  console.log(`   Native chunks: ${nativeChunks.length}`);
  console.log('   Success: ✅');

  // Test 6: Factory function
  console.log('\n6. Testing createChunking() factory:');
  const factoryChunker = createChunking({ chunkSize: 200 });
  const factoryChunks = factoryChunker.chunk(sampleText);
  console.log(`   Factory chunks: ${factoryChunks.length}`);
  console.log('   Success: ✅');

  // Test 7: Merge small chunks
  console.log('\n7. Testing mergeSmallChunks:');
  const tinyChunker = new Chunking({ chunkSize: 20, overlap: 5 });
  const tinyChunks = tinyChunker.chunk(sampleText);
  const mergedChunks = tinyChunker.mergeSmallChunks(tinyChunks, 50);
  console.log(`   Before merge: ${tinyChunks.length} chunks`);
  console.log(`   After merge: ${mergedChunks.length} chunks`);
  console.log('   Success: ✅');

  // Test 8: Code chunking (if ChonkieJS available)
  if (chonkieAvailable) {
    console.log('\n8. Testing code chunking (ChonkieJS):');
    const codeAdapter = createChonkieAdapter({ strategy: 'code', language: 'typescript' });
    const codeText = `
function hello() {
  console.log('Hello');
}

class MyClass {
  constructor() {
    this.value = 42;
  }
  
  getValue() {
    return this.value;
  }
}
    `.trim();

    const codeChunks = await codeAdapter.chunk(codeText);
    console.log(`   Code chunks: ${codeChunks.length}`);
    console.log('   Success: ✅');
  } else {
    console.log('\n8. Code chunking: Skipped (ChonkieJS not installed)');
  }

  // Test 9: Verify adapter info
  console.log('\n9. Verifying adapter state:');
  const info = adapter.getInfo();
  console.log(`   Strategy: ${info.strategy}`);
  console.log(`   Using ChonkieJS: ${info.usingChonkie}`);
  console.log(`   Chunk size: ${info.config.chunkSize}`);
  console.log('   Success: ✅');

  console.log('\n=== ChonkieAdapter Tests Complete ===');
}

main().catch(console.error);
