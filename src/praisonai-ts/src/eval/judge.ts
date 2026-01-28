/**
 * Unified Judge class for LLM-as-judge evaluation.
 * 
 * Provides a simple, unified API for evaluating agent outputs using LLM-as-judge.
 * Follows PraisonAI naming conventions and engineering principles.
 * 
 * DRY: Reuses existing provider infrastructure.
 * Protocol-driven: Implements JudgeProtocol for extensibility.
 * Zero performance impact: Lazy imports for LLM providers.
 * 
 * @example
 * ```typescript
 * import { Judge } from 'praisonai';
 * const result = await Judge.run({ output: "4", expected: "4" });
 * console.log(`Score: ${result.score}/10`);
 * ```
 */

import { randomUUID } from 'crypto';

// ============================================================================
// Types and Interfaces
// ============================================================================

/**
 * Configuration for Judge instances.
 */
export interface JudgeConfig {
  /** LLM model to use for judging (default: gpt-4o-mini) */
  model?: string;
  /** Temperature for LLM calls (default: 0.1 for consistency) */
  temperature?: number;
  /** Maximum tokens for LLM response */
  maxTokens?: number;
  /** Score threshold for passing (default: 7.0) */
  threshold?: number;
  /** Optional custom criteria for evaluation */
  criteria?: string;
}

/**
 * Dynamic criteria configuration for domain-agnostic judging.
 * 
 * Enables judges to evaluate ANY domain, not just agent outputs:
 * - Water flow optimization
 * - Data pipeline efficiency
 * - Manufacturing quality
 * - Recipe/workflow optimization
 * - Any custom domain
 */
export interface JudgeCriteriaConfig {
  /** Name of the criteria configuration */
  name: string;
  /** Description of what is being evaluated */
  description: string;
  /** Custom prompt template with {output} placeholder */
  promptTemplate: string;
  /** List of dimensions to score (e.g., ["efficiency", "safety"]) */
  scoringDimensions: string[];
  /** Score threshold for passing (default: 7.0) */
  threshold?: number;
}

/**
 * Result from a Judge evaluation.
 * 
 * This is the unified result type for all LLM-as-judge evaluations.
 */
export interface JudgeResult {
  /** Quality score (1-10) */
  score: number;
  /** Whether the evaluation passed (score >= threshold) */
  passed: boolean;
  /** Explanation for the score */
  reasoning: string;
  /** The output that was judged */
  output: string;
  /** Optional expected output */
  expected?: string;
  /** Optional criteria used for evaluation */
  criteria?: string;
  /** List of improvement suggestions */
  suggestions: string[];
  /** When judging occurred */
  timestamp: number;
  /** Additional metadata */
  metadata?: Record<string, any>;
}

/**
 * Options for Judge.run() method
 */
export interface JudgeRunOptions {
  /** The output to judge (required if no agent) */
  output?: string;
  /** Optional expected output for accuracy evaluation */
  expected?: string;
  /** Optional criteria for criteria evaluation */
  criteria?: string;
  /** Optional input context */
  input?: string;
  /** Optional Agent to run and judge */
  agent?: any;
  /** Optional Agents to run and judge */
  agents?: any;
  /** Whether to print result summary */
  printSummary?: boolean;
}

/**
 * Constructor options for Judge class
 */
export interface JudgeOptions {
  /** LLM model to use */
  model?: string;
  /** Temperature for LLM calls */
  temperature?: number;
  /** Maximum tokens for response */
  maxTokens?: number;
  /** Score threshold for passing */
  threshold?: number;
  /** Custom criteria for evaluation */
  criteria?: string;
  /** Full JudgeConfig object */
  config?: JudgeConfig;
  /** Domain-agnostic criteria config */
  criteriaConfig?: JudgeCriteriaConfig;
  /** Session ID for trace isolation */
  sessionId?: string;
}

/**
 * Protocol interface for Judge implementations
 */
export interface JudgeProtocol {
  run(options: JudgeRunOptions): Promise<JudgeResult>;
  runAsync(options: JudgeRunOptions): Promise<JudgeResult>;
}

// ============================================================================
// Prompt Templates
// ============================================================================

/** Default prompt for accuracy evaluation */
const ACCURACY_PROMPT = `You are an expert evaluator. Compare the actual output against the expected output.

INPUT: {input}

EXPECTED OUTPUT:
{expected}

ACTUAL OUTPUT:
{output}

Scoring Guidelines:
- 10: Perfect match in meaning and completeness
- 8-9: Very close, minor differences that don't affect correctness
- 6-7: Mostly correct but missing some details or has minor errors
- 4-5: Partially correct but significant issues
- 2-3: Mostly incorrect but shows some understanding
- 1: Completely wrong or irrelevant

Respond in this EXACT format:
SCORE: [number 1-10]
REASONING: [brief explanation]
SUGGESTIONS:
- [improvement suggestion 1]
- [improvement suggestion 2]
`;

/** Default prompt for criteria evaluation */
const CRITERIA_PROMPT = `You are an expert evaluator. Evaluate the output against the given criteria.

CRITERIA: {criteria}

OUTPUT TO EVALUATE:
{output}

Score the output from 1-10 based on how well it meets the criteria.
- 10: Perfectly meets all criteria
- 8-9: Meets criteria very well with minor issues
- 6-7: Meets most criteria but has some gaps
- 4-5: Partially meets criteria
- 2-3: Barely meets criteria
- 1: Does not meet criteria at all

Respond in this EXACT format:
SCORE: [number 1-10]
REASONING: [brief explanation]
SUGGESTIONS:
- [improvement suggestion 1]
- [improvement suggestion 2]
`;

/** Default prompt for general quality evaluation */
const GENERAL_PROMPT = `You are an expert evaluator for AI agent outputs. Your task is to grade the quality of an agent's response.

INPUT (what the agent was asked):
{input}

AGENT OUTPUT (what the agent responded):
{output}

GRADING CRITERIA:
- Accuracy: Is the response factually correct?
- Completeness: Does it fully address the input?
- Clarity: Is it well-written and easy to understand?
- Relevance: Does it stay on topic?

SCORING GUIDELINES:
- 10: Perfect - Excellent in all criteria
- 8-9: Very Good - Minor improvements possible
- 6-7: Good - Some issues but mostly correct
- 4-5: Fair - Significant issues
- 2-3: Poor - Major problems
- 1: Very Poor - Completely wrong or irrelevant

Respond in this EXACT format:
SCORE: [number 1-10]
REASONING: [brief explanation of the score]
SUGGESTIONS:
- [first suggestion for improvement]
- [second suggestion if applicable]
`;

/** Recipe evaluation prompt */
const RECIPE_PROMPT = `You are an expert evaluator for AI agent workflow recipes.

RECIPE OUTPUT TO EVALUATE:
{output}

EXPECTED BEHAVIOR:
{expected}

EVALUATION CRITERIA:
{criteria}

Evaluate the recipe execution on:
1. Task completion (1-10): Did agents complete their assigned tasks?
2. Context flow (1-10): Was context properly passed between agents?
3. Output quality (1-10): Is the final output useful and accurate?

Respond in this EXACT format:
SCORE: [average of above, 1-10]
REASONING: [brief explanation]
SUGGESTIONS:
- [improvement suggestion 1]
- [improvement suggestion 2]
`;

// ============================================================================
// Response Parsing
// ============================================================================

/**
 * Parse LLM response into JudgeResult.
 * 
 * @param responseText - Raw LLM response
 * @param output - Original output
 * @param expected - Original expected output
 * @param criteria - Original criteria
 * @param threshold - Score threshold for passing
 * @returns JudgeResult with score, passed, reasoning, suggestions
 */
export function parseJudgeResponse(
  responseText: string,
  output: string,
  expected: string | null,
  criteria: string | null,
  threshold: number
): JudgeResult {
  let score = 5.0;
  let reasoning = 'Unable to parse response';
  const suggestions: string[] = [];

  const lines = responseText.trim().split('\n');
  let inSuggestions = false;

  for (const rawLine of lines) {
    const line = rawLine.trim();

    if (line.startsWith('SCORE:')) {
      try {
        const scoreStr = line.replace('SCORE:', '').trim();
        score = parseFloat(scoreStr);
        // Clamp to valid range
        score = Math.max(1.0, Math.min(10.0, score));
      } catch {
        // Keep default
      }
    } else if (line.startsWith('REASONING:')) {
      reasoning = line.replace('REASONING:', '').trim();
    } else if (line.startsWith('SUGGESTIONS:')) {
      inSuggestions = true;
      const rest = line.replace('SUGGESTIONS:', '').trim();
      if (rest.toLowerCase() !== 'none' && rest) {
        suggestions.push(rest);
      }
    } else if (inSuggestions && line.startsWith('-')) {
      const suggestion = line.replace(/^-\s*/, '').trim();
      if (suggestion && suggestion.toLowerCase() !== 'none') {
        suggestions.push(suggestion);
      }
    }
  }

  return {
    score,
    passed: score >= threshold,
    reasoning,
    output,
    expected: expected ?? undefined,
    criteria: criteria ?? undefined,
    suggestions,
    timestamp: Date.now(),
  };
}

// ============================================================================
// Judge Class
// ============================================================================

/**
 * Unified LLM-as-judge for evaluating agent outputs.
 * 
 * Provides a simple API for:
 * - Accuracy evaluation (comparing output to expected)
 * - Criteria evaluation (evaluating against custom criteria)
 * - Custom evaluation (subclass for domain-specific judges)
 * 
 * @example
 * ```typescript
 * // Simple accuracy check
 * const result = await new Judge().run({ output: "4", expected: "4" });
 * 
 * // Custom criteria
 * const result = await new Judge({ criteria: "Response is helpful" }).run({ output: "Hello!" });
 * 
 * // With agent
 * const result = await new Judge().run({ agent: myAgent, input: "2+2", expected: "4" });
 * ```
 */
export class Judge implements JudgeProtocol {
  readonly model: string;
  readonly temperature: number;
  readonly maxTokens: number;
  readonly threshold: number;
  readonly criteria: string | null;
  readonly criteriaConfig: JudgeCriteriaConfig | null;
  readonly sessionId: string | null;

  constructor(options: JudgeOptions = {}) {
    // Use config if provided, otherwise use individual params
    const config = options.config;
    
    this.model = options.model ?? config?.model ?? process.env.OPENAI_MODEL_NAME ?? 'gpt-4o-mini';
    this.temperature = options.temperature ?? config?.temperature ?? 0.1;
    this.maxTokens = options.maxTokens ?? config?.maxTokens ?? 500;
    this.threshold = options.threshold ?? config?.threshold ?? options.criteriaConfig?.threshold ?? 7.0;
    this.criteria = options.criteria ?? config?.criteria ?? options.criteriaConfig?.description ?? null;
    this.criteriaConfig = options.criteriaConfig ?? null;
    this.sessionId = options.sessionId ?? null;
  }

  /**
   * Build the appropriate prompt based on evaluation type.
   */
  protected buildPrompt(
    output: string,
    expected: string | null,
    criteria: string | null,
    input: string
  ): string {
    // Use criteriaConfig custom prompt template if available
    if (this.criteriaConfig?.promptTemplate) {
      return this.criteriaConfig.promptTemplate
        .replace('{output}', output)
        .replace('{input}', input || 'Not provided')
        .replace('{input_text}', input || 'Not provided')
        .replace('{expected}', expected || 'Not specified');
    }

    // Use instance criteria if not provided
    const effectiveCriteria = criteria ?? this.criteria;

    if (expected !== null) {
      // Accuracy mode
      return ACCURACY_PROMPT
        .replace('{input}', input || 'Not provided')
        .replace('{expected}', expected)
        .replace('{output}', output);
    } else if (effectiveCriteria) {
      // Criteria mode
      return CRITERIA_PROMPT
        .replace('{criteria}', effectiveCriteria)
        .replace('{output}', output);
    } else {
      // Default: general quality evaluation
      return GENERAL_PROMPT
        .replace('{input}', input || 'Not provided')
        .replace('{output}', output);
    }
  }

  /**
   * Get LLM provider lazily.
   */
  protected async getProvider(): Promise<any> {
    // Lazy import to avoid performance impact
    const { createProvider } = await import('../llm/providers');
    return createProvider(this.model);
  }

  /**
   * Get output from an Agent.
   */
  protected async getAgentOutput(agent: any, input: string): Promise<string> {
    if (typeof agent.chat === 'function') {
      return String(await agent.chat(input));
    } else if (typeof agent.start === 'function') {
      const result = await agent.start(input);
      if (result && typeof result === 'object' && 'raw' in result) {
        return String(result.raw);
      }
      return String(result);
    }
    throw new Error("Agent must have 'chat' or 'start' method");
  }

  /**
   * Get output from Agents (multi-agent).
   */
  protected async getAgentsOutput(agents: any, input: string): Promise<string> {
    if (typeof agents.start === 'function') {
      const result = await agents.start(input);
      if (result && typeof result === 'object' && 'raw' in result) {
        return String(result.raw);
      }
      return String(result);
    }
    throw new Error("Agents must have 'start' method");
  }

  /**
   * Judge an output.
   * 
   * @param options - Evaluation options
   * @returns JudgeResult with score, passed, reasoning, suggestions
   */
  async run(options: JudgeRunOptions): Promise<JudgeResult> {
    let output = options.output ?? '';

    // Get output from agent if provided
    if (options.agent) {
      output = await this.getAgentOutput(options.agent, options.input ?? '');
    } else if (options.agents) {
      output = await this.getAgentsOutput(options.agents, options.input ?? '');
    }

    if (!output) {
      return {
        score: 0,
        passed: false,
        reasoning: 'No output provided to judge',
        output: '',
        expected: options.expected,
        criteria: options.criteria ?? this.criteria ?? undefined,
        suggestions: [],
        timestamp: Date.now(),
      };
    }

    try {
      const provider = await this.getProvider();
      const prompt = this.buildPrompt(
        output,
        options.expected ?? null,
        options.criteria ?? null,
        options.input ?? ''
      );

      const response = await provider.generateText({
        messages: [{ role: 'user', content: prompt }],
        temperature: this.temperature,
        maxTokens: this.maxTokens,
      });

      const responseText = response.text ?? '';
      const result = parseJudgeResponse(
        responseText,
        output,
        options.expected ?? null,
        options.criteria ?? this.criteria,
        this.threshold
      );

      if (options.printSummary) {
        this.printSummary(result);
      }

      return result;
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      return {
        score: 0,
        passed: false,
        reasoning: `Evaluation error: ${errorMessage}`,
        output,
        expected: options.expected,
        criteria: options.criteria ?? this.criteria ?? undefined,
        suggestions: [],
        timestamp: Date.now(),
      };
    }
  }

  /**
   * Judge an output asynchronously (alias for run).
   */
  async runAsync(options: JudgeRunOptions): Promise<JudgeResult> {
    return this.run(options);
  }

  /**
   * Print a summary of the judge result.
   */
  printSummary(result: JudgeResult): void {
    const status = result.passed ? '✅ PASSED' : '❌ FAILED';
    console.log(`\n=== Judge Result ===`);
    console.log(`Score: ${result.score.toFixed(1)}/10`);
    console.log(`Status: ${status}`);
    console.log(`Reasoning: ${result.reasoning}`);
    if (result.suggestions.length > 0) {
      console.log(`Suggestions:`);
      result.suggestions.forEach(s => console.log(`  - ${s}`));
    }
  }
}

// ============================================================================
// Built-in Judge Types
// ============================================================================

/**
 * Judge for accuracy evaluation (comparing output to expected).
 */
export class AccuracyJudge extends Judge {}

/**
 * Judge for criteria-based evaluation.
 */
export class CriteriaJudge extends Judge {}

/**
 * Judge for evaluating recipe/workflow execution traces.
 */
export class RecipeJudge extends Judge {
  readonly mode: string;

  constructor(options: JudgeOptions & { mode?: string } = {}) {
    const criteria = `Recipe execution quality in ${options.mode ?? 'context'} mode`;
    super({
      ...options,
      criteria,
      maxTokens: options.maxTokens ?? 800,
    });
    this.mode = options.mode ?? 'context';
  }

  protected buildPrompt(
    output: string,
    expected: string | null,
    criteria: string | null,
    input: string
  ): string {
    return RECIPE_PROMPT
      .replace('{output}', output)
      .replace('{expected}', expected ?? 'Complete workflow execution')
      .replace('{criteria}', criteria ?? this.criteria ?? `Recipe quality in ${this.mode} mode`);
  }
}

// ============================================================================
// Judge Registry
// ============================================================================

type JudgeConstructor = new (options?: JudgeOptions) => Judge;

const JUDGE_REGISTRY: Map<string, JudgeConstructor> = new Map([
  ['accuracy', AccuracyJudge],
  ['criteria', CriteriaJudge],
  ['recipe', RecipeJudge],
]);

/**
 * Register a custom judge type.
 * 
 * @param name - Name for the judge type
 * @param judgeClass - Judge class to register
 */
export function addJudge(name: string, judgeClass: JudgeConstructor): void {
  JUDGE_REGISTRY.set(name.toLowerCase(), judgeClass);
}

/**
 * Get a registered judge type by name.
 * 
 * @param name - Name of the judge type
 * @returns Judge class or undefined if not found
 */
export function getJudge(name: string): JudgeConstructor | undefined {
  return JUDGE_REGISTRY.get(name.toLowerCase());
}

/**
 * List all registered judge types.
 * 
 * @returns List of judge type names
 */
export function listJudges(): string[] {
  return Array.from(JUDGE_REGISTRY.keys());
}

/**
 * Remove a registered judge type.
 * 
 * @param name - Name of the judge type to remove
 * @returns True if removed, false if not found
 */
export function removeJudge(name: string): boolean {
  return JUDGE_REGISTRY.delete(name.toLowerCase());
}

// ============================================================================
// Optimization Rule Registry
// ============================================================================

type OptimizationRuleConstructor = new (...args: any[]) => any;

const OPTIMIZATION_RULE_REGISTRY: Map<string, OptimizationRuleConstructor> = new Map();

/**
 * Register a custom optimization rule.
 * 
 * @param name - Name for the rule
 * @param ruleClass - Rule class implementing OptimizationRuleProtocol
 */
export function addOptimizationRule(name: string, ruleClass: OptimizationRuleConstructor): void {
  OPTIMIZATION_RULE_REGISTRY.set(name.toLowerCase(), ruleClass);
}

/**
 * Get a registered optimization rule by name.
 * 
 * @param name - Name of the rule
 * @returns Rule class or undefined if not found
 */
export function getOptimizationRule(name: string): OptimizationRuleConstructor | undefined {
  return OPTIMIZATION_RULE_REGISTRY.get(name.toLowerCase());
}

/**
 * List all registered optimization rules.
 * 
 * @returns List of rule names
 */
export function listOptimizationRules(): string[] {
  return Array.from(OPTIMIZATION_RULE_REGISTRY.keys());
}

/**
 * Remove a registered optimization rule.
 * 
 * @param name - Name of the rule to remove
 * @returns True if removed, false if not found
 */
export function removeOptimizationRule(name: string): boolean {
  return OPTIMIZATION_RULE_REGISTRY.delete(name.toLowerCase());
}

// ============================================================================
// Exports
// ============================================================================

export default Judge;
