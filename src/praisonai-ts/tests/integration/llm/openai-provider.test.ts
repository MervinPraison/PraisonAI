/**
 * OpenAI Provider Integration Tests - Real API calls
 * Run with: PRAISONAI_TEST_REAL_KEYS=1 npm test -- --testPathPattern=integration/llm
 */

import { describe, it, expect, beforeAll } from '@jest/globals';
import { createProvider, OpenAIProvider } from '../../../src/llm/providers';

const SKIP_REAL_TESTS = !process.env.PRAISONAI_TEST_REAL_KEYS;
const HAS_OPENAI_KEY = !!process.env.OPENAI_API_KEY;

describe('OpenAI Provider Integration', () => {
  beforeAll(() => {
    if (SKIP_REAL_TESTS) {
      console.log('Skipping real API tests. Set PRAISONAI_TEST_REAL_KEYS=1 to enable.');
    }
    if (!HAS_OPENAI_KEY) {
      console.log('OPENAI_API_KEY not set.');
    }
  });

  it('should generate text', async () => {
    if (SKIP_REAL_TESTS || !HAS_OPENAI_KEY) return;

    const provider = createProvider('openai/gpt-4o-mini');
    const result = await provider.generateText({
      messages: [
        { role: 'system', content: 'You are a helpful assistant. Be concise.' },
        { role: 'user', content: 'Say "Hello" and nothing else.' },
      ],
      maxTokens: 10,
      temperature: 0,
    });

    expect(result.text).toBeDefined();
    expect(result.text.toLowerCase()).toContain('hello');
    expect(result.usage.promptTokens).toBeGreaterThan(0);
    expect(result.usage.completionTokens).toBeGreaterThan(0);
    console.log('OpenAI generateText result:', result.text.substring(0, 50));
  });

  it('should stream text', async () => {
    if (SKIP_REAL_TESTS || !HAS_OPENAI_KEY) return;

    const provider = createProvider('openai/gpt-4o-mini');
    const tokens: string[] = [];

    const stream = await provider.streamText({
      messages: [
        { role: 'user', content: 'Count from 1 to 3, one number per line.' },
      ],
      maxTokens: 20,
      onToken: (token) => tokens.push(token),
    });

    let fullText = '';
    for await (const chunk of stream) {
      if (chunk.text) fullText += chunk.text;
    }

    expect(tokens.length).toBeGreaterThan(0);
    expect(fullText).toContain('1');
    console.log('OpenAI streamText tokens:', tokens.length);
  });

  it('should call tools', async () => {
    if (SKIP_REAL_TESTS || !HAS_OPENAI_KEY) return;

    const provider = createProvider('openai/gpt-4o-mini');
    const result = await provider.generateText({
      messages: [
        { role: 'user', content: 'What is 2 + 2? Use the calculator tool.' },
      ],
      tools: [{
        name: 'calculator',
        description: 'Perform math calculations',
        parameters: {
          type: 'object',
          properties: {
            expression: { type: 'string', description: 'Math expression to evaluate' },
          },
          required: ['expression'],
        },
      }],
      maxTokens: 100,
    });

    expect(result.toolCalls).toBeDefined();
    expect(result.toolCalls!.length).toBeGreaterThan(0);
    expect(result.toolCalls![0].function.name).toBe('calculator');
    console.log('OpenAI tool call:', result.toolCalls![0].function);
  });

  it('should generate structured output', async () => {
    if (SKIP_REAL_TESTS || !HAS_OPENAI_KEY) return;

    const provider = createProvider('openai/gpt-4o-mini');
    const result = await provider.generateObject({
      messages: [
        { role: 'user', content: 'Extract: John is 30 years old and lives in New York.' },
      ],
      schema: {
        type: 'object',
        properties: {
          name: { type: 'string' },
          age: { type: 'number' },
          city: { type: 'string' },
        },
        required: ['name', 'age', 'city'],
        additionalProperties: false,
      },
      maxTokens: 100,
    });

    expect(result.object).toBeDefined();
    expect(result.object.name).toBe('John');
    expect(result.object.age).toBe(30);
    expect(result.object.city).toBe('New York');
    console.log('OpenAI structured output:', result.object);
  });
});
