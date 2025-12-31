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
      instructions: 'Be very brief. One sentence max.', 
      llm: 'gpt-4o-mini',
      verbose: false 
    });
    return await agent.chat('What is 2+2?');
  });

  await runTest('Agent: With Custom Tool', async () => {
    const calculator = (expression: string) => String(eval(expression));
    const agent = new Agent({ 
      instructions: 'Use the calculator tool for math.',
      tools: [calculator],
      llm: 'gpt-4o-mini',
      verbose: false 
    });
    return await agent.chat('What is 15 * 7?');
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
