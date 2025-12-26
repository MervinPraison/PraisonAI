#!/usr/bin/env npx ts-node
/**
 * Comprehensive Feature Verification Script
 * Tests all implemented features with real API keys
 */

import {
  // Providers
  createProvider,
  isProviderAvailable,
  getAvailableProviders,
  
  // Session
  Session,
  SessionManager,
  getSessionManager,
  
  // Tools
  tool,
  ToolRegistry,
  getRegistry,
  
  // Database
  MemoryDbAdapter,
  db,
  
  // Workflows
  Workflow,
  parallel,
  route,
  loop,
  
  // Guardrails
  guardrail,
  GuardrailManager,
  builtinGuardrails,
  
  // Knowledge Base
  KnowledgeBase,
  createKnowledgeBase,
  
  // Evaluation
  accuracyEval,
  performanceEval,
  reliabilityEval,
  EvalSuite,
  
  // Observability
  MemoryObservabilityAdapter,
  ConsoleObservabilityAdapter,
  
  // Skills
  SkillManager,
  parseSkillFile,
  
  // Router
  RouterAgent,
  createRouter,
  routeConditions,
  
  // Handoff
  Handoff,
  handoff,
  handoffFilters,
} from '../../src';

console.log('='.repeat(60));
console.log('PraisonAI TypeScript - Comprehensive Feature Verification');
console.log('='.repeat(60));

let passed = 0;
let failed = 0;

async function test(name: string, fn: () => Promise<void>) {
  try {
    await fn();
    console.log(`✅ ${name}`);
    passed++;
  } catch (error: any) {
    console.log(`❌ ${name}: ${error.message}`);
    failed++;
  }
}

async function main() {
  // 1. Provider Tests
  console.log('\n--- 1. LLM Providers ---');
  
  await test('Provider availability check', async () => {
    const available = getAvailableProviders();
    if (!available.includes('openai')) throw new Error('OpenAI not available');
  });

  await test('OpenAI generateText', async () => {
    const provider = createProvider('openai/gpt-4o-mini');
    const result = await provider.generateText({
      messages: [{ role: 'user', content: 'Say "test" only' }]
    });
    if (!result.text) throw new Error('No response');
  });

  await test('OpenAI streaming', async () => {
    const provider = createProvider('openai/gpt-4o-mini');
    let text = '';
    const stream = await provider.streamText({
      messages: [{ role: 'user', content: 'Say "ok"' }],
      onToken: (t) => { text += t; }
    });
    // Consume the stream
    for await (const chunk of stream) {
      if (chunk.text) text += chunk.text;
    }
    if (!text) throw new Error('No streamed text');
  });

  await test('Anthropic generateText', async () => {
    const provider = createProvider('anthropic/claude-sonnet-4-20250514');
    const result = await provider.generateText({
      messages: [{ role: 'user', content: 'Say "test" only' }]
    });
    if (!result.text) throw new Error('No response');
  });

  // 2. Session Tests
  console.log('\n--- 2. Session Management ---');

  await test('Session creation', async () => {
    const session = new Session();
    if (!session.id) throw new Error('No session ID');
  });

  await test('Session messages', async () => {
    const session = new Session();
    session.addMessage({ role: 'user', content: 'Hello' });
    session.addMessage({ role: 'assistant', content: 'Hi' });
    const messages = session.getMessagesForLLM();
    if (messages.length !== 2) throw new Error('Wrong message count');
  });

  await test('Session runs', async () => {
    const session = new Session();
    const run = session.createRun().start();
    run.complete();
    if (run.status !== 'completed') throw new Error('Run not completed');
  });

  await test('SessionManager', async () => {
    const manager = getSessionManager();
    const session = manager.create({ id: 'test-session' });
    const retrieved = manager.get('test-session');
    if (!retrieved) throw new Error('Session not found');
    manager.delete('test-session');
  });

  // 3. Tool Tests
  console.log('\n--- 3. Tool System ---');

  await test('Tool creation', async () => {
    const myTool = tool({
      name: 'test_tool',
      description: 'A test tool',
      execute: async () => 'result'
    });
    const result = await myTool.execute({});
    if (result !== 'result') throw new Error('Wrong result');
  });

  await test('Tool registry', async () => {
    const registry = new ToolRegistry();
    registry.register(tool({ name: 'tool1', execute: async () => '1' }));
    registry.register(tool({ name: 'tool2', execute: async () => '2' }));
    if (registry.list().length !== 2) throw new Error('Wrong tool count');
  });

  await test('OpenAI tool format', async () => {
    const myTool = tool({
      name: 'calculator',
      description: 'Calculate',
      parameters: { type: 'object', properties: { expr: { type: 'string' } } },
      execute: async () => '42'
    });
    const format = myTool.toOpenAITool();
    if (format.type !== 'function') throw new Error('Wrong format');
  });

  // 4. Database Tests
  console.log('\n--- 4. Database Adapters ---');

  await test('Memory adapter', async () => {
    const adapter = new MemoryDbAdapter();
    await adapter.connect();
    await adapter.createSession({ id: 'test', createdAt: Date.now(), updatedAt: Date.now() });
    const session = await adapter.getSession('test');
    if (!session) throw new Error('Session not found');
    await adapter.disconnect();
  });

  await test('DB factory', async () => {
    const adapter = db({ type: 'memory' });
    await adapter.connect();
    if (!adapter.isConnected()) throw new Error('Not connected');
    await adapter.disconnect();
  });

  // 5. Workflow Tests
  console.log('\n--- 5. Workflows ---');

  await test('Basic workflow', async () => {
    const workflow = new Workflow<number, number>('test')
      .step('add', async (n) => n + 10)
      .step('multiply', async (n) => n * 2);
    const { output } = await workflow.run(5);
    if (output !== 30) throw new Error(`Expected 30, got ${output}`);
  });

  await test('Parallel execution', async () => {
    const results = await parallel([
      async () => 1,
      async () => 2,
      async () => 3
    ]);
    if (results.length !== 3) throw new Error('Wrong result count');
  });

  await test('Route helper', async () => {
    const result = await route([
      { condition: () => false, execute: async () => 'a' },
      { condition: () => true, execute: async () => 'b' }
    ]);
    if (result !== 'b') throw new Error('Wrong route');
  });

  // 6. Guardrails Tests
  console.log('\n--- 6. Guardrails ---');

  await test('Basic guardrail', async () => {
    const g = guardrail({
      name: 'test',
      check: (content) => ({ status: content.length > 0 ? 'passed' : 'failed' })
    });
    const result = await g.run('hello');
    if (result.status !== 'passed') throw new Error('Should pass');
  });

  await test('Built-in guardrails', async () => {
    const maxLen = builtinGuardrails.maxLength(10);
    const result = await maxLen.run('hello');
    if (result.status !== 'passed') throw new Error('Should pass');
  });

  await test('Guardrail manager', async () => {
    const manager = new GuardrailManager();
    manager.add(builtinGuardrails.minLength(1));
    manager.add(builtinGuardrails.maxLength(100));
    const { passed } = await manager.runAll('test');
    if (!passed) throw new Error('Should pass');
  });

  // 7. Knowledge Base Tests
  console.log('\n--- 7. Knowledge Base (RAG) ---');

  await test('Knowledge base add/search', async () => {
    const kb = createKnowledgeBase();
    await kb.add({ id: 'doc1', content: 'TypeScript is great' });
    await kb.add({ id: 'doc2', content: 'Python is also great' });
    const results = await kb.search('TypeScript');
    if (results.length === 0) throw new Error('No results');
  });

  await test('Knowledge base context', async () => {
    const kb = createKnowledgeBase();
    await kb.add({ id: 'doc1', content: 'Test document' });
    const results = await kb.search('test');
    const context = kb.buildContext(results);
    if (!context.includes('Test document')) throw new Error('Wrong context');
  });

  // 8. Evaluation Tests
  console.log('\n--- 8. Evaluation Framework ---');

  await test('Accuracy eval', async () => {
    const result = await accuracyEval({
      input: 'test',
      expectedOutput: 'hello world',
      actualOutput: 'hello world'
    });
    if (!result.passed) throw new Error('Should pass');
  });

  await test('Performance eval', async () => {
    const result = await performanceEval({
      func: async () => 'done',
      iterations: 3,
      warmupRuns: 1
    });
    if (result.times.length !== 3) throw new Error('Wrong iteration count');
  });

  await test('Reliability eval', async () => {
    const result = await reliabilityEval({
      expectedToolCalls: ['a', 'b'],
      actualToolCalls: ['a', 'b']
    });
    if (!result.passed) throw new Error('Should pass');
  });

  await test('Eval suite', async () => {
    const suite = new EvalSuite();
    await suite.runAccuracy('test', {
      input: 'x',
      expectedOutput: 'same',
      actualOutput: 'same'
    });
    const summary = suite.getSummary();
    if (summary.total !== 1) throw new Error('Wrong count');
  });

  // 9. Observability Tests
  console.log('\n--- 9. Observability ---');

  await test('Memory observability', async () => {
    const adapter = new MemoryObservabilityAdapter();
    const trace = adapter.startTrace('test');
    const span = trace.startSpan('operation', 'custom');
    span.end();
    trace.end();
    const traceData = adapter.getTrace(trace.traceId);
    if (!traceData) throw new Error('Trace not found');
  });

  // 10. Skills Tests
  console.log('\n--- 10. Skills System ---');

  await test('Parse skill file', async () => {
    const content = `---
name: test-skill
description: A test skill
---
# Instructions
Do something`;
    const skill = parseSkillFile(content);
    if (skill.metadata.name !== 'test-skill') throw new Error('Wrong name');
  });

  await test('Skill manager', async () => {
    const manager = new SkillManager({ paths: [] });
    manager.register({
      metadata: { name: 'manual-skill', description: 'Manual' },
      instructions: 'Do this'
    });
    const skill = manager.get('manual-skill');
    if (!skill) throw new Error('Skill not found');
  });

  // 11. Router Tests
  console.log('\n--- 11. Router Agent ---');

  await test('Route conditions', async () => {
    const kw = routeConditions.keywords(['math', 'calc']);
    if (!kw('I need math help')) throw new Error('Should match');
    if (kw('I need code help')) throw new Error('Should not match');
  });

  await test('Router creation', async () => {
    const router = createRouter({
      routes: [],
      name: 'TestRouter'
    });
    if (router.name !== 'TestRouter') throw new Error('Wrong name');
  });

  // 12. Handoff Tests
  console.log('\n--- 12. Handoff System ---');

  await test('Handoff filters', async () => {
    const topicFilter = handoffFilters.topic(['billing', 'payment']);
    if (!topicFilter({ messages: [], lastMessage: 'I have a billing question' })) {
      throw new Error('Should match');
    }
  });

  await test('Handoff creation', async () => {
    const mockAgent = { name: 'SupportAgent', chat: async () => ({ text: 'ok' }) } as any;
    const h = handoff({ agent: mockAgent, name: 'support_handoff' });
    if (h.name !== 'support_handoff') throw new Error('Wrong name');
  });

  // 13. Memory Tests
  console.log('\n--- 13. Memory System ---');

  await test('Memory add/get', async () => {
    const { Memory } = await import('../../src/memory/memory');
    const mem = new Memory();
    await mem.add('Hello', 'user');
    await mem.add('Hi there', 'assistant');
    if (mem.size !== 2) throw new Error('Wrong size');
  });

  await test('Memory search', async () => {
    const { Memory } = await import('../../src/memory/memory');
    const mem = new Memory();
    await mem.add('TypeScript is great', 'user');
    await mem.add('Python is also good', 'user');
    const results = await mem.search('TypeScript');
    if (results.length === 0) throw new Error('No results');
  });

  // 14. Telemetry Tests
  console.log('\n--- 14. Telemetry ---');

  await test('Telemetry collector', async () => {
    const { TelemetryCollector } = await import('../../src/telemetry');
    const collector = new TelemetryCollector({ enabled: true });
    collector.track('test_event', { key: 'value' });
    if (collector.getPendingCount() !== 1) throw new Error('Event not tracked');
    collector.disable();
  });

  // 15. AutoAgents Tests
  console.log('\n--- 15. AutoAgents ---');

  await test('AutoAgents creation', async () => {
    const { AutoAgents } = await import('../../src/auto');
    const auto = new AutoAgents({ singleAgent: true });
    const complexity = auto.analyzeComplexity('Simple task');
    if (complexity !== 'simple') throw new Error('Wrong complexity');
  });

  await test('AutoAgents pattern recommendation', async () => {
    const { AutoAgents } = await import('../../src/auto');
    const auto = new AutoAgents();
    const pattern = auto.recommendPattern('Run tasks in parallel');
    if (pattern !== 'parallel') throw new Error('Wrong pattern');
  });

  // 16. ImageAgent Tests
  console.log('\n--- 16. ImageAgent ---');

  await test('ImageAgent creation', async () => {
    const { ImageAgent } = await import('../../src/agent/image');
    const agent = new ImageAgent({ name: 'TestImageAgent' });
    if (agent.name !== 'TestImageAgent') throw new Error('Wrong name');
  });

  // 17. DeepResearchAgent Tests
  console.log('\n--- 17. DeepResearchAgent ---');

  await test('DeepResearchAgent creation', async () => {
    const { DeepResearchAgent } = await import('../../src/agent/research');
    const agent = new DeepResearchAgent({ name: 'TestResearcher' });
    if (agent.name !== 'TestResearcher') throw new Error('Wrong name');
  });

  // 18. QueryRewriterAgent Tests
  console.log('\n--- 18. QueryRewriterAgent ---');

  await test('QueryRewriterAgent creation', async () => {
    const { QueryRewriterAgent } = await import('../../src/agent/query-rewriter');
    const agent = new QueryRewriterAgent({ name: 'TestRewriter' });
    if (agent.name !== 'TestRewriter') throw new Error('Wrong name');
  });

  // 19. PromptExpanderAgent Tests
  console.log('\n--- 19. PromptExpanderAgent ---');

  await test('PromptExpanderAgent creation', async () => {
    const { PromptExpanderAgent } = await import('../../src/agent/prompt-expander');
    const agent = new PromptExpanderAgent({ name: 'TestExpander' });
    if (agent.name !== 'TestExpander') throw new Error('Wrong name');
  });

  await test('PromptExpanderAgent strategy detection', async () => {
    const { PromptExpanderAgent } = await import('../../src/agent/prompt-expander');
    const agent = new PromptExpanderAgent();
    const strategy = agent.detectStrategy('Write code');
    if (strategy !== 'detail') throw new Error('Wrong strategy');
  });

  // 20. Chunking Tests
  console.log('\n--- 20. Chunking ---');

  await test('Chunking by size', async () => {
    const { Chunking } = await import('../../src/knowledge/chunking');
    const chunker = new Chunking({ chunkSize: 100, overlap: 20 });
    const chunks = chunker.chunk('A'.repeat(250));
    if (chunks.length < 2) throw new Error('Should have multiple chunks');
  });

  await test('Chunking by sentence', async () => {
    const { Chunking } = await import('../../src/knowledge/chunking');
    const chunker = new Chunking({ strategy: 'sentence' });
    const chunks = chunker.chunkBySentence('First. Second. Third.');
    if (chunks.length !== 3) throw new Error('Should have 3 chunks');
  });

  // 21. LLMGuardrail Tests
  console.log('\n--- 21. LLMGuardrail ---');

  await test('LLMGuardrail creation', async () => {
    const { LLMGuardrail } = await import('../../src/guardrails/llm-guardrail');
    const guard = new LLMGuardrail({ name: 'test', criteria: 'Must be polite' });
    if (guard.name !== 'test') throw new Error('Wrong name');
  });

  // 22. Planning Tests
  console.log('\n--- 22. Planning ---');

  await test('Plan creation', async () => {
    const { Plan, PlanStep } = await import('../../src/planning');
    const plan = new Plan({ name: 'Test Plan' });
    plan.addStep(new PlanStep({ description: 'Step 1' }));
    if (plan.steps.length !== 1) throw new Error('Should have 1 step');
  });

  await test('TodoList', async () => {
    const { TodoList, TodoItem } = await import('../../src/planning');
    const todos = new TodoList();
    todos.add(new TodoItem({ content: 'Task 1' }));
    todos.add(new TodoItem({ content: 'Task 2' }));
    if (todos.items.length !== 2) throw new Error('Should have 2 items');
  });

  // Summary
  console.log('\n' + '='.repeat(60));
  console.log(`RESULTS: ${passed} passed, ${failed} failed`);
  console.log('='.repeat(60));

  if (failed > 0) {
    process.exit(1);
  }
}

main().catch(console.error);
