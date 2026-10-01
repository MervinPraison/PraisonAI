/**
 * System One / Jev typed decision models (Ollama POST /v1/systemone, TypeSafe API).
 * @see https://ollama.com/blog/ollama-now-supports-jev-style-decision-models
 */

export const KNOWN_DECISION_MODELS = new Set(['nimble', 'tev1', 'tev1:0.8b']);

export type QuestionSpec =
  | { type: 'choice'; instructions: string; criteria: Record<string, string> }
  | { type: 'noul'; instructions: string }
  | { type: 'score'; instructions: string; criteria: string[] };

export interface SystemOneAnswer {
  type: string;
  choice?: string;
  noul?: number;
  score?: number;
  confidence?: number;
  probabilities?: Record<string, number>;
  legend?: Record<string, string>;
}

export interface SystemOneResult {
  model: string;
  answers: Record<string, SystemOneAnswer>;
  usage?: { input_tokens?: number; output_tokens?: number };
  raw: Record<string, unknown>;
}

export interface SystemOneOptions {
  model?: string;
  apiBase?: string;
  apiKey?: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

export function isDecisionModel(model: string): boolean {
  const name = model.split('/').pop()?.trim() ?? '';
  return KNOWN_DECISION_MODELS.has(name) || name.startsWith('tev1');
}

export function choiceQuestion(
  instructions: string,
  criteria: Record<string, string>,
): QuestionSpec {
  return { type: 'choice', instructions, criteria };
}

export function noulQuestion(instructions: string): QuestionSpec {
  return { type: 'noul', instructions };
}

export function scoreQuestion(instructions: string, criteria: string[]): QuestionSpec {
  return { type: 'score', instructions, criteria: [...criteria] };
}

export function resolveSystemOneBaseUrl(apiBase?: string): string {
  if (apiBase) return apiBase.replace(/\/+$/, '');
  const fromEnv =
    (typeof process !== 'undefined' && process.env?.TYPESAFE_BASE_URL) ||
    (typeof process !== 'undefined' && process.env?.OLLAMA_HOST) ||
    'http://127.0.0.1:11434';
  return fromEnv.replace(/\/+$/, '');
}

function defaultApiKey(apiKey?: string): string | undefined {
  if (apiKey !== undefined) return apiKey;
  if (typeof process === 'undefined') return 'ollama';
  return process.env.TYPESAFE_API_KEY || process.env.OLLAMA_API_KEY || 'ollama';
}

export async function systemOne(
  state: Record<string, unknown>,
  questions: Record<string, QuestionSpec>,
  options: SystemOneOptions = {},
): Promise<SystemOneResult> {
  const fetchFn = options.fetchImpl ?? fetch;
  const base = resolveSystemOneBaseUrl(options.apiBase);
  const model =
    options.model ||
    (typeof process !== 'undefined' && process.env.TYPESAFE_DEFAULT_MODEL) ||
    (typeof process !== 'undefined' && process.env.OLLAMA_DECISION_MODEL) ||
    'nimble';
  const url = `${base}/v1/systemone`;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  };
  const key = defaultApiKey(options.apiKey);
  if (key) headers.Authorization = `Bearer ${key}`;

  const controller = new AbortController();
  const timeoutMs = options.timeoutMs ?? 120_000;
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetchFn(url, {
      method: 'POST',
      headers,
      body: JSON.stringify({ model, state, questions }),
      signal: controller.signal,
    });
    const text = await res.text();
    if (!res.ok) {
      throw new Error(`system_one HTTP ${res.status}: ${text.slice(0, 2000)}`);
    }
    const data = JSON.parse(text) as {
      model?: string;
      answers?: Record<string, SystemOneAnswer>;
      usage?: SystemOneResult['usage'];
    };
    return {
      model: data.model ?? model,
      answers: data.answers ?? {},
      usage: data.usage,
      raw: data as Record<string, unknown>,
    };
  } finally {
    clearTimeout(timer);
  }
}

export function getChoice(result: SystemOneResult, name: string): string | undefined {
  const a = result.answers[name];
  return a?.type === 'choice' ? a.choice : undefined;
}

export function getNoul(result: SystemOneResult, name: string): number | undefined {
  const a = result.answers[name];
  return a?.type === 'noul' ? a.noul : undefined;
}

export function getScore(result: SystemOneResult, name: string): number | undefined {
  const a = result.answers[name];
  return a?.type === 'score' ? a.score : undefined;
}
