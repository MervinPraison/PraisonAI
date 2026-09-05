/**
 * Planning mode for AgentTeam: `AgentTeam({ planning: true })`.
 *
 * Python parity: `AgentTeam._run_with_planning`. The team's task descriptions
 * are joined into one request, a PlanningAgent turns that into a Plan, the plan
 * is approved (or the run is abandoned), a TodoList tracks it, and the plan's
 * steps -- not the original tasks -- are what actually run.
 */

import { Plan, PlanningAgent, TodoItem, TodoList } from '../planning';
import { notYetHonoured } from '../utils/parity-notice';

/** Python parity: MultiAgentPlanningConfig. */
export interface TeamPlanningSettings {
  /** Whether planning mode is on at all. */
  enabled: boolean;
  /** Model the planner runs on. Python parity: planning_llm (default gpt-4o-mini). */
  llm: string;
  /** Python parity: auto_approve_plan. */
  autoApprove: boolean;
  /** Custom approval. Python parity: ApprovalCallback(approve_fn=...). */
  approveFn?: (plan: Plan) => boolean | Promise<boolean>;
  /** Called when a plan is rejected. Python parity: ApprovalCallback(on_reject=...). */
  onReject?: (plan: Plan) => void;
}

/** The value `AgentTeam({ planning })` accepts. */
export type TeamPlanningInput =
  | boolean
  | string
  | Partial<Omit<TeamPlanningSettings, 'enabled'>>
  | [string, Partial<Omit<TeamPlanningSettings, 'enabled'>>];

const DEFAULT_PLANNING_LLM = 'gpt-4o-mini';

/** Resolve `planning` into planner settings. A string is the planner's model. */
export function resolveTeamPlanning(value: unknown): TeamPlanningSettings {
  const off: TeamPlanningSettings = { enabled: false, llm: DEFAULT_PLANNING_LLM, autoApprove: false };
  if (value === undefined || value === null || value === false) return off;
  if (value === true) return { ...off, enabled: true };
  if (typeof value === 'string') return { ...off, enabled: true, llm: value };

  // Collected as the value is read so the notice has one call site, at the end.
  let unusable: string | undefined;
  let settings: TeamPlanningSettings = { ...off, enabled: true };

  const merge = (source: Record<string, unknown>): void => {
    const llm = source.llm ?? source.model;
    if (typeof llm === 'string') settings.llm = llm;
    const autoApprove = source.autoApprove ?? source.auto_approve;
    if (typeof autoApprove === 'boolean') settings.autoApprove = autoApprove;
    const approveFn = source.approveFn ?? source.approve_fn;
    if (typeof approveFn === 'function') settings.approveFn = approveFn as TeamPlanningSettings['approveFn'];
    const onReject = source.onReject ?? source.on_reject;
    if (typeof onReject === 'function') settings.onReject = onReject as TeamPlanningSettings['onReject'];
    // The planner Python builds also takes tools= and reasoning=; the
    // TypeScript PlanningAgent has neither, so say so rather than drop them.
    if (source.tools !== undefined || source.reasoning !== undefined) {
      unusable = 'planning.tools and planning.reasoning are not available on the TypeScript PlanningAgent; the rest of the planning config is applied.';
    }
  };

  if (Array.isArray(value)) {
    const [preset, overrides] = value as [unknown, unknown];
    if (typeof preset === 'string') settings.llm = preset;
    if (overrides && typeof overrides === 'object') merge(overrides as Record<string, unknown>);
  } else if (typeof value === 'object') {
    merge(value as Record<string, unknown>);
  } else {
    settings = off;
    unusable = `A ${typeof value} is not a planning config; pass true, a planner model name, or an object with llm / autoApprove / approveFn.`;
  }

  if (unusable) notYetHonoured('AgentTeam', 'planning', unusable);
  return settings;
}

/**
 * Ask the planner for a plan covering `request`. Returns null when the planner
 * produced no steps, which Python treats as "planning failed, fall back to
 * normal execution".
 */
export async function createTeamPlan(settings: TeamPlanningSettings, request: string, verbose: boolean): Promise<Plan | null> {
  const planner = new PlanningAgent({ llm: settings.llm, verbose });
  const plan = await planner.createPlan(request);
  return plan.steps.length > 0 ? plan : null;
}

/**
 * Decide whether the plan may run.
 *
 * Python parity: `ApprovalCallback.__call__` -- auto_approve wins, then a
 * custom approve_fn, then the interactivity rule: a non-interactive process
 * (CI, a script, a test) approves, an interactive one requires an explicit yes
 * and therefore rejects a plan nobody approved.
 */
export async function approveTeamPlan(settings: TeamPlanningSettings, plan: Plan): Promise<boolean> {
  if (settings.autoApprove) return true;
  if (settings.approveFn) {
    const approved = await settings.approveFn(plan);
    if (!approved && settings.onReject) settings.onReject(plan);
    return approved;
  }
  const interactive = typeof process !== 'undefined' && !!(process.stdin as { isTTY?: boolean } | undefined)?.isTTY;
  if (!interactive) return true;
  if (settings.onReject) settings.onReject(plan);
  return false;
}

/** The todo list Python builds from a plan so progress is trackable. */
export function todoListFromPlan(plan: Plan): TodoList {
  const todos = new TodoList(plan.name);
  for (const step of plan.steps) {
    todos.add(new TodoItem({ content: step.description, metadata: { stepId: step.id } }));
  }
  return todos;
}
