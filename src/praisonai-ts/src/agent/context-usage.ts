// The compaction table is not a reliable meter source (for example it lists
// GPT-5 as 1M rather than the provider-documented 400,000). Only resolve
// explicitly verified model identifiers here.
// https://developers.openai.com/api/docs/models/gpt-4o
// https://developers.openai.com/api/docs/models/gpt-4.1
// https://developers.openai.com/api/docs/models/gpt-5
const KNOWN_WINDOWS: Readonly<Record<string, number>> = {
  'gpt-4o': 128000,
  'gpt-4o-2024-05-13': 128000,
  'gpt-4o-2024-08-06': 128000,
  'gpt-4o-2024-11-20': 128000,
  'gpt-4o-mini': 128000,
  'gpt-4o-mini-2024-07-18': 128000,
  'gpt-4.1': 1047576,
  'gpt-4.1-2025-04-14': 1047576,
  'gpt-4.1-mini': 1047576,
  'gpt-4.1-mini-2025-04-14': 1047576,
  'gpt-4.1-nano': 1047576,
  'gpt-4.1-nano-2025-04-14': 1047576,
  'gpt-5': 400000,
  'gpt-5-2025-08-07': 400000,
  'gpt-5-mini': 400000,
  'gpt-5-mini-2025-08-07': 400000,
  'gpt-5-nano': 400000,
  'gpt-5-nano-2025-08-07': 400000,
};

/** A provider-reported prompt's occupancy of its known full model window. */
export interface TurnContextUsage {
  model: string;
  inputTokens: number;
  windowTokens: number;
  percent: number;
}

/** Unknown models do not inherit the compaction budget's generic fallback. */
export function turnContextUsage(model: string | undefined, inputTokens: number | undefined): TurnContextUsage | null {
  if (!model || inputTokens === undefined || !Number.isFinite(inputTokens) || inputTokens < 0) return null;
  const normalized = model.toLowerCase();
  if (!Object.prototype.hasOwnProperty.call(KNOWN_WINDOWS, normalized)) return null;
  const windowTokens = KNOWN_WINDOWS[normalized];
  return { model, inputTokens, windowTokens, percent: Math.floor(inputTokens * 100 / windowTokens) };
}
