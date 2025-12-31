/**
 * AI SDK v6 Live Tests
 * 
 * These tests require real API keys and make actual API calls.
 * Run with: LIVE_TESTS=1 npm test -- --testPathPattern="live"
 * 
 * Environment variables:
 * - OPENAI_API_KEY: Required for most tests
 * - ANTHROPIC_API_KEY: Optional for Anthropic tests
 * - GOOGLE_API_KEY: Optional for Google tests
 */

import { 
  aiGenerateText,
  aiStreamText,
} from '../../src';

// Skip all tests if LIVE_TESTS is not set
const LIVE_TESTS = process.env.LIVE_TESTS === '1';
const OPENAI_KEY = process.env.OPENAI_API_KEY;
const ANTHROPIC_KEY = process.env.ANTHROPIC_API_KEY;
const GOOGLE_KEY = process.env.GOOGLE_GENERATIVE_AI_API_KEY || process.env.GOOGLE_API_KEY;

const describeIf = (condition: boolean) => condition ? describe : describe.skip;

describeIf(LIVE_TESTS && !!OPENAI_KEY)('AI SDK v6 Live Tests (OpenAI)', () => {
  jest.setTimeout(60000); // 60 second timeout for API calls

  describe('generateText', () => {
    it('should generate text response', async () => {
      const result = await aiGenerateText({
        model: 'openai/gpt-4o-mini',
        prompt: 'What is 2+2? Answer with just the number.',
      });

      expect(result).toBeDefined();
      expect(result.text).toBeDefined();
      expect(result.text).toContain('4');
    });

    it('should work with messages format', async () => {
      const result = await aiGenerateText({
        model: 'openai/gpt-4o-mini',
        messages: [
          { role: 'system', content: 'You are a helpful assistant. Be concise.' },
          { role: 'user', content: 'What is the capital of France? One word answer.' },
        ],
      });

      expect(result.text.toLowerCase()).toContain('paris');
    });
  });

  describe('streamText', () => {
    it('should stream text response', async () => {
      const result = await aiStreamText({
        model: 'openai/gpt-4o-mini',
        prompt: 'Count from 1 to 5.',
      });

      expect(result).toBeDefined();
      expect(result.textStream).toBeDefined();

      let fullText = '';
      for await (const chunk of result.textStream) {
        fullText += chunk;
      }
      
      expect(fullText).toMatch(/1.*2.*3.*4.*5/);
    });
  });

  describe('generateObject', () => {
    it('should generate structured JSON', async () => {
      // Test structured output via generateText with JSON mode
      const result = await aiGenerateText({
        model: 'openai/gpt-4o-mini',
        messages: [
          { role: 'system', content: 'You output only raw JSON, no markdown, no explanation.' },
          { role: 'user', content: '{"name":"John","age":30}' },
        ],
      });

      expect(result).toBeDefined();
      expect(result.text).toBeDefined();
      
      // Extract JSON from response (handle markdown wrapping)
      let jsonStr = result.text.trim();
      if (jsonStr.startsWith('```')) {
        jsonStr = jsonStr.replace(/```json?\n?/g, '').replace(/```/g, '').trim();
      }
      
      const parsed = JSON.parse(jsonStr);
      expect(parsed.name).toBe('John');
      expect(parsed.age).toBe(30);
    });
  });
});

describeIf(LIVE_TESTS && !!ANTHROPIC_KEY)('AI SDK v6 Live Tests (Anthropic)', () => {
  jest.setTimeout(60000);

  it('should work with Claude', async () => {
    const result = await aiGenerateText({
      model: 'anthropic/claude-3-haiku-20240307',
      prompt: 'What is 3+3? Answer with just the number.',
    });

    expect(result).toBeDefined();
    expect(result.text).toContain('6');
  });
});

describeIf(LIVE_TESTS && !!GOOGLE_KEY)('AI SDK v6 Live Tests (Google)', () => {
  jest.setTimeout(60000);

  it('should work with Gemini', async () => {
    const result = await aiGenerateText({
      model: 'google/gemini-1.5-flash',
      prompt: 'What is 4+4? Answer with just the number.',
    });

    expect(result).toBeDefined();
    expect(result.text).toContain('8');
  });
});

// Always run this test to verify test setup
describe('Live Test Setup', () => {
  it('should report environment status', () => {
    console.log('\n=== Live Test Environment ===');
    console.log(`LIVE_TESTS: ${LIVE_TESTS ? 'enabled' : 'disabled'}`);
    console.log(`OPENAI_API_KEY: ${OPENAI_KEY ? '✓ set' : '✗ not set'}`);
    console.log(`ANTHROPIC_API_KEY: ${ANTHROPIC_KEY ? '✓ set' : '✗ not set'}`);
    console.log(`GOOGLE_API_KEY: ${GOOGLE_KEY ? '✓ set' : '✗ not set'}`);
    console.log('');
    
    if (!LIVE_TESTS) {
      console.log('To run live tests: LIVE_TESTS=1 npm test -- --testPathPattern="live"');
    }
    
    expect(true).toBe(true);
  });
});
