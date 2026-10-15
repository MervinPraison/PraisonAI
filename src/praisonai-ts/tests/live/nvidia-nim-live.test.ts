/**
 * NVIDIA NIM live tests (issue #5823): one chat, one tool call, one stream.
 *
 * Run with:
 *   LIVE_TESTS=1 NVIDIA_API_KEY=nvapi-... npx jest --testPathIgnorePatterns=/node_modules/ tests/live/nvidia-nim-live.test.ts
 */
import { Agent } from '../../src';

const LIVE = process.env.LIVE_TESTS === '1' && !!process.env.NVIDIA_API_KEY;
const describeIf = LIVE ? describe : describe.skip;
const MODEL = 'nvidia/nemotron-super';

describeIf('NVIDIA NIM live', () => {
  jest.setTimeout(120000);

  it('chats', async () => {
    const agent = new Agent({ instructions: 'Be brief.', llm: MODEL, reasoningEffort: 'off', verbose: false, stream: false });
    const text = await agent.chat('Say hello in one sentence.');
    console.log('NIM chat:', text);
    expect(text.length).toBeGreaterThan(0);
  });

  it('calls a tool', async () => {
    let called = false;
    function get_weather(city: string): string {
      called = true;
      return `It is 21C and sunny in ${city}.`;
    }
    const agent = new Agent({
      instructions: 'Use get_weather for weather questions.',
      tools: [get_weather],
      llm: MODEL,
      reasoningEffort: 'off',
      verbose: false,
      stream: false,
    });
    const text = await agent.chat('What is the weather in Paris?');
    console.log('NIM tool:', text);
    expect(called).toBe(true);
    expect(text).toMatch(/21/);
  });

  it('streams', async () => {
    const tokens: string[] = [];
    const agent = new Agent({ instructions: 'Be brief.', llm: MODEL, reasoningEffort: 'off', verbose: false, stream: true });
    const text = await agent.start('Count from 1 to 5.', undefined, (t) => tokens.push(t));
    console.log('NIM stream:', text, `(${tokens.length} chunks)`);
    expect(tokens.length).toBeGreaterThan(1);
  });
});
