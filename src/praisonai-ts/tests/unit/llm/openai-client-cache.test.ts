import { getOpenAIClient, resetOpenAIClient } from '../../../src/llm/openai';

jest.mock('openai');

describe('getOpenAIClient cache invalidation', () => {
  const savedKey = process.env.OPENAI_API_KEY;
  const savedBase = process.env.OPENAI_BASE_URL;

  beforeEach(() => {
    resetOpenAIClient();
    delete process.env.OPENAI_BASE_URL;
  });

  afterEach(() => {
    if (savedKey === undefined) delete process.env.OPENAI_API_KEY;
    else process.env.OPENAI_API_KEY = savedKey;
    if (savedBase === undefined) delete process.env.OPENAI_BASE_URL;
    else process.env.OPENAI_BASE_URL = savedBase;
    resetOpenAIClient();
  });

  it('rebuilds the client when the API key changes', async () => {
    process.env.OPENAI_API_KEY = 'sk-first';
    const first = await getOpenAIClient();
    process.env.OPENAI_API_KEY = 'sk-second';
    const second = await getOpenAIClient();
    expect(second).not.toBe(first);
  });

  it('reuses the same client when nothing changes', async () => {
    process.env.OPENAI_API_KEY = 'sk-stable';
    const first = await getOpenAIClient();
    const second = await getOpenAIClient();
    expect(second).toBe(first);
  });

  it('rebuilds the client when only the base URL changes', async () => {
    process.env.OPENAI_API_KEY = 'sk-stable';
    process.env.OPENAI_BASE_URL = 'https://a.example/v1';
    const first = await getOpenAIClient();
    process.env.OPENAI_BASE_URL = 'https://b.example/v1';
    const second = await getOpenAIClient();
    expect(second).not.toBe(first);
  });

  it('throws before constructing a client when the key is missing', async () => {
    delete process.env.OPENAI_API_KEY;
    await expect(getOpenAIClient()).rejects.toThrow(
      'OPENAI_API_KEY not found in environment variables'
    );
  });

  it('resetOpenAIClient forces a rebuild on the next call', async () => {
    process.env.OPENAI_API_KEY = 'sk-stable';
    const first = await getOpenAIClient();
    resetOpenAIClient();
    const second = await getOpenAIClient();
    expect(second).not.toBe(first);
  });

  it('returns the client built for its own key under overlapping calls', async () => {
    process.env.OPENAI_API_KEY = 'sk-a';
    const pA = getOpenAIClient();
    process.env.OPENAI_API_KEY = 'sk-b';
    const pB = getOpenAIClient();
    const [a, b] = await Promise.all([pA, pB]);
    // Each caller must keep the client it built for its own credentials,
    // never the client another concurrent call installed into the cache.
    expect(a).not.toBe(b);
  });

  it('does not return null when reset races an in-flight init', async () => {
    process.env.OPENAI_API_KEY = 'sk-race';
    const p = getOpenAIClient();
    resetOpenAIClient();
    const client = await p;
    expect(client).toBeDefined();
    expect(client).not.toBeNull();
  });
});
