/**
 * Real API Smoke Test - Run outside Jest to avoid mocks
 * 
 * Usage: npx ts-node tests/integration/real-api-smoke.ts
 */

import { Agent } from '../../src';

async function runSmokeTests() {
  console.log('🔥 Running Real API Smoke Tests\n');
  
  const OPENAI_KEY = process.env.OPENAI_API_KEY;
  
  if (!OPENAI_KEY) {
    console.log('⚠️  OPENAI_API_KEY not set - skipping real API tests');
    process.exit(0);
  }
  
  console.log('✅ OPENAI_API_KEY detected (masked)');
  
  let passed = 0;
  let failed = 0;
  
  // Test 1: Simple chat
  console.log('\n📝 Test 1: Simple Agent.chat()');
  try {
    const agent = new Agent({
      instructions: 'You are a helpful assistant. Be very brief.',
      llm: 'gpt-4o-mini',
      stream: false,
      verbose: false
    });
    
    const response = await agent.chat('Say "hello" and nothing else.');
    
    if (response && response.toLowerCase().includes('hello')) {
      console.log('   ✅ PASSED - Response contains "hello"');
      passed++;
    } else {
      console.log(`   ❌ FAILED - Response: "${response}"`);
      failed++;
    }
  } catch (error: any) {
    console.log(`   ❌ FAILED - Error: ${error.message}`);
    failed++;
  }
  
  // Test 2: Tool calling
  console.log('\n📝 Test 2: Agent with tool calling');
  try {
    const getWeather = (city: string) => `Weather in ${city}: 22°C, Sunny`;
    
    const agent = new Agent({
      instructions: 'You are a weather assistant. Use the getWeather tool to answer weather questions.',
      llm: 'gpt-4o-mini',
      stream: false,
      verbose: false,
      tools: [getWeather]
    });
    
    const response = await agent.chat('What is the weather in Paris?');
    
    if (response && /paris|22|sunny|weather/i.test(response)) {
      console.log('   ✅ PASSED - Response mentions weather data');
      passed++;
    } else {
      console.log(`   ❌ FAILED - Response: "${response}"`);
      failed++;
    }
  } catch (error: any) {
    console.log(`   ❌ FAILED - Error: ${error.message}`);
    failed++;
  }
  
  // Test 3: Session ID
  console.log('\n📝 Test 3: Session ID generation');
  try {
    const agent1 = new Agent({ instructions: 'Test' });
    const agent2 = new Agent({ instructions: 'Test' });
    
    if (agent1.getSessionId() !== agent2.getSessionId()) {
      console.log('   ✅ PASSED - Unique session IDs generated');
      passed++;
    } else {
      console.log('   ❌ FAILED - Session IDs are not unique');
      failed++;
    }
  } catch (error: any) {
    console.log(`   ❌ FAILED - Error: ${error.message}`);
    failed++;
  }
  
  // Summary
  console.log('\n' + '='.repeat(50));
  console.log(`📊 Results: ${passed} passed, ${failed} failed`);
  console.log('='.repeat(50));
  
  process.exit(failed > 0 ? 1 : 0);
}

runSmokeTests().catch(console.error);
