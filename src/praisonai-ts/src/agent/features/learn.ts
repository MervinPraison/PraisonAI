/**
 * Continuous learning configuration (Python parity: `Agent(learn=...)` /
 * `LearnConfig`, `memory/learn/manager.py` `LearnManager`).
 *
 * Only the *configuration* is resolved here, exactly as Python resolves it
 * (`True` -> agentic mode, a mode string, a dict, or a config object). The
 * `LearnManager` that captures and injects learnings lives under
 * `src/memory/learn` in a later port stream; until it exists the Agent keeps
 * a precise parity notice so the setting never vanishes silently.
 */

export type LearnMode = 'disabled' | 'agentic' | 'propose';
export type LearnScope = 'private' | 'shared' | 'global';
export type LearnBackend = 'file' | 'sqlite' | 'postgres' | 'mongodb';

export const LEARN_MODES: ReadonlySet<string> = new Set(['disabled', 'agentic', 'propose']);

export interface LearnConfig {
  persona: boolean;
  insights: boolean;
  thread: boolean;
  patterns: boolean;
  decisions: boolean;
  feedback: boolean;
  improvements: boolean;
  nudgeInterval: number;
  nudgeMinToolIters: number;
  proposeSkills: boolean;
  mode: LearnMode;
  scope: LearnScope;
  backend: LearnBackend | string;
  dbUrl?: string;
  storePath?: string;
  maxEntries: number;
  retentionDays: number;
  llm?: string;
}

function bool(obj: Record<string, unknown>, camel: string, snake: string, fallback: boolean): boolean {
  const v = obj[camel] ?? obj[snake];
  return typeof v === 'boolean' ? v : fallback;
}
function num(obj: Record<string, unknown>, camel: string, snake: string, fallback: number): number {
  const v = obj[camel] ?? obj[snake];
  return typeof v === 'number' && Number.isFinite(v) ? v : fallback;
}
function str(obj: Record<string, unknown>, camel: string, snake: string): string | undefined {
  const v = obj[camel] ?? obj[snake];
  return typeof v === 'string' ? v : undefined;
}

/**
 * Resolve the constructor option. Mirrors `agent/agent.py`: `true` enables
 * agentic mode, a string names a mode, an object supplies fields
 * (snake_case accepted). Unknown modes disable learning with a warning, as
 * Python does.
 */
export function resolveLearnConfig(
  input: boolean | string | Record<string, unknown> | undefined | null,
  warn: (message: string) => void = () => {}
): LearnConfig | undefined {
  if (input === undefined || input === null || input === false) return undefined;
  let raw: Record<string, unknown>;
  if (input === true) raw = { mode: 'agentic' };
  else if (typeof input === 'string') {
    const mode = input.trim().toLowerCase();
    if (!LEARN_MODES.has(mode)) {
      warn(`Unsupported learn= value "${input}"; expected true, "disabled", "agentic", "propose", or a config object. Learning disabled.`);
      return undefined;
    }
    if (mode === 'disabled') return undefined;
    raw = { mode };
  } else if (typeof input === 'object') raw = input;
  else {
    warn(`Unsupported learn= value ${String(input)}; learning disabled.`);
    return undefined;
  }

  const modeRaw = (str(raw, 'mode', 'mode') ?? 'disabled').toLowerCase();
  if (!LEARN_MODES.has(modeRaw)) throw new Error(`Invalid learn mode "${modeRaw}". Valid modes: disabled, agentic, propose`);
  return {
    persona: bool(raw, 'persona', 'persona', true),
    insights: bool(raw, 'insights', 'insights', true),
    thread: bool(raw, 'thread', 'thread', true),
    patterns: bool(raw, 'patterns', 'patterns', false),
    decisions: bool(raw, 'decisions', 'decisions', false),
    feedback: bool(raw, 'feedback', 'feedback', false),
    improvements: bool(raw, 'improvements', 'improvements', false),
    nudgeInterval: num(raw, 'nudgeInterval', 'nudge_interval', 0),
    nudgeMinToolIters: num(raw, 'nudgeMinToolIters', 'nudge_min_tool_iters', 3),
    proposeSkills: bool(raw, 'proposeSkills', 'propose_skills', false),
    mode: modeRaw as LearnMode,
    scope: (str(raw, 'scope', 'scope') ?? 'private') as LearnScope,
    backend: str(raw, 'backend', 'backend') ?? 'file',
    dbUrl: str(raw, 'dbUrl', 'db_url'),
    storePath: str(raw, 'storePath', 'store_path'),
    maxEntries: num(raw, 'maxEntries', 'max_entries', 0),
    retentionDays: num(raw, 'retentionDays', 'retention_days', 0),
    llm: str(raw, 'llm', 'llm'),
  };
}
