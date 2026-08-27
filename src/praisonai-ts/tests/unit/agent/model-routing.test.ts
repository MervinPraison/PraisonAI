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
