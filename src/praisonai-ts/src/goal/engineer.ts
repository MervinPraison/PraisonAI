/**
 * GoalEngineer - the core Goal Engineering entry point.
 *
 * Python parity: praisonaiagents/goal/engineer.py. Goal Engineering is the
 * systematic practice of turning a vague objective into a structured,
 * measurable {@link Goal} (statement + weighted success criteria +
 * constraints), then verifying an output against it.
 *
 * @example
 * const engineer = new GoalEngineer({ autoDecompose: false });
 * const goal = await engineer.engineer('Summarise the report in under 100 words');
 * goal.addCriterion('Summary is under 100 words');
 * const result = await engineer.verify(goal, 'A concise summary...');
 * console.log(result.score, result.achieved);
 *
 * Zero performance impact: the LLM client and the Judge are created lazily.
 */

import { Judge } from '../eval/judge';
import type { GenerateTextOptions } from '../llm/providers/types';
import { Logger } from '../utils/logger';
import { GoalConfig, GoalConfigOptions } from './config';
import { Goal, GoalVerificationResult, SuccessCriterion, CriterionStatus } from './models';

/** Python parity: goal/engineer.py:36 `_DECOMPOSE_PROMPT`. */
const DECOMPOSE_PROMPT = `You are a goal-engineering assistant. Break the following goal into at most {max_criteria} concise, measurable success criteria.

GOAL: {statement}

Return ONLY a JSON array of short strings, e.g. ["criterion 1", "criterion 2"].
Each criterion must be objectively checkable.`;

/**
 * Minimal LLM surface the engineer needs. {@link BaseLLM} from `src/llm`
 * satisfies it structurally; tests can pass a stub.
 */
export interface GoalLLM {
  generate(prompt: string): Promise<string | { text: string }>;
}

/** Constructor options for {@link GoalEngineer} (goal/engineer.py:58-66). */
export interface GoalEngineerOptions {
  /** LLM model for decomposition/verification (overrides config) (default null). */
  model?: string | null;
  /** Max number of success criteria to generate (default null -> config). */
  maxCriteria?: number | null;
  /** Score (0-10) at/above which a goal is achieved (default null -> config). */
  threshold?: number | null;
  /** Auto-generate criteria via the LLM when engineering (default null -> config). */
  autoDecompose?: boolean | null;
  /** A full {@link GoalConfig} (takes precedence over kwargs) (default null). */
  config?: GoalConfig | GoalConfigOptions | null;
  /** Enable verbose logging (default false). */
  verbose?: boolean;
  /**
   * TypeScript-only: injectable LLM used for both decomposition and
   * verification. Defaults to `BaseLLM({ model: config.model })` for
   * decomposition and the eval {@link Judge} (which resolves its own provider
   * from `config.model`) for verification.
   */
  llm?: GoalLLM;
}

/**
 * Engineers structured, measurable goals and verifies outputs against them.
 *
 * Python parity: goal/engineer.py:45 `GoalEngineer`.
 */
export class GoalEngineer {
  config: GoalConfig;
  private readonly llm: GoalLLM | null;
  private defaultLLM: GoalLLM | null = null;

  constructor(options: GoalEngineerOptions = {}) {
    this.config =
      options.config instanceof GoalConfig ? options.config : new GoalConfig(options.config ?? {});
    if (options.model != null) {
      this.config.model = options.model;
    }
    if (options.maxCriteria != null) {
      this.config.maxCriteria = options.maxCriteria;
    }
    if (options.threshold != null) {
      this.config.threshold = options.threshold;
    }
    if (options.autoDecompose != null) {
      this.config.autoDecompose = options.autoDecompose;
    }
    if (options.verbose) {
      this.config.verbose = options.verbose;
    }
    this.llm = options.llm ?? null;
  }

  /**
   * Build a structured {@link Goal} from a plain statement.
   *
   * If `criteria` are provided they are used directly. Otherwise, when
   * `autoDecompose` is enabled, the LLM proposes measurable criteria.
   *
   * Python parity: goal/engineer.py:79 `engineer(statement, criteria=None, constraints=None)`.
   */
  async engineer(
    statement: string,
    criteria: string[] | null = null,
    constraints: string[] | null = null
  ): Promise<Goal> {
    const goal = new Goal({ statement, constraints: [...(constraints ?? [])] });

    if (criteria && criteria.length > 0) {
      for (const description of criteria) {
        goal.addCriterion(description);
      }
    } else if (this.config.autoDecompose) {
      for (const description of await this.decompose(statement)) {
        goal.addCriterion(description);
      }
    }

    if (this.config.verbose) {
      Logger.info(`Engineered goal ${goal.id} with ${goal.criteria.length} criteria`);
    }
    return goal;
  }

  /**
   * Use the LLM to decompose a statement into success criteria.
   *
   * Python parity: goal/engineer.py:108 `_decompose`.
   */
  protected async decompose(statement: string): Promise<string[]> {
    const prompt = DECOMPOSE_PROMPT.replace('{max_criteria}', String(this.config.maxCriteria)).replace(
      '{statement}',
      statement
    );
    let response: string | { text: string };
    try {
      response = await (await this.getLLM()).generate(prompt);
    } catch (exc) {
      Logger.warn(`Goal decomposition failed: ${exc instanceof Error ? exc.message : String(exc)}`);
      return [];
    }
    return GoalEngineer.parseCriteria(response);
  }

  /**
   * Parse an LLM response into a list of criterion strings.
   *
   * Python parity: goal/engineer.py:129 `_parse_criteria`. A JSON array
   * anywhere in the reply wins; otherwise lines/bullets are split.
   */
  static parseCriteria(response: unknown): string[] {
    const text = responseText(response);
    const match = /\[[\s\S]*\]/.exec(text);
    if (match) {
      try {
        const items = JSON.parse(match[0]);
        if (Array.isArray(items)) {
          return items.map((i) => String(i).trim()).filter((i) => i.length > 0);
        }
      } catch {
        // Fall through to the line splitter.
      }
    }
    // Fallback: split lines/bullets (Python `lstrip("-*0123456789. ")`).
    const lines: string[] = [];
    for (const line of text.split(/\r?\n/)) {
      const cleaned = line.trim().replace(/^[-*0-9. ]+/, '').trim();
      if (cleaned) {
        lines.push(cleaned);
      }
    }
    return lines;
  }

  /**
   * Verify an `output` against a `goal` using LLM-as-judge.
   *
   * Reuses the unified eval {@link Judge} (DRY). Falls back to a neutral
   * result if the judge is unavailable: criteria stay `pending` and
   * `achieved` is false, without mutating the goal into an `unmet` state.
   *
   * Python parity: goal/engineer.py:147 `verify(goal, output)`.
   */
  async verify(goal: Goal, output: unknown): Promise<GoalVerificationResult> {
    const criteriaBlock =
      goal.criteria.map((c) => `- ${c.description}`).join('\n') || '- Achieves the stated goal';

    let criteriaText =
      'Evaluate whether the output achieves this goal.\n' +
      `Goal: ${goal.statement}\n` +
      `Success criteria:\n${criteriaBlock}`;
    if (goal.constraints.length > 0) {
      const constraintsBlock = goal.constraints.map((c) => `- ${c}`).join('\n');
      criteriaText += `\nConstraints (must not be violated):\n${constraintsBlock}`;
    }

    let score = 0.0;
    let reasoning = '';
    let verificationFailed = false;
    try {
      const judgeResult = await this.createJudge(criteriaText).run({ output: outputText(output) });
      // Judge.run swallows provider errors into this sentinel; Python's Judge raises.
      if (judgeResult.reasoning.startsWith('Evaluation error:')) {
        throw new Error(judgeResult.reasoning.replace(/^Evaluation error:\s*/, ''));
      }
      score = Number(judgeResult.score ?? 0.0) || 0.0;
      reasoning = judgeResult.reasoning ?? '';
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : String(exc);
      Logger.warn(`Goal verification failed: ${message}`);
      reasoning = `Verification unavailable: ${message}`;
      verificationFailed = true;
    }

    let achieved: boolean;
    let status: CriterionStatus;
    if (verificationFailed) {
      achieved = false;
      status = 'pending';
    } else {
      achieved = score >= this.config.threshold;
      status = achieved ? 'met' : 'unmet';
    }

    for (const criterion of goal.criteria) {
      criterion.status = status;
    }

    // Independent snapshot so mutating the result never leaks back into the goal.
    const snapshot: SuccessCriterion[] = goal.criteria.map((c) => c.clone());

    return new GoalVerificationResult({
      goalId: goal.id,
      score,
      achieved,
      criteria: snapshot,
      reasoning,
    });
  }

  /** The decomposition LLM: the injected one, else a lazily built `BaseLLM`. */
  protected async getLLM(): Promise<GoalLLM> {
    if (this.llm) {
      return this.llm;
    }
    if (!this.defaultLLM) {
      const { BaseLLM } = await import('../llm');
      this.defaultLLM = new BaseLLM({ model: this.config.model, temperature: 0.1 });
    }
    return this.defaultLLM;
  }

  /** The verification judge: routed through the injected LLM when one was given. */
  protected createJudge(criteria: string): Judge {
    if (this.llm) {
      return new InjectedLLMJudge({ model: this.config.model, criteria }, this.llm);
    }
    return new Judge({ model: this.config.model, criteria });
  }
}

/** A {@link Judge} whose provider is an injected {@link GoalLLM}. */
class InjectedLLMJudge extends Judge {
  constructor(
    options: ConstructorParameters<typeof Judge>[0],
    private readonly llm: GoalLLM
  ) {
    super(options);
  }

  protected async getProvider(): Promise<{ generateText: (o: GenerateTextOptions) => Promise<{ text: string }> }> {
    const llm = this.llm;
    return {
      async generateText(options: GenerateTextOptions): Promise<{ text: string }> {
        const prompt = options.messages.map((m) => String(m.content ?? '')).join('\n');
        return { text: responseText(await llm.generate(prompt)) };
      },
    };
  }
}

/** Python `response if isinstance(response, str) else str(response)`, unwrapping `{ text }`. */
function responseText(response: unknown): string {
  if (typeof response === 'string') {
    return response;
  }
  if (response && typeof response === 'object' && 'text' in response) {
    return String((response as { text: unknown }).text ?? '');
  }
  return response == null ? '' : String(response);
}

/** Stringify an arbitrary output the way the judge expects. */
function outputText(output: unknown): string {
  if (typeof output === 'string') {
    return output;
  }
  if (output == null) {
    return '';
  }
  if (typeof output === 'object') {
    try {
      return JSON.stringify(output);
    } catch {
      return String(output);
    }
  }
  return String(output);
}
