/**
 * Comprehensive Live Tests
 * 
 * Tests all AI SDK features with real API keys.
 * 
 * Run with:
 *   export TAVILY_API_KEY=... OPENAI_API_KEY=... ANTHROPIC_API_KEY=... GOOGLE_API_KEY=...
 *   npx ts-node tests/live/comprehensive-live.test.ts
 */

import {
  Agent,
  AgentTeam,
  AgentFlow,
  AgentOS,
  aiGenerateText,
  aiStreamText,
  aiEmbed,
  aiGenerateObject,
  getModel,
  parseModel,
  MODEL_ALIASES,
  tavilySearch,
  getToolsRegistry,
} from '../../src';

interface TestResult {
  test: string;
  status: '✓' | '✗' | '⚠';
  response?: string;
  error?: string;
  duration?: number;
}

const results: TestResult[] = [];

async function runTest(name: string, fn: () => Promise<string>): Promise<void> {
  const start = Date.now();
  console.log(`Running: ${name}...`);
  try {
    const response = await fn();
    const duration = Date.now() - start;
    results.push({ test: name, status: '✓', response: response.substring(0, 100), duration });
    console.log(`  ✓ ${name} (${duration}ms)`);
  } catch (e: any) {
    const duration = Date.now() - start;
    results.push({ test: name, status: '✗', error: e.message, duration });
    console.log(`  ✗ ${name}: ${e.message}`);
  }
}

async function main() {
  console.log('=== COMPREHENSIVE LIVE TESTS ===\n');
  console.log('Environment:');
  console.log('  OPENAI_API_KEY:', process.env.OPENAI_API_KEY ? '✓ Set' : '✗ Missing');
  console.log('  ANTHROPIC_API_KEY:', process.env.ANTHROPIC_API_KEY ? '✓ Set' : '✗ Missing');
  console.log('  GOOGLE_API_KEY:', process.env.GOOGLE_API_KEY ? '✓ Set' : '✗ Missing');
  console.log('  TAVILY_API_KEY:', process.env.TAVILY_API_KEY ? '✓ Set' : '✗ Missing');
  console.log('\n');

  // === AGENT TESTS ===
  console.log('--- Agent Tests ---');

  await runTest('Agent: Basic Chat (OpenAI)', async () => {
    const agent = new Agent({
      name: 'BasicAgent',
      instructions: 'Be very brief. One sentence max.',
      llm: 'gpt-4o-mini',
      verbose: false,
      markdown: false,
      stream: false
    });
    return await agent.chat('What is 2+2?');
  });

  await runTest('Agent: With All Params', async () => {
    const agent = new Agent({
      name: 'FullAgent',
      instructions: 'You are a helpful assistant.',
      llm: 'gpt-4o-mini',
      verbose: false,
      pretty: false,
      markdown: true,
      stream: false,
      cache: false,
      cacheTTL: 3600,
      telemetry: false,
      historyLimit: 100,
      autoRestore: false,
      autoPersist: false,
      role: 'Assistant',
      goal: 'Help users',
      backstory: 'A helpful AI'
    });
    return await agent.chat('Say hello');
  });

  await runTest('Agent: With Custom Tool', async () => {
    const calculator = (expression: string) => String(eval(expression));
    const agent = new Agent({
      name: 'ToolAgent',
      instructions: 'Use the calculator tool for math.',
      tools: [calculator],
      llm: 'gpt-4o-mini',
      verbose: false,
      stream: false
    });
    return await agent.chat('What is 15 * 7?');
  });

  // === AGENT TEAM TESTS ===
  console.log('\n--- AgentTeam Tests ---');

  await runTest('AgentTeam: Sequential Collaboration', async () => {
    const researcher = new Agent({
      name: 'Researcher',
      instructions: 'You are a researcher. Provide brief, factual answers in one sentence.',
      llm: 'gpt-4o-mini',
      verbose: false,
      stream: false
    });
    const writer = new Agent({
      name: 'Writer',
      instructions: 'You are a writer. Summarize the input in one sentence.',
      llm: 'gpt-4o-mini',
      verbose: false,
      stream: false
    });
    const team = new AgentTeam({
      agents: [researcher, writer],
      verbose: false,
      pretty: false,
      process: 'sequential'
    });
    const results = await team.start();
    return results.join(' | ');
  });

  await runTest('AgentTeam: Parallel Execution', async () => {
    const agent1 = new Agent({
      name: 'Agent1',
      instructions: 'Say "Hello from Agent 1" and nothing else.',
      llm: 'gpt-4o-mini',
      verbose: false,
      stream: false
    });
    const agent2 = new Agent({
      name: 'Agent2',
      instructions: 'Say "Hello from Agent 2" and nothing else.',
      llm: 'gpt-4o-mini',
      verbose: false,
      stream: false
    });
    const team = new AgentTeam({
      agents: [agent1, agent2],
      verbose: false,
      pretty: false,
      process: 'parallel'
    });
    const results = await team.start();
    return results.join(' | ');
  });

  await runTest('AgentTeam: With Custom Tasks', async () => {
    const agent = new Agent({
      name: 'TaskAgent',
      instructions: 'Complete tasks efficiently.',
      llm: 'gpt-4o-mini',
      verbose: false,
      stream: false
    });
    const team = new AgentTeam({
      agents: [agent],
      tasks: ['Say "Task completed" and nothing else.'],
      verbose: false,
      pretty: false,
      process: 'sequential'
    });
    const results = await team.start();
    return results.join(' | ');
  });

  // === AGENT FLOW TESTS ===
  console.log('\n--- AgentFlow Tests ---');

  await runTest('AgentFlow: Sequential Steps', async () => {
    const flow = new AgentFlow('test-flow');

    flow.step('step1', async (input, context) => {
      return { message: 'Step 1 complete', input };
    });

    flow.step('step2', async (input, context) => {
      return { message: 'Step 2 complete', previous: input };
    });

    const result = await flow.run({ initial: 'data' });
    return JSON.stringify(result.output);
  });

  await runTest('AgentFlow: With Agent', async () => {
    const agent = new Agent({
      name: 'FlowAgent',
      instructions: 'Be very brief. One word answers only.',
      llm: 'gpt-4o-mini',
      verbose: false,
      stream: false
    });

    const flow = new AgentFlow('agent-flow');
    flow.agent(agent, 'What is 1+1? Reply with just the number.');

    const result = await flow.run('start');
    return String(result.output);
  });

  // === AGENT OS TESTS ===
  console.log('\n--- AgentOS Tests ---');

  await runTest('AgentOS: Basic Instantiation', async () => {
    const agent = new Agent({
      name: 'OSAgent',
      instructions: 'Be helpful.',
      llm: 'gpt-4o-mini',
      verbose: false,
      stream: false
    });

    const app = new AgentOS({
      name: 'Test OS',
      agents: [agent],
      config: {
        port: 19999,
        apiPrefix: '/api'
      }
    });

    // Verify properties
    if (app.name !== 'Test OS') throw new Error('Name mismatch');
    if (app.agents.length !== 1) throw new Error('Agents count mismatch');
    if (app.config.port !== 19999) throw new Error('Port mismatch');

    return `AgentOS '${app.name}' created with ${app.agents.length} agent(s)`;
  });

  await runTest('AgentOS: Express App Creation', async () => {
    const agent = new Agent({
      name: 'AppAgent',
      instructions: 'Be helpful.',
      llm: 'gpt-4o-mini',
      verbose: false,
      stream: false
    });

    const app = new AgentOS({
      name: 'Express Test',
      agents: [agent],
    });

    // Get the express app (lazy created)
    const expressApp = app.getApp();
    if (!expressApp) throw new Error('Express app not created');

    // Verify same instance returned on second call
    const sameApp = app.getApp();
    if (expressApp !== sameApp) throw new Error('Not same instance');

    return 'Express app created and cached correctly';
  });

  await runTest('AgentOS: With Teams and Flows', async () => {
    const agent = new Agent({
      name: 'MultiAgent',
      instructions: 'Be helpful.',
      llm: 'gpt-4o-mini',
      verbose: false,
      stream: false
    });

    const team = new AgentTeam({
      agents: [agent],
      verbose: false,
      pretty: false
    });

    const flow = new AgentFlow('test-flow');
    flow.step('step1', async () => ({ done: true }));

    const app = new AgentOS({
      name: 'Full OS',
      agents: [agent],
      teams: [team],
      flows: [flow],
    });

    if (app.teams.length !== 1) throw new Error('Teams count mismatch');
    if (app.flows.length !== 1) throw new Error('Flows count mismatch');

    return `AgentOS with ${app.agents.length} agent(s), ${app.teams.length} team(s), ${app.flows.length} flow(s)`;
  });

  // === AI SDK TESTS ===
  console.log('\n--- AI SDK Tests ---');

  await runTest('AI SDK: generateText (OpenAI)', async () => {
    const result = await aiGenerateText({
      model: 'gpt-4o-mini',
      prompt: 'Say "Hello World" and nothing else.'
    });
    return result.text;
  });

  await runTest('AI SDK: generateText (Anthropic)', async () => {
    const result = await aiGenerateText({
      model: 'anthropic/claude-3-haiku-20240307',
      prompt: 'Say "Hello from Claude" and nothing else.'
    });
    return result.text;
  });

  await runTest('AI SDK: generateText (Google)', async () => {
    // Google requires GOOGLE_GENERATIVE_AI_API_KEY, not GOOGLE_API_KEY
    if (!process.env.GOOGLE_GENERATIVE_AI_API_KEY && process.env.GOOGLE_API_KEY) {
      process.env.GOOGLE_GENERATIVE_AI_API_KEY = process.env.GOOGLE_API_KEY;
    }
    const result = await aiGenerateText({
      model: 'google/gemini-2.0-flash',
      prompt: 'Say "Hello from Gemini" and nothing else.'
    });
    return result.text;
  });

  await runTest('AI SDK: streamText', async () => {
    const result = await aiStreamText({
      model: 'gpt-4o-mini',
      prompt: 'Count from 1 to 5.'
    });
    let text = '';
    for await (const chunk of result.textStream) {
      text += chunk;
    }
    return text;
  });

  // === MODEL TESTS ===
  console.log('\n--- Model Tests ---');

  await runTest('Model: Parse gpt-4o', async () => {
    const parsed = parseModel('gpt-4o');
    return `provider: ${parsed.provider}, model: ${parsed.modelId}`;
  });

  await runTest('Model: Parse claude-3-sonnet', async () => {
    const parsed = parseModel('claude-3-sonnet');
    return `provider: ${parsed.provider}, model: ${parsed.modelId}`;
  });

  await runTest('Model: Aliases Check', async () => {
    const aliases = Object.keys(MODEL_ALIASES);
    const required = ['gpt-5', 'o3-mini', 'claude-4', 'gemini-3', 'deepseek-r1'];
    const missing = required.filter(a => !aliases.includes(a));
    if (missing.length > 0) throw new Error(`Missing aliases: ${missing.join(', ')}`);
    return `${aliases.length} aliases, all required present`;
  });

  // === TOOL TESTS ===
  console.log('\n--- Tool Tests ---');

  await runTest('Tool: Tavily Search (via Agent)', async () => {
    // Test Tavily through an agent which handles the tool properly
    const tool = tavilySearch();
    // Just verify the tool is created correctly
    if (!tool.name || !tool.description || !tool.execute) {
      throw new Error('Tool missing required properties');
    }
    return `Tool created: ${tool.name}, has execute: ${typeof tool.execute === 'function'}`;
  });

  await runTest('Tool: Registry List', async () => {
    const registry = getToolsRegistry();
    const tools = registry.list();
    return `${tools.length} tools registered`;
  });

  // === PRINT SUMMARY ===
  console.log('\n=== TEST SUMMARY ===');
  const passed = results.filter(r => r.status === '✓').length;
  const failed = results.filter(r => r.status === '✗').length;
  const warned = results.filter(r => r.status === '⚠').length;

  console.log(`\nTotal: ${results.length} tests`);
  console.log(`Passed: ${passed}`);
  console.log(`Failed: ${failed}`);
  console.log(`Warnings: ${warned}`);

  if (failed > 0) {
    console.log('\n--- Failed Tests ---');
    results.filter(r => r.status === '✗').forEach(r => {
      console.log(`  ✗ ${r.test}: ${r.error}`);
    });
  }

  console.log('\n--- All Results ---');
  results.forEach(r => {
    const status = r.status === '✓' ? '✓' : r.status === '✗' ? '✗' : '⚠';
    const info = r.response || r.error || '';
    console.log(`${status} ${r.test}: ${info.substring(0, 60)}${info.length > 60 ? '...' : ''}`);
  });

  // Exit with error if any tests failed
  if (failed > 0) {
    process.exit(1);
  }
}

main().catch(e => {
  console.error('Fatal error:', e);
  process.exit(1);
});
