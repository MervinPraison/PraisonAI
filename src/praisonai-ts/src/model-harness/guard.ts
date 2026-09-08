/**
 * A global switch that blocks real provider calls, for test suites.
 *
 * Python parity: `praisonaiagents.model_harness.guard`
 * (`allow_model_requests`, `no_model_requests`, `ModelRequestBlocked`).
 *
 * ```ts
 * // test setup
 * allowModelRequests(false);   // nothing in this suite may reach a provider
 * ```
 *
 * A blocked call throws {@link ModelRequestBlocked} naming the offending call
 * site, so an accidental live call in a test is loud rather than slow and
 * billed.
 */

/** Thrown when a real provider call is attempted while requests are blocked. */
export class ModelRequestBlocked extends Error {
  readonly model?: string;
  readonly callSite?: string;

  constructor(model?: string, callSite?: string) {
    const where = callSite ? ` Called from ${callSite}.` : '';
    super(
      `Blocked a real request to model '${model ?? 'unknown'}': model requests are ` +
        `turned off (allowModelRequests(false)).${where} ` +
        `Script the reply instead -- new Agent({ llm: new ScriptedModel([...]) }) -- ` +
        `or call allowModelRequests(true) if this call really should reach the network.`
    );
    this.name = 'ModelRequestBlocked';
    this.model = model;
    this.callSite = callSite;
  }
}

let allowed = true;
/**
 * Count of open `noModelRequests()` scopes. Deliberately a counter rather than
 * a saved-and-restored boolean: with a shared snapshot, an inner scope exiting
 * first restores `true` while an outer scope is still open, letting a real call
 * through -- exactly the leak the guard exists to prevent. Requests stay
 * blocked until every scope has closed.
 */
let blockDepth = 0;

/** Turn real provider calls on or off for the whole process. */
export function allowModelRequests(value: boolean = true): void {
  allowed = value;
}

/** Whether a real provider call is currently permitted. */
export function modelRequestsAllowed(): boolean {
  return allowed && blockDepth === 0;
}

/**
 * Block real provider calls for the duration of `fn`. Nests and composes with
 * {@link allowModelRequests}; requests stay blocked until every open scope has
 * exited, including across interleaved async scopes.
 */
export async function noModelRequests<T>(fn: () => T | Promise<T>): Promise<T> {
  blockDepth += 1;
  try {
    return await fn();
  } finally {
    blockDepth -= 1;
  }
}

/** Best-effort caller location, skipping this package's own frames. */
function describeCallSite(): string | undefined {
  const stack = new Error().stack;
  if (!stack) return undefined;
  for (const line of stack.split('\n').slice(1)) {
    if (line.includes('/model-harness/') || line.includes('node:internal')) continue;
    const trimmed = line.trim();
    if (trimmed.startsWith('at ')) return trimmed.slice(3);
  }
  return undefined;
}

/** Throw if requests are blocked. Called at the provider boundary. */
export function checkModelRequest(model?: string): void {
  if (modelRequestsAllowed()) return;
  throw new ModelRequestBlocked(model, describeCallSite());
}
