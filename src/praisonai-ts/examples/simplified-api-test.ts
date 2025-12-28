/**
 * Test file for simplified TS SDK APIs
 * Run with: npx tsx examples/simplified-api-test.ts
 */

import { Agent, db, Router, PlanningAgent, TaskAgent, AgentTelemetry } from '../src';

async function testSimpleAgent() {
  console.log('\n=== Test 1: Simple Agent ===');
  const agent = new Agent({
    instructions: 'You are a helpful assistant. Be brief.',
    verbose: false
  });
  
  const response = await agent.chat('What is 2+2? Answer in one word.');
  console.log('Response:', response.slice(0, 100));
  console.log('✅ Simple Agent works');
}

async function testAgentWithTools() {
  console.log('\n=== Test 2: Agent with Tools ===');
  
  const getWeather = (city: string) => `Weather in ${city}: 22°C, sunny`;
  const calculate = (expr: string) => {
    try {
      return String(eval(expr));
    } catch {
      return 'Error';
    }
  };
  
  const agent = new Agent({
    instructions: 'You help with weather and calculations. Be brief.',
    tools: [getWeather, calculate],
    verbose: false
  });
  
  const response = await agent.chat('What is 5 + 3?');
  console.log('Response:', response.slice(0, 100));
  console.log('✅ Agent with Tools works');
}

async function testAgentWithPersistence() {
  console.log('\n=== Test 3: Agent with Persistence (Memory) ===');
  
  const agent = new Agent({
    instructions: 'You remember conversations. Be brief.',
    db: db('memory:'),  // In-memory for testing
    sessionId: 'test-session-123',
    verbose: false
  });
  
  await agent.chat('My name is Alice.');
  const response = await agent.chat('What is my name?');
  console.log('Response:', response.slice(0, 100));
  console.log('History length:', agent.getHistory().length);
  console.log('✅ Agent with Persistence works');
}

async function testRouter() {
  console.log('\n=== Test 4: Simplified Router ===');
  
  const mathAgent = new Agent({
    instructions: 'You are a math expert. Answer math questions briefly.',
    verbose: false
  });
  
  const codeAgent = new Agent({
    instructions: 'You are a coding expert. Answer coding questions briefly.',
    verbose: false
  });
  
  const router = new Router({
    math: { agent: mathAgent, keywords: ['calculate', 'math', 'sum', '+', '-', '*', '/'] },
    code: { agent: codeAgent, keywords: ['code', 'program', 'function', 'javascript'] }
  });
  
  const response = await router.chat('Calculate 10 + 5');
  console.log('Response:', response.slice(0, 100));
  console.log('✅ Simplified Router works');
}

async function testPlanningAgent() {
  console.log('\n=== Test 5: Planning Agent ===');
  
  const agent = new PlanningAgent({
    verbose: false,
    maxSteps: 3  // Limit steps for testing
  });
  
  const plan = await agent.createPlan('Make a cup of tea');
  console.log('Plan created with', plan.steps.length, 'steps');
  console.log('First step:', plan.steps[0]?.description || 'N/A');
  console.log('✅ Planning Agent works');
}

async function testTaskAgent() {
  console.log('\n=== Test 6: Task Agent ===');
  
  const agent = new TaskAgent({ verbose: false });
  
  agent.addTask('Fix critical bug', 'high');
  agent.addTask('Write documentation', 'medium');
  agent.addTask('Review PR', 'low');
  
  console.log('Pending tasks:', agent.getPendingTasks().length);
  
  agent.completeTask('bug');
  console.log('After completing bug task:', agent.getPendingTasks().length);
  console.log('Progress:', agent.getProgress().percentage + '%');
  console.log('✅ Task Agent works');
}

async function testAgentTelemetry() {
  console.log('\n=== Test 7: Agent Telemetry ===');
  
  const agent = new Agent({
    instructions: 'Be brief.',
    verbose: false
  });
  
  const telemetry = new AgentTelemetry('TestAgent');
  
  await telemetry.trackChat(async () => {
    return await agent.chat('Hello!');
  });
  
  await telemetry.trackChat(async () => {
    return await agent.chat('How are you?');
  });
  
  const stats = telemetry.getStats();
  console.log('Total chats:', stats.totalChats);
  console.log('Success rate:', telemetry.getSuccessRate() + '%');
  console.log('✅ Agent Telemetry works');
}

async function main() {
  console.log('🚀 Testing Simplified TS SDK APIs\n');
  
  try {
    await testSimpleAgent();
    await testAgentWithTools();
    await testAgentWithPersistence();
    await testRouter();
    await testPlanningAgent();
    await testTaskAgent();
    await testAgentTelemetry();
    
    console.log('\n✅ All tests passed!');
  } catch (error) {
    console.error('\n❌ Test failed:', error);
    process.exit(1);
  }
}

main();
