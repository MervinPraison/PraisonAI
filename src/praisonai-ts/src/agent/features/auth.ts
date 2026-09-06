/**
 * Subscription auth on an Agent (Python parity: `Agent(auth="claude-code")`,
 * `agent/agent.py` lines 2087-2100 and `_AUTH_DEFAULT_MODELS`, over
 * `praisonaiagents/auth`).
 *
 * `auth` says "bill this run against my subscription seat, not my API key".
 * Two consequences follow, and both matter:
 *
 * 1. **It fails at construction, never at request time.** A user who asked to
 *    be billed against a subscription must not be silently downgraded to
 *    API-key billing, so an unknown or unregistered provider throws before the
 *    agent exists — where the error is about the option, not about a request.
 * 2. **It pins the vendor.** A subscription seat belongs to one vendor, so the
 *    OpenAI default model would ship the provider's OAuth token to the wrong
 *    endpoint. When the caller gave no model, `auth` chooses one.
 *
 * The credential stores themselves (a Claude Code keychain entry, a Codex CLI
 * file) are host concerns and are not read here: a provider is registered with
 * `registerAuthProvider` from `src/llm`, which is also what Python's
 * `register_subscription_provider` is.
 */

// From `../../llm/auth`, the leaf, NOT from the `../../llm` barrel. The barrel
// re-exports these same three symbols, but it also imports `openai` and
// `../../llm/embeddings` at the top level -- and this file is on `Agent`'s
// static graph, so importing it through the barrel put the OpenAI client and
// three `@ai-sdk/*` provider packages into praisonai-mobile's webview bundle
// (326.7kB, measured) for three functions that depend on nothing.
import { listAuthProviders, resolveAuth, type LLMAuth } from '../../llm/auth';

/**
 * Default model per subscription provider, used only when the caller gave
 * `auth` without a model (Python `_AUTH_DEFAULT_MODELS`).
 */
export const AUTH_DEFAULT_MODELS: Readonly<Record<string, string>> = Object.freeze({
  'claude-code': 'anthropic/claude-sonnet-4-5',
  'qwen-cli': 'openai/qwen3-coder-plus',
});

/**
 * Fail now if `name` names no registered provider (Python
 * `resolve_subscription_credentials`, which raises `AuthError` at
 * construction for exactly this reason).
 */
export function assertAuthProviderRegistered(name: string): void {
  const registered = listAuthProviders();
  if (registered.includes(name)) return;
  throw new Error(
    `Unknown subscription provider '${name}'. Registered: ${registered.length > 0 ? registered.join(', ') : '(none)'}.\n` +
    `  A subscription store is a host concern: register one with registerAuthProvider('${name}', resolver).\n` +
    `  Passing auth= and falling back to API-key billing would charge the wrong account, so this fails here rather than at request time.`
  );
}

/** The model `auth` implies when the caller named none. */
export function authDefaultModel(name: string): string | undefined {
  return AUTH_DEFAULT_MODELS[name];
}

/** Resolve the provider's credentials (Python's `resolve_credentials()`). */
export async function resolveAgentAuth(name: string): Promise<LLMAuth> {
  return resolveAuth(name);
}

/**
 * Wrap `fetchImpl` so every outgoing request carries the provider's headers
 * (a user agent, beta flags). Existing headers on a request win, so a caller
 * can still override one deliberately.
 */
export function withAuthHeaders(
  fetchImpl: typeof fetch | undefined,
  headers: Record<string, string>
): typeof fetch | undefined {
  if (Object.keys(headers).length === 0) return fetchImpl;
  const underlying: typeof fetch | undefined =
    fetchImpl ?? (typeof fetch === 'function' ? fetch : undefined);
  if (!underlying) return fetchImpl;
  return async (input: any, init?: any) => {
    const merged = new Headers(init?.headers ?? {});
    for (const [key, value] of Object.entries(headers)) {
      if (!merged.has(key)) merged.set(key, value);
    }
    return underlying(input, { ...(init ?? {}), headers: merged });
  };
}
