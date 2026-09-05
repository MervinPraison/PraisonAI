/**
 * "Where does this run?" — `backend=`, `runOn=` and `toolsRunOn=`
 * (Python parity: `agent/placement.py`, `agent/tools_placement.py`,
 * `agent/execution_mixin.py::_delegate_to_backend`).
 *
 * Two different questions, deliberately kept apart:
 *
 * - `runOn` / `backend` place the **whole agent** — model calls, loop and
 *   tools — on a managed runtime. `runOn: "anthropic"` is shorthand for
 *   `backend: <hosted agent for anthropic>`.
 * - `toolsRunOn` places **only the tools**. Thinking stays here; the shell,
 *   the file writes and the code execution move.
 *
 * Because the two answer sets are disjoint, a wrong pairing is a typo worth
 * catching rather than a preference worth honouring: `runOn: "docker"` cannot
 * mean anything, and gets an error naming the parameter the caller wanted.
 * That validation is ported verbatim from `resolve_placement`.
 *
 * Neither a hosted runtime nor a remote sandbox ships in this package (they
 * are provider integrations), so both are resolved through registries a host
 * fills in — {@link registerManagedRuntime} and {@link registerToolPlace}.
 * An unregistered name fails loudly at construction with the same
 * "install the integration" shape Python uses, instead of running the agent
 * on the wrong machine.
 */

/** A managed runtime that can host an entire agent loop (Python `ManagedBackendProtocol`). */
export interface ManagedBackendLike {
  /** Run one prompt on managed infrastructure and return the whole response. */
  execute(prompt: unknown, options?: Record<string, unknown>): Promise<unknown> | unknown;
  /** Optional streaming form, used when the turn is streaming. */
  stream?(prompt: unknown, options?: Record<string, unknown>): AsyncIterable<string>;
  /** Optional id of the managed session, linked into the agent's session store. */
  managedSessionId?: string;
}

/**
 * A place that can run a tool call (Python's `ToolPlace` / `SharedCompute`
 * adapters). `runTool` receives the tool name, its parsed arguments and the
 * local implementation, and returns the result — a local place just calls it.
 */
export interface ToolPlaceLike {
  readonly placeName: string;
  runTool(
    toolName: string,
    args: Record<string, unknown>,
    localImplementation: () => Promise<unknown>
  ): Promise<unknown>;
}

/** The `local` place: the tool runs in this process, unchanged (Python's default). */
export const LOCAL_TOOL_PLACE: ToolPlaceLike = Object.freeze({
  placeName: 'local',
  async runTool(
    _toolName: string,
    _args: Record<string, unknown>,
    localImplementation: () => Promise<unknown>
  ): Promise<unknown> {
    return localImplementation();
  },
});

const managedRuntimes = new Map<string, () => ManagedBackendLike>();
const toolPlaces = new Map<string, () => ToolPlaceLike>([['local', () => LOCAL_TOOL_PLACE]]);

/**
 * Register a runtime that `runOn: "<name>"` may name (Python's backend
 * entry-point registry, which the wrapper package fills in).
 */
export function registerManagedRuntime(name: string, factory: () => ManagedBackendLike): void {
  managedRuntimes.set(name.toLowerCase(), factory);
}

/** Forget a managed runtime registration. Returns whether one was removed. */
export function unregisterManagedRuntime(name: string): boolean {
  return managedRuntimes.delete(name.toLowerCase());
}

/** Every runtime name `runOn=` accepts right now. */
export function managedRuntimeNames(): string[] {
  return [...managedRuntimes.keys()].sort();
}

/** Register a place that `toolsRunOn: "<name>"` may name (Python's compute bridge). */
export function registerToolPlace(name: string, factory: () => ToolPlaceLike): void {
  toolPlaces.set(name.toLowerCase(), factory);
}

/** Forget a tool place registration. `local` cannot be removed. */
export function unregisterToolPlace(name: string): boolean {
  if (name.toLowerCase() === 'local') return false;
  return toolPlaces.delete(name.toLowerCase());
}

/** Every place name `toolsRunOn=` accepts right now. */
export function toolPlaceNames(): string[] {
  return [...toolPlaces.keys()].sort();
}

/** Anything with an `execute()` is a backend (Python: `hasattr(backend, 'execute')`). */
export function isManagedBackendLike(value: unknown): value is ManagedBackendLike {
  if (value === null || (typeof value !== 'object' && typeof value !== 'function')) return false;
  return typeof (value as Record<string, unknown>).execute === 'function';
}

function isToolPlaceLike(value: unknown): value is ToolPlaceLike {
  if (value === null || typeof value !== 'object') return false;
  const v = value as Record<string, unknown>;
  return typeof v.runTool === 'function';
}

/** Python `_name_of`: only bare strings are routed by name; objects carry their own config. */
function nameOf(value: unknown): string | null {
  return typeof value === 'string' ? value.toLowerCase() : null;
}

function quoteList(names: readonly string[]): string {
  return names.length === 0 ? '(none registered)' : names.map((n) => `'${n}'`).join(', ');
}

/** The resolved answer to "where does this run?" (Python `Placement`). */
export interface Placement {
  /** The managed backend running the whole agent, or `undefined`. */
  backend?: ManagedBackendLike;
  /** The place this agent's tools run, or `undefined` for in-process. */
  toolPlace?: ToolPlaceLike;
}

export interface ResolvePlacementInput {
  /** Class name, used only so errors read naturally (Python's `owner`). */
  owner?: string;
  runOn?: unknown;
  toolsRunOn?: unknown;
  backend?: unknown;
}

/**
 * Validate the three placement options against each other and resolve them
 * (Python `resolve_placement` plus `Agent._hosted_backend_for`).
 *
 * Throws when two options name two different places for the same thing, or
 * when a place is asked to do a job it cannot do.
 */
export function resolvePlacement(input: ResolvePlacementInput): Placement {
  const owner = input.owner ?? 'Agent';
  const { runOn, toolsRunOn, backend } = input;
  const managed = managedRuntimeNames();
  const places = toolPlaceNames();

  // ── a place that cannot do the job asked of it ──────────────────────────
  const runOnName = nameOf(runOn);
  if (runOn !== undefined && runOn !== null && runOnName !== null && !managedRuntimes.has(runOnName)) {
    if (toolPlaces.has(runOnName)) {
      throw new TypeError(
        `${owner}(runOn: '${runOnName}') is not valid: runOn places the whole agent -- model calls, ` +
        `loop and tools -- on a managed runtime, and '${runOnName}' runs commands but cannot host an agent loop.\n` +
        `  To run only the tools there:  ${owner}({ toolsRunOn: '${runOnName}' })\n` +
        `  Runtimes that host a whole agent: ${quoteList(managed)}`
      );
    }
    throw new TypeError(
      `${owner}(runOn: '${runOnName}') is not a known managed runtime.\n` +
      `  Runtimes that host a whole agent: ${quoteList(managed)}\n` +
      `  Places that can run tools:        ${quoteList(places)} (pass those as toolsRunOn)\n` +
      `  A managed runtime is a provider integration: register one with registerManagedRuntime('${runOnName}', ...).`
    );
  }

  const toolsName = nameOf(toolsRunOn);
  if (toolsName !== null && managedRuntimes.has(toolsName) && !toolPlaces.has(toolsName)) {
    throw new TypeError(
      `${owner}(toolsRunOn: '${toolsName}') is not valid: '${toolsName}' hosts an entire agent, not individual tools.\n` +
      `  Did you mean:  ${owner}({ runOn: '${toolsName}' })`
    );
  }

  // A typo here used to survive construction and only surface on the first
  // model turn -- after the prompt was built and, for a real run, after the
  // API spend. Validate at the call site instead.
  if (toolsName !== null && !toolPlaces.has(toolsName)) {
    throw new TypeError(
      `${owner}(toolsRunOn: '${toolsName}') is not a known place.\n` +
      `  Places that can run tools: ${quoteList(places)}\n` +
      `  Runtimes that host a whole agent: ${quoteList(managed)} (pass those as runOn)\n` +
      `  A remote place is a provider integration: register one with registerToolPlace('${toolsName}', ...).`
    );
  }

  // ── two names for the same thing ────────────────────────────────────────
  if (runOn !== undefined && runOn !== null && backend !== undefined && backend !== null) {
    throw new TypeError(
      `${owner}(runOn, backend) sets the agent's runtime twice. runOn is the short form of a hosted ` +
      `backend for that provider; pass one or the other.\n` +
      `  Use backend only when you need to configure the runtime (model, system prompt, tools).`
    );
  }

  if (runOn !== undefined && runOn !== null && toolsRunOn !== undefined && toolsRunOn !== null) {
    throw new TypeError(
      `${owner}(runOn, toolsRunOn) points the tools at two machines. runOn already runs everything ` +
      `-- including tools -- on the managed runtime.\n` +
      `  Whole agent remote:  ${owner}({ runOn })\n` +
      `  Only tools remote:   ${owner}({ toolsRunOn })`
    );
  }

  if (backend !== undefined && backend !== null && toolsRunOn !== undefined && toolsRunOn !== null) {
    throw new TypeError(
      `${owner}(backend, toolsRunOn) points the tools at two machines: backend runs the whole agent ` +
      `(tools included) on its managed runtime, so the tools cannot also run elsewhere.\n` +
      `  Drop toolsRunOn to keep the hosted runtime, or drop backend to keep local thinking with remote tools.`
    );
  }

  // ── resolve ─────────────────────────────────────────────────────────────
  const placement: Placement = {};

  if (backend !== undefined && backend !== null) {
    if (!isManagedBackendLike(backend)) {
      throw new TypeError(
        `${owner}(backend) does not support execute(): a managed backend must expose ` +
        `execute(prompt, options) returning the response.`
      );
    }
    placement.backend = backend;
  } else if (runOn !== undefined && runOn !== null) {
    if (isManagedBackendLike(runOn)) {
      placement.backend = runOn;
    } else {
      placement.backend = managedRuntimes.get(runOnName as string)!();
    }
  }

  if (toolsRunOn !== undefined && toolsRunOn !== null) {
    if (isToolPlaceLike(toolsRunOn)) {
      placement.toolPlace = toolsRunOn;
    } else if (toolsName !== null) {
      placement.toolPlace = toolPlaces.get(toolsName)!();
    } else {
      throw new TypeError(
        `${owner}(toolsRunOn) must be a place name or an object with runTool(name, args, run).`
      );
    }
  }

  return placement;
}

/** Everything Python forwards to a managed backend's `execute()`. */
export interface BackendDelegationOptions {
  temperature?: number;
  tools?: unknown;
  outputJson?: unknown;
  outputPydantic?: unknown;
  reasoningSteps?: boolean;
  stream?: boolean;
  taskName?: string;
  taskDescription?: string;
  taskId?: string;
  /** Python's `config` keyword: forwarded verbatim, never interpreted here. */
  config?: Record<string, unknown>;
  forceRetrieval?: boolean;
  skipRetrieval?: boolean;
  attachments?: readonly string[];
  toolChoice?: string;
}

/**
 * Hand the whole turn to the managed backend (Python
 * `_delegate_to_backend`). Streams through `backend.stream()` when the turn is
 * streaming and the backend offers one, so tokens still reach `onToken`.
 */
export async function delegateToBackend(
  backend: ManagedBackendLike,
  prompt: string,
  options: BackendDelegationOptions,
  onToken?: (token: string) => void
): Promise<string> {
  if (options.stream && typeof backend.stream === 'function') {
    let accumulated = '';
    for await (const chunk of backend.stream(prompt, { ...options })) {
      const text = typeof chunk === 'string' ? chunk : String(chunk);
      if (text.length === 0) continue;
      accumulated += text;
      onToken?.(text);
    }
    return accumulated;
  }
  const result = await backend.execute(prompt, { ...options });
  return result === null || result === undefined ? '' : String(result);
}
