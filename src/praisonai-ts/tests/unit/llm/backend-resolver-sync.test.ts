/**
 * resolveBackendSync — provider resolution through the synchronous path.
 *
 * The sync resolver used to reach its providers through bare require() calls
 * inside its body. Replacing those with static imports must not change what it
 * resolves: the native registry when asked for it (or when the AI SDK check has
 * not run), the AI SDK backend once isAISDKAvailable() has cached a positive
 * result, and — the case the require() version got WRONG under native ESM,
 * where the shim repointed it at the CommonJS twin and hence at a second
 * registry — providers registered on the default registry by the caller.
 *
 * resolveBackend (async) already has coverage in tests/unit/agent/model-routing.test.ts;
 * the built-in native providers in tests/unit/llm/provider-registry.test.ts.
 */

import {
  resolveBackendSync,
  isAISDKAvailable,
  resetAISDKAvailabilityCache,
} from '../../../src/llm/backend-resolver';
import { registerProvider, unregisterProvider } from '../../../src/llm/providers';
import type {
  LLMProvider,
  ProviderConfig,
  GenerateTextOptions,
  GenerateTextResult,
  StreamTextOptions,
  StreamChunk,
  GenerateObjectOptions,
  GenerateObjectResult,
} from '../../../src/llm/providers/types';

class StubProvider implements LLMProvider {
  readonly providerId = 'stub';
  readonly modelId: string;
  constructor(modelId: string, _config?: ProviderConfig) {
    this.modelId = modelId;
  }
  async generateText(_options: GenerateTextOptions): Promise<GenerateTextResult> {
    return { text: 'stub', usage: { promptTokens: 1, completionTokens: 1, totalTokens: 2 }, finishReason: 'stop' };
  }
  async streamText(_options: StreamTextOptions): Promise<AsyncIterable<StreamChunk>> {
    return { async *[Symbol.asyncIterator]() { yield { text: 'stub' }; } };
  }
  async generateObject<T>(_options: GenerateObjectOptions<T>): Promise<GenerateObjectResult<T>> {
    return { object: {} as T, usage: { promptTokens: 1, completionTokens: 1, totalTokens: 2 } };
  }
}

describe('resolveBackendSync', () => {
  // Provider constructors require a key (AnthropicProvider throws
  // 'ANTHROPIC_API_KEY is required'), so these tests passed only on a machine
  // that happened to have one exported and failed in CI. Resolution is what is
  // under test, not authentication: pin placeholder keys and restore them.
  const KEY_VARS = ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'GOOGLE_API_KEY', 'GEMINI_API_KEY'] as const;
  const savedKeys: Record<string, string | undefined> = {};

  beforeEach(() => {
    for (const name of KEY_VARS) {
      savedKeys[name] = process.env[name];
      process.env[name] = `test-${name.toLowerCase()}`;
    }
    resetAISDKAvailabilityCache();
  });

  afterEach(() => {
    for (const name of KEY_VARS) {
      if (savedKeys[name] === undefined) delete process.env[name];
      else process.env[name] = savedKeys[name] as string;
    }
  });

  it('resolves a built-in native provider when the native backend is requested', () => {
    const result = resolveBackendSync('openai/gpt-4o-mini', { backend: 'native' });
    expect(result.source).toBe('native');
    expect(result.providerId).toBe('openai');
    expect(result.modelId).toBe('gpt-4o-mini');
    expect(result.provider.providerId).toBe('openai');
    expect(result.provider.modelId).toBe('gpt-4o-mini');
  });

  it('falls back to native while AI SDK availability has not been checked', () => {
    // Cache is null: the sync path cannot await the check, so it must not guess.
    const result = resolveBackendSync('anthropic/claude-3-5-sonnet-latest');
    expect(result.source).toBe('native');
    expect(result.provider.providerId).toBe('anthropic');
  });

  it('resolves through the AI SDK backend once availability is cached', async () => {
    // `ai` is a devDependency, so the check caches true.
    expect(await isAISDKAvailable()).toBe(true);
    const result = resolveBackendSync('openai/gpt-4o-mini');
    expect(result.source).toBe('ai-sdk');
    expect(result.providerId).toBe('openai');
    expect(result.provider.providerId).toBe('openai');
    expect(result.provider.modelId).toBe('gpt-4o-mini');
  });

  it('resolves a provider the caller registered on the default registry', () => {
    registerProvider('stub', StubProvider);
    try {
      const result = resolveBackendSync('stub/any-model', { backend: 'native' });
      expect(result.source).toBe('native');
      expect(result.provider).toBeInstanceOf(StubProvider);
      expect(result.provider.modelId).toBe('any-model');
    } finally {
      unregisterProvider('stub');
    }
  });
});
