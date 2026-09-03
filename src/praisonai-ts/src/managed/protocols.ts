/**
 * Contract between the Agent delegation layer and managed agent backends.
 *
 * Python parity: praisonaiagents/agent/protocols.py:324-460 (`ManagedBackendProtocol`)
 */

/**
 * Provider-specific keyword options. Python passes these as `**kwargs`; the
 * TypeScript contract takes a single options bag with the same keys.
 */
export type ManagedBackendKwargs = Record<string, unknown>;

/**
 * Protocol for external managed agent backends.
 *
 * Defines the contract between the Agent's delegation layer and any managed
 * agent infrastructure provider (Anthropic Managed Agents, etc.). The core
 * SDK defines *what* (this interface); the wrapper implements *how* (the
 * provider-specific adapter).
 *
 * Implementations must handle agent/environment/session creation and
 * caching, event streaming (`agent.message`, `agent.tool_use`,
 * `session.status_idle`), custom tool calls, tool confirmation, usage
 * tracking and session reset for multi-turn isolation.
 *
 * `updateAgent`, `interrupt`, `retrieveSession` and `listSessions` are
 * optional (Python: "default no-ops for backward compat").
 * Python parity: praisonaiagents/agent/protocols.py:325-460
 */
export interface ManagedBackendProtocol {
  /**
   * Execute a prompt on managed infrastructure and return the full response.
   * Primary entry point called by the Agent's backend delegation.
   * @param prompt The user message to send to the managed agent.
   * @param kwargs Provider-specific options (e.g. timeout, metadata).
   */
  execute(prompt: string, kwargs?: ManagedBackendKwargs): Promise<string>;

  /**
   * Stream a prompt response as text chunks, as the managed agent produces
   * them. Used when the Agent is invoked with `stream: true`.
   * @param prompt The user message.
   * @param kwargs Provider-specific options.
   */
  stream(prompt: string, kwargs?: ManagedBackendKwargs): AsyncIterable<string>;

  /**
   * Discard the cached session so the next `execute()` creates a fresh one.
   * The agent and environment remain cached for reuse.
   */
  resetSession(): void;

  /**
   * Discard all cached state (agent, environment, session, client). The next
   * `execute()` call re-creates everything from scratch.
   */
  resetAll(): void;

  /**
   * Update an existing managed agent's configuration (system prompt, tools,
   * model, name, ...) without recreating it.
   * @param kwargs Fields to update.
   */
  updateAgent?(kwargs?: ManagedBackendKwargs): void;

  /**
   * Send a user interrupt to the active session (equivalent to the
   * `user.interrupt` event in the Anthropic API).
   */
  interrupt?(): void;

  /** Retrieve the current managed session's metadata and usage. */
  retrieveSession?(): Record<string, any>;

  /**
   * List sessions for the current agent.
   * @param kwargs Provider-specific filters (limit, status, ...).
   */
  listSessions?(kwargs?: ManagedBackendKwargs): Array<Record<string, any>>;
}

/**
 * Structural check mirroring Python's `@runtime_checkable`
 * `isinstance(obj, ManagedBackendProtocol)`: the four required methods must
 * be present as functions.
 */
export function isManagedBackend(value: unknown): value is ManagedBackendProtocol {
  if (value === null || (typeof value !== 'object' && typeof value !== 'function')) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.execute === 'function' &&
    typeof v.stream === 'function' &&
    typeof v.resetSession === 'function' &&
    typeof v.resetAll === 'function'
  );
}
