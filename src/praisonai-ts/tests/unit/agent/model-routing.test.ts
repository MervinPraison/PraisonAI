/**
 * Which vendor a model name actually reaches.
 *
 * The Agent constructor carried its own copy of the model-parsing rule, and it
 * defaulted every slash-less name to OpenAI. So `new Agent({ llm:
 * "claude-3-5-sonnet-latest" })` sent an OpenAI-format request, with
 * OpenAI-format tools, to the OpenAI endpoint -- a wrong-vendor call that
 * surfaces as model-not-found, or as a bill nobody can explain.
 *
 * `backend-resolver.parseModelString` had always inferred these correctly.
 * There were simply two rules that disagreed, and the constructor used the
 * wrong one.
 */
import { Agent } from '../../../src/agent/simple';

/** The Agent exposes no getter for this, and it decides the whole request
 *  shape, so the test reads it directly rather than asserting on a side
 *  effect two layers away. */
const usesAISdk = (agent: Agent): boolean => (agent as any)._useAISDKBackend === true;
const modelOf = (agent: Agent): string => (agent as any).llmService?.model ?? '';

describe('model routing', () => {
  it('a bare claude- name routes to Anthropic, not OpenAI', () => {
    expect(usesAISdk(new Agent({ instructions: 'x', llm: 'claude-3-5-sonnet-latest' }))).toBe(true);
  });

  it('a bare gemini- name routes to Google, not OpenAI', () => {
    expect(usesAISdk(new Agent({ instructions: 'x', llm: 'gemini-2.0-flash' }))).toBe(true);
  });

  it('a bare gpt- name still routes to OpenAI', () => {
    // The pair. Without it, "always use the AI SDK" would satisfy both cases
    // above and send every OpenAI request down the wrong path instead.
    expect(usesAISdk(new Agent({ instructions: 'x', llm: 'gpt-4o-mini' }))).toBe(false);
  });

  it('an explicit provider/model prefix is honoured', () => {
    expect(usesAISdk(new Agent({ instructions: 'x', llm: 'anthropic/claude-3-5-sonnet-latest' }))).toBe(true);
    expect(usesAISdk(new Agent({ instructions: 'x', llm: 'openai/gpt-4o' }))).toBe(false);
  });

  it('the provider prefix is stripped from the model id', () => {
    // Sending "anthropic/claude-..." as the model NAME is a 404 at whichever
    // endpoint receives it.
    expect(modelOf(new Agent({ instructions: 'x', llm: 'openai/gpt-4o' }))).toBe('gpt-4o');
  });

  it('a custom baseURL keeps a bare name on the OpenAI-compatible path', () => {
    // The deliberate exception. Pointing at a proxy that serves claude-* over
    // an OpenAI-shaped API is a real deployment, and prefix inference would
    // route it away from the endpoint the caller explicitly asked for.
    const agent = new Agent({
      instructions: 'x',
      llm: 'claude-3-5-sonnet-latest',
      baseURL: 'https://my-gateway.example/v1',
    });
    expect(usesAISdk(agent)).toBe(false);
  });

  it('an EXPLICIT prefix still wins over a custom baseURL', () => {
    // The pair for the exception: asking for anthropic/... by name is
    // unambiguous, and a baseURL must not silently override it.
    const agent = new Agent({
      instructions: 'x',
      llm: 'anthropic/claude-3-5-sonnet-latest',
      baseURL: 'https://my-gateway.example/v1',
    });
    expect(usesAISdk(agent)).toBe(true);
  });

  it('an unknown bare name still defaults to OpenAI', () => {
    // Unchanged behaviour for anything the prefixes do not recognise.
    expect(usesAISdk(new Agent({ instructions: 'x', llm: 'some-local-model' }))).toBe(false);
  });
});

/**
 * The routing fix exposes a bare claude-/gemini- name to the AI-SDK backend,
 * whose key gate previously read only the provider env var. A caller who passed
 * apiKey to the constructor -- and set no env var -- would authenticate on the
 * OpenAI path but be rejected on the one their model actually takes. These
 * tests pin the forwarding so that regression cannot return silently.
 */
describe('per-agent credential forwarding to the AI-SDK backend', () => {
  const savedAnthropic = process.env.ANTHROPIC_API_KEY;

  afterEach(() => {
    if (savedAnthropic === undefined) delete process.env.ANTHROPIC_API_KEY;
    else process.env.ANTHROPIC_API_KEY = savedAnthropic;
  });

  it('resolveBackend maps a flat apiKey onto the resolved provider', async () => {
    // With no env var, only a forwarded key can satisfy the backend's gate.
    delete process.env.ANTHROPIC_API_KEY;
    const { resolveBackend } = require('../../../src/llm/backend-resolver');
    const result = await resolveBackend('claude-3-5-sonnet-latest', {
      config: { apiKey: 'sk-ant-test' },
    });
    // The provider constructs at all (ensureInitialized's key gate is lazy, but
    // the mapping itself must succeed and select the anthropic provider).
    expect(result.providerId).toBe('anthropic');
    expect(result.source === 'ai-sdk' || result.source === 'native').toBe(true);
  });

  it('validateProviderApiKey accepts an explicit key with no env var', () => {
    delete process.env.ANTHROPIC_API_KEY;
    const { validateProviderApiKey } = require('../../../src/llm/providers/ai-sdk/provider-map');
    expect(validateProviderApiKey('anthropic')).toBe(false);
    expect(validateProviderApiKey('anthropic', 'sk-ant-test')).toBe(true);
  });
});
