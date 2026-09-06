/**
 * LLM auth (Python parity: `auth: Optional[str]` -> praisonaiagents.auth).
 *
 * A LEAF module, and that is the whole reason it is a file of its own.
 *
 * This block used to live in `llm/index.ts`, which is a barrel: it imports
 * `openai` and `llm/embeddings` at the top level. `agent/features/auth.ts`
 * needs exactly `resolveAuth`, `listAuthProviders` and `LLMAuth` from it --
 * three symbols with no dependencies at all -- and reaching them through the
 * barrel dragged the whole OpenAI client and the embedding stack onto every
 * graph that could see `Agent`. On praisonai-mobile's webview bundle that was
 * measured at 326.7kB of `@ai-sdk/*` provider packages nothing on a phone can
 * call, against a 1600kB budget that had 23.6kB left.
 *
 * `llm/index.ts` re-exports every name below, so the public API is unchanged:
 * `import { resolveAuth } from 'praisonai'` and `from 'praisonai/llm'` both
 * still work, and there is still exactly ONE `authProviders` map because there
 * is still exactly one module that declares it.
 *
 * The rule for this file: nothing here may import a module with a side effect
 * or a heavy dependency. It is imported for three functions; it must cost
 * three functions.
 */

/** Resolved credentials, mirroring Python's `SubscriptionCredentials`. */
export interface LLMAuth {
  apiKey?: string;
  baseURL?: string;
  headers?: Record<string, string>;
}

export type LLMAuthResolver = () => LLMAuth | Promise<LLMAuth>;

/**
 * What `LLMConfig.auth` accepts: resolved credentials, a function returning
 * them, or the name of a provider registered with {@link registerAuthProvider}
 * (Python's `register_subscription_provider`).
 */
export type LLMAuthSource = string | LLMAuth | LLMAuthResolver;

const authProviders = new Map<string, LLMAuthResolver>();

/** Python parity: `register_subscription_provider(name, factory)`. */
export function registerAuthProvider(name: string, resolver: LLMAuthResolver): void {
  authProviders.set(name, resolver);
}

/** Python parity: `list_subscription_providers()`. */
export function listAuthProviders(): string[] {
  return Array.from(authProviders.keys()).sort();
}

/** Test helper: forget every registered provider. */
export function resetAuthProviders(): void {
  authProviders.clear();
}

function validateAuth(auth: unknown, source: string): LLMAuth {
  if (!auth || typeof auth !== 'object') {
    throw new Error(`LLM auth (${source}) must resolve to an object { apiKey?, baseURL?, headers? }; got ${typeof auth}`);
  }
  const a = auth as LLMAuth;
  if (a.apiKey !== undefined && typeof a.apiKey !== 'string') throw new Error(`LLM auth (${source}): apiKey must be a string`);
  if (a.baseURL !== undefined && typeof a.baseURL !== 'string') throw new Error(`LLM auth (${source}): baseURL must be a string`);
  if (a.headers !== undefined && (typeof a.headers !== 'object' || a.headers === null)) {
    throw new Error(`LLM auth (${source}): headers must be a string map`);
  }
  return a;
}

/**
 * Resolve an {@link LLMAuthSource} to credentials. Python's built-in named
 * OAuth stores (`claude-code`, `codex`, `gemini-cli`, `qwen-cli`) read local
 * CLI keychains and are not ported; a name resolves only when registered via
 * {@link registerAuthProvider}. An unknown name throws rather than silently
 * billing the plain API key.
 */
export async function resolveAuth(auth: LLMAuthSource): Promise<LLMAuth> {
  if (typeof auth === 'function') return validateAuth(await auth(), 'function');
  if (typeof auth === 'string') {
    const resolver = authProviders.get(auth);
    if (!resolver) {
      const known = listAuthProviders();
      throw new Error(
        `LLM auth "${auth}" is not a registered credential source` +
          (known.length ? ` (registered: ${known.join(', ')})` : '') +
          `. Python's named OAuth stores (claude-code, codex, gemini-cli, qwen-cli) are not ported to TypeScript; ` +
          `register one with registerAuthProvider("${auth}", () => ({ apiKey, baseURL, headers })) or pass ` +
          `{ apiKey, baseURL, headers } directly.`
      );
    }
    return validateAuth(await resolver(), `provider "${auth}"`);
  }
  return validateAuth(auth, 'object');
}
