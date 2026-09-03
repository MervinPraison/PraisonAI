/**
 * Prompt templates (Python parity: `Agent(templates=...)` / `TemplateConfig`,
 * which consolidates `system_template`, `prompt_template`,
 * `response_template` and `use_system_prompt`).
 *
 * - `system`: replaces the instructions as the system prompt. Placeholders
 *   `{instructions}`, `{role}`, `{goal}`, `{backstory}` and `{name}` are
 *   substituted.
 * - `prompt`: wraps the user prompt; `{input}` is substituted (appended when
 *   the template has no placeholder).
 * - `response`: either a wrapper applied to the answer (`{response}`
 *   placeholder) or, without one, a formatting instruction added to the
 *   system prompt.
 * - `useSystemPrompt: false`: no system message is sent at all.
 */

export interface TemplateConfig {
  system?: string;
  prompt?: string;
  response?: string;
  useSystemPrompt: boolean;
}

export interface SystemTemplateVars {
  instructions: string;
  name?: string;
  role?: string;
  goal?: string;
  backstory?: string;
}

function optionalString(obj: Record<string, unknown>, key: string): string | undefined {
  const v = obj[key];
  if (v === undefined || v === null) return undefined;
  if (typeof v !== 'string') throw new Error(`templates.${key} must be a string`);
  return v;
}

/** Resolve the constructor option (snake_case `use_system_prompt` accepted). */
export function resolveTemplates(input: Record<string, unknown> | undefined | null): TemplateConfig | undefined {
  if (input === undefined || input === null) return undefined;
  if (typeof input !== 'object') throw new Error('templates must be an object with system/prompt/response/useSystemPrompt');
  const useRaw = input.useSystemPrompt ?? input.use_system_prompt;
  if (useRaw !== undefined && typeof useRaw !== 'boolean') throw new Error('templates.useSystemPrompt must be a boolean');
  const known = new Set(['system', 'prompt', 'response', 'useSystemPrompt', 'use_system_prompt']);
  const unknown = Object.keys(input).filter((k) => !known.has(k));
  if (unknown.length > 0) {
    throw new Error(`Unknown templates field(s): ${unknown.join(', ')}. Valid fields: system, prompt, response, useSystemPrompt`);
  }
  return {
    system: optionalString(input, 'system'),
    prompt: optionalString(input, 'prompt'),
    response: optionalString(input, 'response'),
    useSystemPrompt: (useRaw as boolean | undefined) ?? true,
  };
}

/** Substitute `{key}` placeholders; unknown placeholders are left as written. */
export function renderTemplate(template: string, vars: Record<string, string | undefined>): string {
  return template.replace(/\{([a-zA-Z_][a-zA-Z0-9_]*)\}/g, (match, key: string) => {
    const value = vars[key];
    return value === undefined ? match : value;
  });
}

/** The system prompt body: the rendered `system` template, else the instructions. */
export function applySystemTemplate(config: TemplateConfig | undefined, vars: SystemTemplateVars): string {
  if (!config?.system) return vars.instructions;
  return renderTemplate(config.system, {
    instructions: vars.instructions,
    name: vars.name,
    role: vars.role,
    goal: vars.goal,
    backstory: vars.backstory,
  });
}

/** Wrap the user prompt with the `prompt` template. */
export function applyPromptTemplate(config: TemplateConfig | undefined, input: string): string {
  if (!config?.prompt) return input;
  if (config.prompt.includes('{input}')) return renderTemplate(config.prompt, { input });
  return `${config.prompt}\n\n${input}`;
}

/** Whether the response template is a wrapper (has `{response}`) rather than an instruction. */
export function responseTemplateIsWrapper(config: TemplateConfig | undefined): boolean {
  return Boolean(config?.response && config.response.includes('{response}'));
}

/** Apply a `{response}` wrapper template to the model's answer. */
export function applyResponseTemplate(config: TemplateConfig | undefined, response: string): string {
  if (!responseTemplateIsWrapper(config)) return response;
  return renderTemplate(config!.response!, { response });
}
