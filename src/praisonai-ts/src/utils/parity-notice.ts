/**
 * Parity notices for options accepted from the Python SDK surface.
 *
 * The signature parity gate (src/praisonai/praisonai/_dev/parity/signatures)
 * requires every Python constructor/method parameter to exist on the
 * TypeScript side. Some of those parameters are accepted and typed before the
 * behaviour behind them is ported. Such an option must never be silently
 * ignored: a setting that is accepted and does nothing is a defect that no
 * test catches. This helper makes the gap audible once per process and
 * queryable from code.
 *
 * Usage inside a constructor:
 *
 *   if (config.sandbox !== undefined) notYetHonoured('Agent', 'sandbox');
 *
 * Silence with PRAISONAI_PARITY_SILENT=1 (for example in tests), and read
 * back what was accepted-but-unhonoured with `unhonouredOptions()`.
 */

/**
 * Every option this SDK accepts for Python parity but does not yet act on.
 *
 * This is the ledger, not a convenience: the name and signature gates both
 * measure whether a parameter EXISTS, so an option that is accepted and does
 * nothing passes them both. Nothing counted these until they were counted by
 * hand and there were 76. Declaring them in one place makes the number
 * generated rather than remembered -- `praisonai._dev.parity.behaviour` reads
 * this file, writes BEHAVIOUR_PARITY.md, and fails the build if the total
 * grows.
 *
 * To close one: implement the behaviour, delete its entry here, add a test
 * that proves the option changes what the code does, and regenerate.
 * The list is the work queue, and it is meant to shrink to nothing.
 */
export const UNHONOURED_OPTIONS: Readonly<Record<string, readonly string[]>> = {
  'Agent.__init__': [
    'auth', 'toolsets', 'reflection', 'autonomy', 'templates', 'selfImprove', 'toolConfig',
    'learn', 'backend', 'runOn', 'toolsRunOn', 'runtime', 'toolSearch', 'messageSteering', 'sandbox',
  ],
  'Agent.chat': [
    'reasoningSteps', 'taskName', 'taskDescription', 'taskId', 'config', 'attachments',
  ],
  'AgentTeam.__init__': [
    'managerLlm', 'memory', 'planning', 'context', 'execution', 'hooks', 'autonomy', 'knowledge',
    'guardrails', 'web', 'reflection', 'caching', 'learn', 'toolsRunOn', 'runOn',
  ],
  'Task.__init__': [
    'asyncExecution', 'config', 'outputPydantic', 'images', 'nextTasks', 'condition', 'isStart',
    'loopState', 'memory', 'inputFile', 'rerun', 'retainFullContext', 'agentConfig', 'skipOnFailure',
    'retryDelay', 'handler', 'loopOver', 'loopVar', 'execution', 'routing', 'outputConfig', 'when',
    'thenTask', 'elseTask', 'autonomy', 'knowledge', 'web', 'reflection', 'planning', 'hooks',
    'caching', 'failOnMemoryError',
  ],
  'Handoff': [
    'contextPolicy', 'maxContextTokens', 'maxContextMessages', 'preserveSystem',
    'timeoutSeconds', 'maxConcurrent', 'detectCycles', 'maxDepth',
  ],
} as const;

/** The options still unhonoured for one surface, or [] if the surface is clean. */
export function unhonouredFor(surface: string): readonly string[] {
  return UNHONOURED_OPTIONS[surface] ?? [];
}

/** How many options are accepted but not yet acted on, across every surface. */
export function unhonouredCount(): number {
  return Object.values(UNHONOURED_OPTIONS).reduce((n, list) => n + list.length, 0);
}

const seen = new Set<string>();

function silenced(): boolean {
  const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env;
  return env?.PRAISONAI_PARITY_SILENT === '1' || env?.PRAISONAI_PARITY_SILENT === 'true';
}

/**
 * Record that `option` on `surface` was supplied by the caller but is not yet
 * honoured by the TypeScript implementation. Warns once per (surface, option).
 */
export function notYetHonoured(surface: string, option: string, detail?: string): void {
  const key = `${surface}.${option}`;
  if (seen.has(key)) return;
  seen.add(key);
  if (silenced()) return;
  const extra = detail ? ` ${detail}` : '';
  console.warn(
    `[praisonai] ${surface}: option "${option}" is accepted for parity with the Python SDK but is not yet honoured in TypeScript.${extra}`
  );
}

/** Every (surface, option) pair reported so far, as "Surface.option" keys. */
export function unhonouredOptions(): string[] {
  return Array.from(seen).sort();
}

/** Test helper: forget previously reported keys so warnings fire again. */
export function resetParityNotices(): void {
  seen.clear();
}
