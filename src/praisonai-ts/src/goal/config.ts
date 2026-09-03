/**
 * Configuration for Goal Engineering.
 *
 * Python parity: praisonaiagents/goal/config.py. Follows the PraisonAI
 * `XConfig` convention: `false=disabled, true=defaults, Config=custom`.
 */

/** Constructor options for {@link GoalConfig} (goal/config.py:14-30). */
export interface GoalConfigOptions {
  /** LLM model used for decomposition/verification (default: `OPENAI_MODEL_NAME` env, then "gpt-4o-mini"). */
  model?: string | null;
  /** Maximum number of success criteria to generate (default 5). */
  maxCriteria?: number;
  /** Score (0-10) at/above which a goal is considered achieved (default 8.0). */
  threshold?: number;
  /** Whether to auto-generate criteria via the LLM (default true). */
  autoDecompose?: boolean;
  /** Enable verbose logging (default false). */
  verbose?: boolean;
}

/**
 * Configuration for the GoalEngineer.
 *
 * Python parity: goal/config.py:14 `GoalConfig` (including the
 * `__post_init__` model fallback at goal/config.py:32).
 */
export class GoalConfig {
  model: string;
  maxCriteria: number;
  threshold: number;
  autoDecompose: boolean;
  verbose: boolean;

  constructor(options: GoalConfigOptions = {}) {
    this.model = options.model ?? resolveDefaultModel();
    this.maxCriteria = options.maxCriteria ?? 5;
    this.threshold = options.threshold ?? 8.0;
    this.autoDecompose = options.autoDecompose ?? true;
    this.verbose = options.verbose ?? false;
  }
}

/** Python parity: goal/config.py:34 `os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")`. */
export function resolveDefaultModel(): string {
  const env = typeof process !== 'undefined' && process.env ? process.env.OPENAI_MODEL_NAME : undefined;
  return env ?? 'gpt-4o-mini';
}
