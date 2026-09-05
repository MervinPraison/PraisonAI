/**
 * The hierarchical manager loop: `AgentTeam({ process: 'hierarchical', managerLlm })`.
 *
 * Python parity: `praisonaiagents/process/process.py::Process.hierarchical`. A
 * synthetic "Manager" agent, running on `manager_llm`, is shown the status of
 * every real task and answers with `{task_id, agent_name, action}`. The team
 * executes what it names, re-prompts on an invalid pick, and stops on
 * `action: "stop"`, on max iterations, or when every task is accounted for.
 *
 * The bounds are Python's, and they exist because each one was a hang: a task
 * that ends "failed" is a valid id that never becomes "completed", so without
 * the per-task re-selection cap the manager can re-delegate it forever.
 */

import { Logger } from '../utils/logger';
import type { TeamTaskStatus } from './team-options';

/** MAX invalid selections before the loop gives up (Python: MAX_INVALID_SELECTIONS). */
const MAX_INVALID_SELECTIONS = 3;
/** MAX times one failed task may be re-delegated (Python: MAX_TASK_RESELECTIONS). */
const MAX_TASK_RESELECTIONS = 3;

/** What the manager is told about one task. */
export interface ManagerTaskView {
  task_id: number;
  name: string;
  description: string;
  status: TeamTaskStatus;
  agent: string;
}

/** The manager's answer. Python parity: ManagerInstructions. */
export interface ManagerInstructions {
  task_id: number;
  agent_name: string;
  action: string;
}

/** JSON schema pinned on the manager's reply. Python parity: output_pydantic=ManagerInstructions. */
export const MANAGER_INSTRUCTIONS_SCHEMA = {
  type: 'object',
  properties: {
    task_id: { type: 'integer' },
    agent_name: { type: 'string' },
    action: { type: 'string', enum: ['execute', 'stop'] },
  },
  required: ['task_id', 'agent_name', 'action'],
  additionalProperties: false,
} as const;

/** Everything the loop needs from the team, so this module never touches team state directly. */
export interface HierarchicalOptions {
  /** Model the Manager agent runs on. Python parity: manager_llm. */
  managerLlm: string;
  /** Iteration ceiling. Python parity: max_iter. */
  maxIter: number;
  verbose: boolean;
  /** A fresh view of every delegable task, read once per iteration. */
  snapshot: () => ManagerTaskView[];
  /** Names of the agents the manager may delegate to. */
  agentNames: string[];
  /** Point a task at a different agent, by the name the manager chose. */
  assignAgent: (taskId: number, agentName: string) => void;
  /** Run one task and leave its status updated. */
  runTask: (taskId: number) => Promise<void>;
  /**
   * Ask the manager. Defaults to a "Manager" Agent on `managerLlm`; injectable
   * so a caller (or a test) can supply the decision without a model.
   */
  ask?: (prompt: string) => Promise<string>;
}

/** Why the loop stopped. Useful to callers and to tests. */
export type HierarchicalOutcome = 'completed' | 'stopped' | 'max-iterations' | 'invalid-selections' | 'manager-error';

/** Build the Manager agent Python creates for a hierarchical run. */
async function createManagerAsk(managerLlm: string, verbose: boolean): Promise<(prompt: string) => Promise<string>> {
  const { Agent } = await import('./simple');
  const manager = new Agent({
    name: 'Manager',
    role: 'Project manager',
    goal: 'Manage the entire flow of tasks and delegate them to the right agent',
    backstory: 'Expert project manager to coordinate tasks among agents',
    instructions: 'Decide the order of tasks and which agent executes them',
    llm: managerLlm,
    verbose,
    markdown: true,
    stream: false,
  });
  return (prompt: string) => manager.chat(prompt, undefined, undefined, { outputJson: MANAGER_INSTRUCTIONS_SCHEMA as unknown as Record<string, any> });
}

/** Pull the manager's JSON out of a reply that may be fenced or padded with prose. */
export function parseManagerInstructions(reply: string): ManagerInstructions | null {
  const unfenced = reply.replace(/```(?:json)?/gi, '').trim();
  const candidates = [unfenced];
  const firstBrace = unfenced.indexOf('{');
  const lastBrace = unfenced.lastIndexOf('}');
  if (firstBrace >= 0 && lastBrace > firstBrace) candidates.push(unfenced.slice(firstBrace, lastBrace + 1));
  for (const candidate of candidates) {
    try {
      const parsed = JSON.parse(candidate);
      if (!parsed || typeof parsed !== 'object') continue;
      const taskId = Number((parsed as any).task_id ?? (parsed as any).taskId);
      const action = String((parsed as any).action ?? 'execute');
      const agentName = String((parsed as any).agent_name ?? (parsed as any).agentName ?? '');
      if (!Number.isFinite(taskId) && action.toLowerCase() !== 'stop') continue;
      return { task_id: taskId, agent_name: agentName, action };
    } catch {
      // try the next candidate
    }
  }
  return null;
}

/**
 * Run the tasks under manager supervision. Returns why the loop ended; task
 * results are left on the team through the `runTask` callback.
 */
export async function runHierarchical(options: HierarchicalOptions): Promise<HierarchicalOutcome> {
  const ask = options.ask ?? (await createManagerAsk(options.managerLlm, options.verbose));

  const excluded = new Set<number>();
  const counted = new Set<number>();
  const failedReselects = new Map<number, number>();
  const initial = options.snapshot();
  const total = initial.length;
  for (const view of initial) if (view.status === 'completed') counted.add(view.task_id);

  let invalidSelections = 0;
  let errorContext = '';
  let iteration = 0;

  while (counted.size < total) {
    iteration += 1;
    if (iteration > options.maxIter) {
      await Logger.debug(`Max iteration limit ${options.maxIter} reached, ending hierarchical process.`);
      return 'max-iterations';
    }

    const summary = options.snapshot().filter((view) => !excluded.has(view.task_id));
    const prompt = `
Here is the current status of all tasks except yours (manager_task):
${JSON.stringify(summary, null, 2)}

Provide a JSON with the structure:
{
   "task_id": <int>,
   "agent_name": "<string>",
   "action": "<execute or stop>"
}
` + errorContext;

    let instructions: ManagerInstructions | null;
    try {
      instructions = parseManagerInstructions(await ask(prompt));
    } catch (error) {
      await Logger.error(`Manager parse error: ${(error as Error)?.message ?? String(error)}`);
      return 'manager-error';
    }
    if (!instructions) {
      await Logger.error('Manager parse error: the reply was not the requested JSON.');
      return 'manager-error';
    }

    if (instructions.action.toLowerCase() === 'stop') {
      await Logger.debug('Manager decided to stop task execution');
      return 'stopped';
    }

    const selected = instructions.task_id;
    const known = summary.some((view) => view.task_id === selected);
    if (!known) {
      invalidSelections += 1;
      if (invalidSelections > MAX_INVALID_SELECTIONS) {
        await Logger.error(`Manager produced ${invalidSelections} invalid task selections; aborting.`);
        return 'invalid-selections';
      }
      const validIds = summary.map((view) => view.task_id);
      errorContext =
        `\n\n[ERROR] Your previous selection of task_id=${selected} was invalid. ` +
        `Valid task IDs are: ${JSON.stringify(validIds)}. Never select manager_task. ` +
        `Please select again from the valid options.`;
      continue;
    }

    invalidSelections = 0;
    errorContext = '';

    if (instructions.agent_name && options.agentNames.includes(instructions.agent_name)) {
      options.assignAgent(selected, instructions.agent_name);
    }

    const before = summary.find((view) => view.task_id === selected)!;
    if (before.status === 'failed') {
      const seen = (failedReselects.get(selected) ?? 0) + 1;
      failedReselects.set(selected, seen);
      if (seen > MAX_TASK_RESELECTIONS) {
        await Logger.error(`Task ${selected} failed ${seen} times; excluding from further delegation.`);
        excluded.add(selected);
        counted.add(selected);
        continue;
      }
    }

    if (before.status === 'completed') {
      await Logger.warn(`Manager re-selected already-completed task ${selected}; ignoring re-selection.`);
      counted.add(selected);
      continue;
    }

    await options.runTask(selected);
    const after = options.snapshot().find((view) => view.task_id === selected);
    if (after?.status === 'completed') counted.add(selected);
  }

  return 'completed';
}
