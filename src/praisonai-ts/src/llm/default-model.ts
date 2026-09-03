/**
 * Provider-aware default model resolution.
 *
 * Python parity: `Agent._PROVIDER_DEFAULT_MODELS` / `Agent._resolve_default_model`
 * (src/praisonai-agents/praisonaiagents/agent/agent.py).
 *
 * A hardcoded `gpt-4o-mini` default is only correct for a user who has an
 * OpenAI key. A user whose only credential is `ANTHROPIC_API_KEY` used to get
 * an OpenAI model that could not authenticate -- a default that cannot work.
 * The walk below picks a model matching whichever credential is actually
 * present, exactly as the Python SDK does.
 */

import { getEnv } from './openaiClientOptions';

/**
 * Ordered `[credential env var, provider-appropriate default model]` pairs.
 * The first provider whose credential is present wins. OpenAI is first so
 * existing OpenAI users keep their default; any other single configured
 * provider yields a matching default instead of a failing OpenAI one.
 *
 * Byte-identical to Python's `Agent._PROVIDER_DEFAULT_MODELS`, so the two SDKs
 * pick the same model from the same environment.
 */
export const PROVIDER_DEFAULT_MODELS: ReadonlyArray<readonly [string, string]> = [
  ['OPENAI_API_KEY', 'gpt-4o-mini'],
  ['ANTHROPIC_API_KEY', 'anthropic/claude-3-5-sonnet-latest'],
  ['GEMINI_API_KEY', 'gemini/gemini-1.5-flash'],
  ['GOOGLE_API_KEY', 'google/gemini-1.5-flash'],
  ['GROQ_API_KEY', 'groq/llama-3.3-70b-versatile'],
  ['COHERE_API_KEY', 'cohere/command-r'],
  ['OLLAMA_HOST', 'ollama/llama3.2'],
] as const;

/** The final fallback when no credential at all is configured. */
export const FALLBACK_DEFAULT_MODEL = 'gpt-4o-mini';

/**
 * Resolve the default model for an agent that named none.
 *
 * Precedence (Python parity, plus the TypeScript-only `PRAISONAI_MODEL`):
 * `OPENAI_MODEL_NAME` > `PRAISONAI_MODEL` > first provider whose credential
 * env var is set > `gpt-4o-mini`.
 *
 * Unlike Python this is not memoised: reading the environment on every call
 * keeps a `process.env` change (a test, a CLI that loads `.env` late) honest.
 *
 * @returns A model string, provider-prefixed unless it is an OpenAI model.
 * @example
 * // Only ANTHROPIC_API_KEY set:
 * resolveDefaultModel(); // 'anthropic/claude-3-5-sonnet-latest'
 */
export function resolveDefaultModel(): string {
  const explicit = getEnv('OPENAI_MODEL_NAME') || getEnv('PRAISONAI_MODEL');
  if (explicit) return explicit;
  for (const [keyVar, model] of PROVIDER_DEFAULT_MODELS) {
    if (getEnv(keyVar)) return model;
  }
  return FALLBACK_DEFAULT_MODEL;
}
