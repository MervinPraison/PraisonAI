/**
 * Real Agent Integration Test
 * Tests actual agent execution with real API calls
 * 
 * Run with: npx ts-node examples/real-agent-test.ts
 */

import { Agent, tool } from '../src';

async function testBasicAgent() {
  console.log('\n🔹 Test 1: Basic Agent with simple prompt');
  console.log('─'.repeat(50));
  
  const agent = new Agent({
    name: 'BasicAgent',
    instructions: 'You are a helpful assistant. Keep responses brief.',
    llm: 'gpt-4o-mini',
    verbose: false,
  });
  
  const response = await agent.start('What is 2 + 2? Answer with just the number.');
  console.log(`Response: ${response}`);
  return response.includes('4');
}

async function testAgentWithTool() {
  console.log('\n🔹 Test 2: Agent with custom tool');
  console.log('─'.repeat(50));
  
  const calculatorTool = tool({
    name: 'calculator',
    description: 'Performs basic math calculations',
    parameters: {
      type: 'object',
      properties: {
        expression: { type: 'string', description: 'Math expression to evaluate' }
      },
      required: ['expression']
    },
    execute: ({ expression }: { expression: string }) => {
      try {
        // Simple eval for demo (in production, use a proper math parser)
        const result = Function(`"use strict"; return (${expression})`)();
        return `Result: ${result}`;
      } catch (e) {
        return `Error: Invalid expression`;
      }
    }
  });
  
  const agent = new Agent({
    name: 'MathAgent',
    instructions: 'You are a math assistant. Use the calculator tool for calculations.',
    llm: 'gpt-4o-mini',
    tools: [calculatorTool],
    verbose: false,
  });
  
  const response = await agent.start('Calculate 15 * 7 using the calculator tool');
  console.log(`Response: ${response}`);
  return response.includes('105');
}

async function testMultiTurnConversation() {
  console.log('\n🔹 Test 3: Multi-turn conversation');
  console.log('─'.repeat(50));
  
  const agent = new Agent({
    name: 'ConversationAgent',
    instructions: 'You are a helpful assistant. Remember context from previous messages.',
    llm: 'gpt-4o-mini',
    verbose: false,
  });
  
  console.log('Turn 1: Setting context...');
  const response1 = await agent.chat('My name is Alice. Remember this.');
  console.log(`Response 1: ${response1}`);
  
  console.log('\nTurn 2: Testing memory...');
  const response2 = await agent.chat('What is my name?');
  console.log(`Response 2: ${response2}`);
  
  return response2.toLowerCase().includes('alice');
}

async function testStreamingAgent() {
  console.log('\n🔹 Test 4: Streaming response');
  console.log('─'.repeat(50));
  
  const agent = new Agent({
    name: 'StreamAgent',
    instructions: 'You are a helpful assistant.',
    llm: 'gpt-4o-mini',
    stream: true,
    verbose: false,
  });
  
  console.log('Streaming response:');
  let fullResponse = '';
  
  // Use start which handles streaming internally
  const response = await agent.start('Count from 1 to 5, one number per line.');
  fullResponse = response;
  console.log(`\nFull response: ${fullResponse}`);
  
  return fullResponse.includes('1') && fullResponse.includes('5');
}

async function main() {
  console.log('╔════════════════════════════════════════════════════════════╗');
  console.log('║      PRAISONAI TYPESCRIPT - REAL AGENT INTEGRATION TEST    ║');
  console.log('╚════════════════════════════════════════════════════════════╝');
  
  if (!process.env.OPENAI_API_KEY) {
    console.log('\n❌ OPENAI_API_KEY not set. Skipping real API tests.');
    process.exit(1);
  }
  
  const results: { test: string; passed: boolean }[] = [];
  
  try {
    results.push({ test: 'Basic Agent', passed: await testBasicAgent() });
  } catch (e: any) {
    console.error(`Error: ${e.message}`);
    results.push({ test: 'Basic Agent', passed: false });
  }
  
  try {
    results.push({ test: 'Agent with Tool', passed: await testAgentWithTool() });
  } catch (e: any) {
    console.error(`Error: ${e.message}`);
    results.push({ test: 'Agent with Tool', passed: false });
  }
  
  try {
    results.push({ test: 'Multi-turn Conversation', passed: await testMultiTurnConversation() });
  } catch (e: any) {
    console.error(`Error: ${e.message}`);
    results.push({ test: 'Multi-turn Conversation', passed: false });
  }
  
  try {
    results.push({ test: 'Streaming Agent', passed: await testStreamingAgent() });
  } catch (e: any) {
    console.error(`Error: ${e.message}`);
    results.push({ test: 'Streaming Agent', passed: false });
  }
  
  // Summary
  console.log('\n╔════════════════════════════════════════════════════════════╗');
  console.log('║                      TEST SUMMARY                          ║');
  console.log('╚════════════════════════════════════════════════════════════╝\n');
  
  results.forEach(r => {
    const icon = r.passed ? '✅' : '❌';
    console.log(`${icon} ${r.test}: ${r.passed ? 'PASSED' : 'FAILED'}`);
  });
  
  const passed = results.filter(r => r.passed).length;
  const total = results.length;
  console.log(`\nTotal: ${passed}/${total} tests passed`);
  
  process.exit(passed === total ? 0 : 1);
}

main().catch(console.error);
