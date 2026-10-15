/**
 * NVIDIA NIM (build.nvidia.com or a local NIM container) over the
 * OpenAI-compatible AI SDK provider. Mirrors the Python SDK: the same short
 * aliases, key order and Nemotron 3 reasoning switch.
 */

import { AISDKError, AISDKProviderOptions } from './types';
import { getEnv } from '../../openaiClientOptions';

export const NVIDIA_NIM_DEFAULT_BASE_URL = 'https://integrate.api.nvidia.com/v1';

const NVIDIA_NIM_PREFIXES = new Set(['nvidia', 'nim', 'nvidia-nim']);

/** Short name -> catalog slug (verified 2026-10-15 via GET /v1/models). */
export const NVIDIA_NIM_ALIASES: Record<string, string> = {
  'nemotron-super': 'nemotron-3-super-120b-a12b',
  'nemotron-nano': 'nemotron-nano-3-30b-a3b',
  'nemotron-ultra': 'nemotron-3-ultra-550b-a55b',
};

/**
 * The id NIM expects on the wire. NIM ids carry their publisher, so a bare
 * name gets `nvidia/` back: `nemotron-super` -> `nvidia/nemotron-3-super-120b-a12b`,
 * while `meta/llama-3.3-70b-instruct` is already complete.
 */
export function toNvidiaNimModelId(modelId: string): string {
  if (modelId.includes('/')) return modelId;
  return `nvidia/${NVIDIA_NIM_ALIASES[modelId.toLowerCase()] ?? modelId}`;
}

/**
 * Create the NIM provider. Key order: explicit apiKey, NVIDIA_NIM_API_KEY,
 * NVIDIA_API_KEY. A local NIM accepts any non-empty key, so a non-NVIDIA
 * baseURL gets a placeholder. OPENAI_API_KEY is never consulted.
 *
 * `packageName` comes from the provider registry so the import stays computed:
 * a literal `import('@ai-sdk/openai-compatible')` would be pulled into
 * bundles (e.g. the mobile webview) that never load host providers.
 */
export async function createNvidiaNimProvider(
  options: AISDKProviderOptions = {},
  packageName: string
): Promise<unknown> {
  const baseURL = options.baseURL || getEnv('NVIDIA_NIM_API_BASE') || NVIDIA_NIM_DEFAULT_BASE_URL;
  let apiKey = options.apiKey || getEnv('NVIDIA_NIM_API_KEY') || getEnv('NVIDIA_API_KEY');
  if (!apiKey) {
    if (baseURL.includes('integrate.api.nvidia.com')) {
      throw new AISDKError(
        'NVIDIA_API_KEY is not set. Get one at build.nvidia.com, or pass baseURL for a local NIM.',
        'AUTHENTICATION',
        false
      );
    }
    apiKey = 'not-used';
  }
  const { createOpenAICompatible } = await import(packageName);
  return createOpenAICompatible({
    name: 'nvidia-nim',
    baseURL,
    apiKey,
    ...(options.headers ? { headers: options.headers } : {}),
    ...(options.fetch ? { fetch: options.fetch } : {}),
  });
}

/**
 * Nemotron 3 on NIM ignores `reasoning_effort`; thinking is switched through
 * `chat_template_kwargs`. Takes the full model string (`nvidia/nemotron-super`)
 * and returns undefined for anything else, including Nemotron served by other
 * providers and an unset effort (server default: thinking on).
 */
export function nvidiaNimReasoningKwargs(
  model: string,
  effort: string | undefined
): Record<string, boolean> | undefined {
  const slash = model.indexOf('/');
  if (!effort || slash < 0 || !NVIDIA_NIM_PREFIXES.has(model.slice(0, slash).toLowerCase())) return undefined;
  if (!/nemotron-(3|nano-3)-/i.test(toNvidiaNimModelId(model.slice(slash + 1)))) return undefined;
  if (effort === 'off') return { enable_thinking: false };
  if (effort === 'minimal' || effort === 'low') return { enable_thinking: true, low_effort: true };
  return { enable_thinking: true };
}
