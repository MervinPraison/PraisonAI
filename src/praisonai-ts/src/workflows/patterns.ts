/**
 * Workflow control-flow patterns (Python parity).
 *
 * Python reference: praisonaiagents/workflows/workflows.py
 *   - Route            (decision-based branching on the previous output)
 *   - Parallel         (fan-out with a worker cap and three failure modes)
 *   - Include          (run another recipe/workflow as a step)
 *   - If / when / if_  (conditional branching on a "{{var}} > 80" string)
 *   - MAX_NESTING_DEPTH
 *
 * These classes are plain step descriptors, exactly like the Python
 * dataclasses. Execution lives in `AgentFlow.run()` (./index.ts), which walks
 * the step list and interprets each pattern.
 *
 * @example
 * ```typescript
 * import { AgentFlow, when, Parallel, Route } from 'praisonai';
 *
 * const flow = new AgentFlow({
 *   name: 'review',
 *   variables: { score: 90 },
 *   steps: [
 *     new Parallel([summariser, factChecker], 2, 'partial_ok'),
 *     when('{{score}} > 80', [approve], [reject]),
 *     new Route({ approve: [publish], reject: [revise] }),
 *   ],
 * });
 * ```
 */

import type { StepResult, WorkflowContext, Task } from './index';
import type { Loop } from './loop';
import type { Repeat } from './repeat';

// ============================================================================
// Constants
// ============================================================================

/** Maximum nesting depth for patterns (prevents runaway recursion). Python: MAX_NESTING_DEPTH = 5 */
export const MAX_NESTING_DEPTH = 5;

/** Default cap on concurrent parallel branches. Python: DEFAULT_MAX_PARALLEL_WORKERS = 3 */
export const DEFAULT_MAX_PARALLEL_WORKERS = 3;

/** Failure strategies accepted by {@link Parallel}. */
export type ParallelOnFailure = 'partial_ok' | 'fail_fast' | 'fail_all';

export const PARALLEL_ON_FAILURE_MODES: readonly ParallelOnFailure[] = ['partial_ok', 'fail_fast', 'fail_all'];

// ============================================================================
// Step typing
// ============================================================================

/** Anything with a `chat()` method (an Agent) can be used directly as a step. */
export interface AgentLikeStep {
  chat: (prompt: string, ...rest: any[]) => Promise<any> | any;
  name?: string;
}

/**
 * Minimal surface a workflow needs in order to be nested via {@link Include}.
 * `AgentFlow` satisfies it; so can any user object.
 */
export interface IncludableWorkflow {
  name?: string;
  id?: string;
  run(input: any, options?: { variables?: Record<string, any>; includeChain?: Set<unknown> }): Promise<{
    output: any;
    results: StepResult[];
    context: WorkflowContext;
  }>;
}

/**
 * A single entry in an `AgentFlow` step list: a leaf (`Task`, function or
 * agent) or a control-flow pattern. The `Task`/`Loop`/`Repeat` references are
 * type-only imports, so this module has no runtime dependency on ./index.
 */
export type FlowStep =
  | Task
  | Loop
  | Repeat
  | If
  | Parallel
  | Route
  | Include
  | AgentLikeStep
  | ((input: any, context: WorkflowContext) => any);

// ============================================================================
// Errors
// ============================================================================

/** One failed branch of a {@link Parallel} block. */
export interface ParallelBranchError {
  /** Index of the branch in `Parallel.steps`. */
  step: number;
  error: unknown;
}

/**
 * Raised when a workflow step fails in a way that must abort the run
 * (`Parallel` with `fail_fast` / `fail_all`).
 * Python: WorkflowStepError(message, cause=None, errors=None)
 */
export class WorkflowStepError extends Error {
  readonly cause?: unknown;
  readonly errors: ParallelBranchError[];

  constructor(message: string, cause?: unknown, errors: ParallelBranchError[] = []) {
    super(message);
    this.name = 'WorkflowStepError';
    this.cause = cause;
    this.errors = errors;
  }
}

/**
 * Raised when patterns nest deeper than {@link MAX_NESTING_DEPTH}. Unlike an
 * ordinary branch failure this always aborts the run — a `Parallel` block
 * never records it as a partial result.
 */
export class NestingDepthError extends Error {
  constructor(message?: string) {
    super(message ?? `Maximum nesting depth (${MAX_NESTING_DEPTH}) exceeded. Simplify your workflow or reduce pattern nesting.`);
    this.name = 'NestingDepthError';
  }
}

// ============================================================================
// Route
// ============================================================================

/**
 * Decision-based branching. Routes to different steps based on the previous
 * step's output (word-boundary, case-insensitive key match; `default` otherwise).
 *
 * Python: Route(routes, default=None)
 */
export class Route {
  readonly routes: Record<string, FlowStep[]>;
  /** Steps taken when no key matches. Falls back to `routes.default`, then `[]`. */
  readonly default: FlowStep[];

  constructor(routes: Record<string, FlowStep[]>, defaultSteps: FlowStep[] | null = null) {
    this.routes = routes ?? {};
    // Python: `default or routes.get("default", [])` — an empty list also falls through.
    this.default = defaultSteps && defaultSteps.length > 0
      ? defaultSteps
      : (this.routes['default'] ?? []);
  }
}

// ============================================================================
// Parallel
// ============================================================================

/**
 * Execute multiple steps concurrently and combine their outputs.
 *
 * Failure strategies (Python parity):
 * - `partial_ok` (default): keep going; failed branches contribute `null`
 * - `fail_fast`: stop scheduling new branches and throw on the first failure
 * - `fail_all`: wait for every branch, then throw if any failed
 *
 * Python: Parallel(steps, max_workers=None, on_failure="partial_ok")
 */
export class Parallel {
  readonly steps: FlowStep[];
  /** Cap on concurrent branches. `null` = min(DEFAULT_MAX_PARALLEL_WORKERS, steps.length). */
  readonly maxWorkers: number | null;
  readonly onFailure: ParallelOnFailure;

  constructor(steps: FlowStep[], maxWorkers: number | null = null, onFailure: ParallelOnFailure = 'partial_ok') {
    if (!PARALLEL_ON_FAILURE_MODES.includes(onFailure)) {
      throw new Error(
        `Invalid onFailure='${onFailure}'. Must be one of ${JSON.stringify(PARALLEL_ON_FAILURE_MODES)}. ` +
        'See Parallel docstring for semantics.'
      );
    }
    this.steps = steps ?? [];
    this.maxWorkers = maxWorkers;
    this.onFailure = onFailure;
  }
}

// ============================================================================
// Include
// ============================================================================

/**
 * Include another recipe or workflow as a workflow step.
 *
 * A `recipe` string is resolved through the resolver registered with
 * {@link setRecipeResolver}; a `workflow` instance is run directly.
 *
 * Python: Include(recipe=None, workflow=None, input=None)
 */
export class Include {
  readonly recipe: string | null;
  readonly workflow: IncludableWorkflow | null;
  /** Input override; supports `{{var}}`, `{{previous_output}}` and `{{input}}`. */
  readonly input: string | null;

  constructor(
    recipe: string | null = null,
    workflow: IncludableWorkflow | null = null,
    input: string | null = null
  ) {
    if (recipe == null && workflow == null) {
      throw new Error("Either 'recipe' or 'workflow' must be provided");
    }
    this.recipe = recipe;
    this.workflow = workflow;
    this.input = input;
  }
}

/**
 * Resolves a recipe name to a runnable workflow. Return `null`/`undefined`
 * when the recipe is unknown.
 */
export type RecipeResolver = (
  recipe: string
) => IncludableWorkflow | null | undefined | Promise<IncludableWorkflow | null | undefined>;

let recipeResolver: RecipeResolver | null = null;

/**
 * Register the resolver used by {@link Include} steps that name a `recipe`.
 * Pass `null` to clear it. Without a resolver, running such a step throws.
 */
export function setRecipeResolver(resolver: RecipeResolver | null): void {
  recipeResolver = resolver;
}

/** The currently registered recipe resolver, if any. */
export function getRecipeResolver(): RecipeResolver | null {
  return recipeResolver;
}

// ============================================================================
// If
// ============================================================================

/**
 * Conditional branching. Evaluates `condition` (a string with `{{var}}`
 * placeholders) against the workflow variables and runs `thenSteps` or
 * `elseSteps`.
 *
 * Supported condition formats (see {@link evaluateWorkflowCondition}):
 * - Numeric comparison: "{{var}} > 80", "{{var}} >= 50", "{{var}} < 10"
 * - String equality:    "{{var}} == approved", "{{var}} != rejected"
 * - Contains check:     "error in {{message}}", "{{status}} contains success"
 * - Boolean:            "{{flag}}" (truthy check)
 * - Nested property:    "{{item.score}} >= 60"
 *
 * Python: If(condition, then_steps, else_steps=None)
 */
export class If {
  readonly condition: string;
  readonly thenSteps: FlowStep[];
  readonly elseSteps: FlowStep[];

  constructor(condition: string, thenSteps: FlowStep[], elseSteps: FlowStep[] | null = null) {
    this.condition = condition;
    this.thenSteps = thenSteps ?? [];
    this.elseSteps = elseSteps ?? [];
  }
}

// ============================================================================
// Convenience factories (Python: route(), parallel(), include(), when(), if_())
// ============================================================================

/** Create a routing decision point. Python: route(routes, default=None) */
export function routePattern(routes: Record<string, FlowStep[]>, defaultSteps: FlowStep[] | null = null): Route {
  return new Route(routes, defaultSteps);
}

/** Execute steps in parallel. Python: parallel(steps, max_workers=None, on_failure="partial_ok") */
export function parallelPattern(
  steps: FlowStep[],
  maxWorkers: number | null = null,
  onFailure: ParallelOnFailure = 'partial_ok'
): Parallel {
  return new Parallel(steps, maxWorkers, onFailure);
}

/** Include another recipe or workflow as a step. Python: include(recipe=None, workflow=None, input=None) */
export function include(
  recipe: string | null = null,
  workflow: IncludableWorkflow | null = null,
  input: string | null = null
): Include {
  return new Include(recipe, workflow, input);
}

/**
 * Create a conditional branching step (preferred spelling).
 * Python: when(condition, then_steps, else_steps=None)
 */
export function when(condition: string, thenSteps: FlowStep[], elseSteps: FlowStep[] | null = null): If {
  return new If(condition, thenSteps, elseSteps);
}

/** Alias for {@link when}. Python: if_(condition, then_steps, else_steps=None) */
export function if_(condition: string, thenSteps: FlowStep[], elseSteps: FlowStep[] | null = null): If {
  return new If(condition, thenSteps, elseSteps);
}

/** Alias for {@link if_} with a JS-friendly name. */
export const ifStep = if_;

// ============================================================================
// Condition evaluation (port of praisonaiagents/conditions/evaluator.py)
// ============================================================================

function getNestedValue(varPath: string, vars: Record<string, any>): any {
  let value: any = vars;
  for (const part of varPath.split('.')) {
    if (value !== null && typeof value === 'object') {
      value = value[part];
    } else {
      return undefined;
    }
  }
  return value;
}

function stringifyValue(value: any): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

/**
 * Evaluate a workflow condition string with `{{var}}` substitution.
 *
 * Python: praisonaiagents.conditions.evaluator.evaluate_condition(condition, variables, previous_output)
 *
 * Returns `false` (fail-safe) when the condition cannot be evaluated.
 */
export function evaluateWorkflowCondition(
  condition: string,
  variables: Record<string, any>,
  previousOutput: any = null
): boolean {
  if (typeof condition !== 'string') return false;
  let substituted = condition;

  // {{previous_output}} first, before general substitution.
  if (previousOutput !== null && previousOutput !== undefined) {
    substituted = substituted.split('{{previous_output}}').join(stringifyValue(previousOutput));
  }

  const placeholderPattern = /\{\{([^}]+)\}\}/g;
  const matches: string[] = [];
  let m: RegExpExecArray | null;
  while ((m = placeholderPattern.exec(substituted)) !== null) {
    matches.push(m[1]);
  }

  for (const rawName of matches) {
    if (rawName === 'previous_output') continue;
    const varName = rawName.trim();
    const value = varName.includes('.')
      ? getNestedValue(varName, variables ?? {})
      : (variables ?? {})[varName];
    substituted = substituted.split(`{{${rawName}}}`).join(stringifyValue(value));
  }

  // Only the *template* decides whether this is a comparison; a substituted
  // value that happens to look like one ("5 < 3") must not be parsed as such.
  const templateHasComparison = /(>=|<=|==|!=|>|<)/.test(condition);
  const trimmed = substituted.trim();

  try {
    if (templateHasComparison) {
      if (/^[<>=]/.test(trimmed)) {
        // Missing left operand (variable was undefined).
        return false;
      }

      const numeric = trimmed.match(/^(-?\d+(?:\.\d+)?)\s*(>=|<=|==|!=|>|<)\s*(-?\d+(?:\.\d+)?)$/);
      if (numeric) {
        const left = parseFloat(numeric[1]);
        const op = numeric[2];
        const right = parseFloat(numeric[3]);
        switch (op) {
          case '>': return left > right;
          case '>=': return left >= right;
          case '<': return left < right;
          case '<=': return left <= right;
          case '==': return left === right;
          case '!=': return left !== right;
        }
      }

      const stringEq = trimmed.match(/^(.+?)\s*(==|!=)\s*(.+)$/);
      if (stringEq) {
        const left = stringEq[1].trim();
        const right = stringEq[3].trim();
        return stringEq[2] === '==' ? left === right : left !== right;
      }
    }

    if (substituted.includes(' in ')) {
      const idx = substituted.indexOf(' in ');
      const needle = substituted.slice(0, idx).trim();
      const haystack = substituted.slice(idx + 4).trim();
      return haystack.toLowerCase().includes(needle.toLowerCase());
    }

    if (substituted.includes(' contains ')) {
      const idx = substituted.indexOf(' contains ');
      const haystack = substituted.slice(0, idx).trim();
      const needle = substituted.slice(idx + 10).trim();
      return haystack.toLowerCase().includes(needle.toLowerCase());
    }

    const lower = trimmed.toLowerCase();
    if (lower === 'true') return true;
    if (lower === 'false') return false;

    // A comparison template that matched no comparison format above: fail safe.
    if (templateHasComparison) return false;

    return trimmed.length > 0;
  } catch {
    return false;
  }
}

/**
 * Substitute `{{var}}`, `{{nested.path}}`, `{{previous_output}}` and `{{input}}`
 * in a template string. Unknown placeholders are left untouched (Python parity:
 * only keys present in `variables` are replaced).
 */
export function substituteWorkflowVariables(
  template: string,
  variables: Record<string, any>,
  previousOutput: any = null,
  input: any = null
): string {
  if (typeof template !== 'string') return template as any;
  const vars = variables ?? {};
  return template.replace(/\{\{([^}]+)\}\}/g, (placeholder, rawName: string) => {
    const name = rawName.trim();
    if (name === 'previous_output') {
      if (previousOutput !== null && previousOutput !== undefined) return stringifyValue(previousOutput);
      if (vars.previous_output !== undefined) return stringifyValue(vars.previous_output);
      return placeholder;
    }
    if (name === 'input') {
      if (input !== null && input !== undefined) return stringifyValue(input);
      if (vars.input !== undefined) return stringifyValue(vars.input);
      return placeholder;
    }
    const value = name.includes('.') ? getNestedValue(name, vars) : vars[name];
    return value === undefined ? placeholder : stringifyValue(value);
  });
}

/** True when `step` is one of the pattern descriptors defined in this module. */
export function isControlFlowPattern(step: unknown): step is If | Parallel | Route | Include {
  return step instanceof If || step instanceof Parallel || step instanceof Route || step instanceof Include;
}
