/**
 * Smoke Tests - Real API key validation (gated)
 * 
 * These tests only run when API keys are available in environment
 * AND when not running in mock mode.
 * They validate real provider integration without exposing secrets.
 * 
 * To run with real API:
 *   OPENAI_API_KEY=sk-... npm test -- --testPathPattern=smoke --no-coverage
 */

import { Agent } from '../../src';

const OPENAI_KEY = process.env.OPENAI_API_KEY;
const IS_MOCK_MODE = process.env.NODE_ENV === 'test' || process.env.JEST_WORKER_ID !== undefined;
const SKIP_REASON = IS_MOCK_MODE 
  ? 'Skipping: Running in mock mode (use real-smoke.test.ts for real API tests)'
  : 'Skipping: OPENAI_API_KEY not set';
const SHOULD_RUN_REAL_API = OPENAI_KEY && !IS_MOCK_MODE;

describe('Real Provider Smoke Tests', () => {
  describe('Agent.chat with OpenAI', () => {
    (SHOULD_RUN_REAL_API ? it : it.skip)('should complete a simple chat', async () => {
      const agent = new Agent({
        instructions: 'You are a helpful assistant. Be very brief.',
        llm: 'gpt-4o-mini',
        stream: false,
        verbose: false
      });

      const response = await agent.chat('Say "hello" and nothing else.');
      
      expect(response).toBeDefined();
      expect(typeof response).toBe('string');
      expect(response.length).toBeGreaterThan(0);
      // Response should contain "hello" in some form
      expect(response.toLowerCase()).toContain('hello');
    }, 30000);

    (SHOULD_RUN_REAL_API ? it : it.skip)('should handle tool calling', async () => {
      const getWeather = (city: string) => `Weather in ${city}: 22°C, Sunny`;
      
      const agent = new Agent({
        instructions: 'You are a weather assistant. Use the getWeather tool to answer.',
        llm: 'gpt-4o-mini',
        stream: false,
        verbose: false,
        tools: [getWeather]
      });

      const response = await agent.chat('What is the weather in Paris?');
      
      expect(response).toBeDefined();
      expect(typeof response).toBe('string');
      // Response should mention the weather data
      expect(response.toLowerCase()).toMatch(/paris|22|sunny|weather/i);
    }, 60000);
  });

  describe('Session persistence', () => {
    it('should generate unique session IDs', () => {
      const agent1 = new Agent({ instructions: 'Test' });
      const agent2 = new Agent({ instructions: 'Test' });
      
      expect(agent1.getSessionId()).not.toBe(agent2.getSessionId());
    });

    it('should use provided session ID', () => {
      const agent = new Agent({ 
        instructions: 'Test',
        sessionId: 'test-session-123'
      });
      
      expect(agent.getSessionId()).toBe('test-session-123');
    });
  });
});

// Log skip reason if no API key
if (!OPENAI_KEY) {
  console.log(`\n⚠️  ${SKIP_REASON}\n`);
}
