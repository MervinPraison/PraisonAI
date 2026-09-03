/**
 * Self-reflection (Python parity: `Agent(reflection=...)`, `ReflectionConfig`,
 * and the reflection loop in `agent/chat_mixin.py`).
 *
 * After the model answers, it is asked to critique its own response and to
 * say whether the answer is satisfactory. An unsatisfactory answer is
 * regenerated using the critique, up to `maxIterations` times; a
 * satisfactory verdict only counts once `minIterations` reflections have run.
 *
 * The loop is written against a `complete(messages, schema?)` callback so it
 * can be tested without a provider and so the Agent decides which transport
 * (OpenAI-compatible service or AI SDK backend) performs the calls.
 */

/** Resolved reflection settings (Python `ReflectionConfig`). */
export interface ReflectionConfig {
  /** Reflections that must run before a "yes" is accepted (Python `min_iterations`, default 1). */
  minIterations: number;
  /** Upper bound on reflection rounds (Python `max_iterations`, default 3). */
  maxIterations: number;
  /** Model used for the critique, when different from the agent's (Python `llm`). */
  llm?: string;
  /** Custom critique instruction (Python `prompt`). */
  prompt?: string;
}

/** Python `REFLECTION_PRESETS`. */
export const REFLECTION_PRESETS: Readonly<Record<string, Pick<ReflectionConfig, 'minIterations' | 'maxIterations'>>> = Object.freeze({
  minimal: { minIterations: 1, maxIterations: 1 },
  standard: { minIterations: 1, maxIterations: 3 },
  thorough: { minIterations: 2, maxIterations: 5 },
});

/** Python's default critique instruction. */
export const DEFAULT_REFLECTION_INSTRUCTION = 'Identify any flaws, improvements, or actions.';

/** Python: "Now regenerate your response using the reflection you made". */
export const REGENERATE_PROMPT = 'Now regenerate your response using the reflection you made';

/** Structured-output schema for the critique (Python `ReflectionOutput`). */
export const REFLECTION_OUTPUT_SCHEMA: Record<string, unknown> = {
  type: 'object',
  properties: {
    reflection: { type: 'string' },
    satisfactory: { type: 'string', enum: ['yes', 'no'] },
  },
  required: ['reflection', 'satisfactory'],
  additionalProperties: false,
};

/**
 * Turn the constructor option into a config. `true` uses Python's defaults,
 * a string names a preset, an object supplies fields (snake_case accepted).
 * Unknown presets throw, as Python's resolver does.
 */
export function resolveReflection(
  input: boolean | string | Record<string, unknown> | undefined | null
): ReflectionConfig | undefined {
  if (input === undefined || input === null || input === false) return undefined;
  if (input === true) return { minIterations: 1, maxIterations: 3 };
  if (typeof input === 'string') {
    const preset = REFLECTION_PRESETS[input.trim().toLowerCase()];
    if (!preset) {
      throw new Error(
        `Invalid reflection preset "${input}". Valid presets: ${Object.keys(REFLECTION_PRESETS).join(', ')}`
      );
    }
    return { ...preset };
  }
  const min = numberField(input, 'minIterations', 'min_iterations') ?? 1;
  const max = numberField(input, 'maxIterations', 'max_iterations') ?? 3;
  const llm = stringField(input, 'llm');
  const prompt = stringField(input, 'prompt');
  return { minIterations: Math.max(1, min), maxIterations: Math.max(1, max), llm, prompt };
}

function numberField(obj: Record<string, unknown>, ...keys: string[]): number | undefined {
  for (const k of keys) {
    const v = obj[k];
    if (typeof v === 'number' && Number.isFinite(v)) return v;
  }
  return undefined;
}

function stringField(obj: Record<string, unknown>, ...keys: string[]): string | undefined {
  for (const k of keys) {
    const v = obj[k];
    if (typeof v === 'string' && v.length > 0) return v;
  }
  return undefined;
}

/** Python's reflection prompt, verbatim in structure. */
export function buildReflectionPrompt(response: string, instruction?: string): string {
  return [
    '',
    `Reflect on your previous response: '${response}'.`,
    instruction || DEFAULT_REFLECTION_INSTRUCTION,
    `Provide a "satisfactory" status ('yes' or 'no').`,
    `Output MUST be JSON with 'reflection' and 'satisfactory'.`,
    '',
  ].join('\n');
}

export interface ReflectionOutput {
  reflection: string;
  satisfactory: 'yes' | 'no';
}

/**
 * Parse the critique. Accepts a bare JSON object or one wrapped in a code
 * fence (Python `clean_json_output`). Throws when no verdict can be read.
 */
export function parseReflectionOutput(text: string): ReflectionOutput {
  let candidate = text.trim();
  const fenced = candidate.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fenced) candidate = fenced[1].trim();
  const start = candidate.indexOf('{');
  const end = candidate.lastIndexOf('}');
  if (start >= 0 && end > start) candidate = candidate.slice(start, end + 1);
  const parsed = JSON.parse(candidate) as Record<string, unknown>;
  const verdict = String(parsed.satisfactory ?? '').trim().toLowerCase();
  if (verdict !== 'yes' && verdict !== 'no') {
    throw new Error(`Reflection output has no yes/no "satisfactory" field: ${text}`);
  }
  return { reflection: String(parsed.reflection ?? ''), satisfactory: verdict };
}

/** A conversation message as the loop manipulates it. */
export interface ReflectionMessage {
  role: string;
  content: string | null;
  [key: string]: unknown;
}

export interface ReflectionRound {
  reflection: string;
  satisfactory: 'yes' | 'no';
  /** The response the critique was about. */
  response: string;
}

export interface RunReflectionLoopOptions {
  /** The model's first answer. */
  response: string;
  /** The conversation so far (system + history + prompt). Mutated: the critique exchange is appended. */
  messages: ReflectionMessage[];
  config: ReflectionConfig;
  /**
   * Ask the model for a completion of `messages`. When `schema` is given the
   * call is for the structured critique; the Agent may honour it with
   * response_format or ignore it and rely on the prompt.
   */
  complete: (messages: ReflectionMessage[], schema?: Record<string, unknown>) => Promise<string>;
  /** Observer for each critique (Python's `display_self_reflection`). */
  onReflection?: (round: ReflectionRound) => void;
}

/**
 * Run Python's reflection loop and return the accepted response together
 * with every critique that was made.
 */
export async function runReflectionLoop(opts: RunReflectionLoopOptions): Promise<{ response: string; rounds: ReflectionRound[] }> {
  const { config, messages, complete } = opts;
  const rounds: ReflectionRound[] = [];
  let response = opts.response;
  let count = 0;

  for (;;) {
    messages.push({ role: 'user', content: buildReflectionPrompt(response, config.prompt) });
    let output: ReflectionOutput;
    try {
      const raw = await complete(messages, REFLECTION_OUTPUT_SCHEMA);
      output = parseReflectionOutput(raw);
    } catch {
      // Python: a failed critique is recorded, counted, and the loop moves on.
      messages.push({ role: 'assistant', content: 'Self Reflection failed.' });
      count++;
      if (count >= config.maxIterations) return { response, rounds };
      continue;
    }
    rounds.push({ ...output, response });
    opts.onReflection?.({ ...output, response });
    messages.push({ role: 'assistant', content: `Self Reflection: ${output.reflection} Satisfactory?: ${output.satisfactory}` });

    // Only consider satisfactory after the minimum number of reflections.
    if (output.satisfactory === 'yes' && count >= config.minIterations - 1) return { response, rounds };
    if (count >= config.maxIterations - 1) return { response, rounds };

    messages.push({ role: 'user', content: REGENERATE_PROMPT });
    response = await complete(messages);
    messages.push({ role: 'assistant', content: response });
    count++;
  }
}
