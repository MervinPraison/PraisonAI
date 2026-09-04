/**
 * The parts of a handoff that decide *what the target sees* and *whether the
 * handoff is allowed to happen at all*: the context-policy filter, the
 * invocation-scoped history seeding, and the per-chain state that cycle and
 * depth checks read.
 *
 * This lives beside `handoff.ts` rather than inside it so the handoff class
 * gains calls instead of blocks. Nothing here imports `handoff.ts`: the policy
 * is taken as a plain string and the errors are raised by the caller, which
 * keeps the two modules acyclic under CommonJS.
 *
 * Python parity with praisonaiagents/agent/handoff.py:
 * - `Handoff._prepare_context`   -> `selectHandoffMessages`
 * - `Handoff._seed_target_history` -> `withSeededHistory`
 * - `_handoff_chain_var` / `_get_handoff_chain` / `_push_handoff`
 *                                 -> `currentHandoffChain` / `runWithHandoffChain`
 */

import { estimateMessagesTokens } from '../context/policy';

// ============================================================================
// Context policy
// ============================================================================

/**
 * How many non-system messages the `summary` policy keeps. Python hard-codes
 * `other_msgs[-3:]` in `_prepare_context`; `max_context_messages` applies to
 * `last_n` only, so the two are deliberately not the same knob.
 */
export const SUMMARY_MESSAGE_COUNT = 3;

/** The settings `selectHandoffMessages` reads off a resolved handoff config. */
export interface HandoffContextSelection {
  /** One of `full` | `summary` | `none` | `last_n` (Python: `ContextPolicy`). */
  contextPolicy: string;
  /** Messages kept by the `last_n` policy. */
  maxContextMessages: number;
  /** Token ceiling for the selected context; `<= 0` disables the ceiling. */
  maxContextTokens: number;
  /** Keep `system` messages regardless of the slice. */
  preserveSystem: boolean;
}

/** Python: `isinstance(m, dict) and m.get('role') == 'system'`. */
function isSystemMessage(message: unknown): boolean {
  return (
    !!message &&
    typeof message === 'object' &&
    !Array.isArray(message) &&
    (message as Record<string, unknown>).role === 'system'
  );
}

/**
 * `arr[-n:]` as Python evaluates it for the counts `_prepare_context` uses.
 * `n <= 0` keeps everything: Python's `arr[-0:]` is `arr[0:]`, the whole list,
 * and a handoff configured with `maxContextMessages: 0` therefore does *not*
 * mean "no messages" — that is what `contextPolicy: 'none'` is for.
 */
function lastN<T>(items: readonly T[], n: number): T[] {
  if (!(n > 0)) return [...items];
  return items.slice(Math.max(0, items.length - n));
}

/**
 * Trim a message list to `maxTokens` estimated tokens by dropping the oldest
 * messages first. With `preserveSystem` the `system` messages are never
 * dropped, so a system prompt larger than the budget is kept in full rather
 * than leaving the target with no instructions at all.
 *
 * The estimate is the SDK's own heuristic (`estimateMessagesTokens`), the same
 * one the context-compaction policy uses, so a handoff and a compaction agree
 * about how big a conversation is.
 *
 * Note on parity: Python declares `HandoffConfig.max_context_tokens`,
 * serialises it in `to_dict()` and never reads it — no code path in
 * praisonaiagents consults the field. TypeScript honours the documented
 * meaning ("Maximum tokens to include in context") instead of copying the
 * omission, so this is the one handoff setting where TypeScript does more
 * than Python rather than the same.
 */
export function fitToTokenBudget<T>(messages: readonly T[], maxTokens: number, preserveSystem: boolean): T[] {
  const kept = [...messages];
  if (!(maxTokens > 0) || kept.length === 0) return kept;

  while (kept.length > 0 && estimateMessagesTokens(kept as Record<string, any>[]) > maxTokens) {
    const index = kept.findIndex(message => !(preserveSystem && isSystemMessage(message)));
    if (index === -1) break; // only protected messages remain
    kept.splice(index, 1);
  }
  return kept;
}

/**
 * The messages a handoff target should see, from the source conversation and
 * the configured context policy. Python parity with the policy block of
 * `Handoff._prepare_context`:
 *
 * - `none`    -> nothing
 * - `last_n`  -> the last `maxContextMessages`
 * - `summary` -> the last {@link SUMMARY_MESSAGE_COUNT}
 * - `full`    -> everything
 *
 * With `preserveSystem` (the default) the slice is taken over the non-system
 * messages and every `system` message is prepended, so trimming a long
 * conversation never silently drops the target's instructions. Without it the
 * slice is taken over the raw list, exactly as Python does.
 *
 * `maxContextTokens` is applied last, to whatever the policy selected.
 */
export function selectHandoffMessages(
  messages: readonly any[] | null | undefined,
  selection: HandoffContextSelection
): any[] {
  if (!Array.isArray(messages) || messages.length === 0) return [];

  const { contextPolicy, preserveSystem } = selection;
  let selected: any[];

  if (contextPolicy === 'none') {
    return [];
  } else if (contextPolicy === 'last_n' || contextPolicy === 'summary') {
    const n = contextPolicy === 'last_n' ? selection.maxContextMessages : SUMMARY_MESSAGE_COUNT;
    if (preserveSystem) {
      const system = messages.filter(isSystemMessage);
      const other = messages.filter(message => !isSystemMessage(message));
      selected = [...system, ...lastN(other, n)];
    } else {
      selected = lastN(messages, n);
    }
  } else {
    // ContextPolicy.FULL (and any unknown value, as in Python's else branch).
    selected = [...messages];
  }

  return fitToTokenBudget(selected, selection.maxContextTokens, preserveSystem);
}

// ============================================================================
// Invocation-scoped history seeding
// ============================================================================

/** Structural view of the history APIs a handoff target may expose. */
type SeedableAgent = {
  chatHistory?: unknown;
  chat_history?: unknown;
  getHistory?: () => unknown;
  setHistory?: (messages: readonly any[]) => void;
};

function sameHead(existing: readonly any[], prior: readonly any[]): boolean {
  if (existing.length < prior.length) return false;
  try {
    return JSON.stringify(existing.slice(0, prior.length)) === JSON.stringify(prior);
  } catch {
    return false; // circular or otherwise unserialisable: seed rather than guess
  }
}

/**
 * Run `fn` with `prior` prepended to the target agent's conversation, then put
 * the agent's history back exactly as it was — on failure too. Python parity
 * with the `_seed_target_history` context manager.
 *
 * Without this the target only ever sees the handoff prompt string and the
 * configured context policy has nothing to act on. The seeding is
 * invocation-scoped so handoff context cannot leak into the next handoff or
 * into an ordinary chat that reuses the same agent.
 *
 * Two history shapes are supported: a plain `chatHistory`/`chat_history` array
 * (Python's shape, and what a stub target uses) and the simple `Agent`'s
 * `getHistory()`/`setHistory()` pair. `setHistory` validates what it is given
 * and throws on a history it cannot represent (a second `system` message, an
 * orphaned tool result); such a seed is skipped rather than failing the
 * handoff. An agent with neither shape — an `EnhancedAgent`, whose messages
 * live in a `Session` with no restore API — runs unseeded.
 */
export async function withSeededHistory<T>(
  agent: unknown,
  prior: readonly any[],
  fn: () => Promise<T>
): Promise<T> {
  if (!agent || typeof agent !== 'object' || prior.length === 0) return fn();
  const target = agent as SeedableAgent & Record<string, any>;

  const arrayKey = Array.isArray(target.chatHistory)
    ? 'chatHistory'
    : Array.isArray(target.chat_history)
      ? 'chat_history'
      : null;

  if (arrayKey) {
    const original = target[arrayKey] as any[];
    if (sameHead(original, prior)) return fn();
    target[arrayKey] = [...prior, ...original];
    try {
      return await fn();
    } finally {
      target[arrayKey] = original;
    }
  }

  if (typeof target.getHistory === 'function' && typeof target.setHistory === 'function') {
    let original: any[];
    try {
      const current = target.getHistory();
      original = Array.isArray(current) ? current : [];
      if (sameHead(original, prior)) return fn();
      target.setHistory([...prior, ...original]);
    } catch {
      return fn(); // a history the agent refuses to hold is not worth failing over
    }
    try {
      return await fn();
    } finally {
      try {
        target.setHistory(original);
      } catch {
        /* restoring a history the agent just held should not mask the result */
      }
    }
  }

  return fn();
}

// ============================================================================
// Handoff chain (cycle detection and depth limiting)
// ============================================================================

/**
 * The chain of agents that have handed off to reach the current point, as
 * Python keeps it in a `contextvars.ContextVar`.
 *
 * `AsyncLocalStorage` is the equivalent isolation in JavaScript: without it
 * one module-level array is shared by every concurrent handoff, so sibling
 * fan-outs would see each other's pushes and invent cycles that do not exist.
 *
 * It is reached through `process.getBuiltinModule` (Node 20.16+/22.3+) rather
 * than `require('async_hooks')` or a static import, and that is deliberate:
 * this module is on the `praisonai/mobile` graph, where a bare `require(...)`
 * earns the ESM shim's `createRequire` banner — a top-level await esbuild
 * refuses to lower for the WebView floor — and a static import of a Node
 * builtin would be left unresolved in a React Native bundle.
 *
 * A runtime without it (Node 18, a browser bundle) falls back to one
 * module-level chain: nesting is still tracked correctly, only isolation
 * between *concurrently running* handoffs is lost. The scope counter below
 * bounds the damage — a chain a sibling restored over cannot outlive the last
 * handoff — and `parallelHandoffs` passes each sibling an explicit
 * `handoffChain` so the fan-out case does not depend on the ambient value.
 */
type ChainStore = {
  getStore(): readonly string[] | undefined;
  run<T>(chain: readonly string[], fn: () => T): T;
};

let asyncStore: ChainStore | null | undefined;
let fallbackChain: readonly string[] = [];
let activeScopes = 0;

function store(): ChainStore | null {
  if (asyncStore !== undefined) return asyncStore;
  asyncStore = null;
  try {
    const proc = (globalThis as { process?: { getBuiltinModule?: (name: string) => any } }).process;
    const getBuiltinModule = proc?.getBuiltinModule;
    if (typeof getBuiltinModule === 'function') {
      const AsyncLocalStorage = getBuiltinModule.call(proc, 'async_hooks')?.AsyncLocalStorage;
      if (typeof AsyncLocalStorage === 'function') {
        asyncStore = new AsyncLocalStorage() as ChainStore;
      }
    }
  } catch {
    asyncStore = null; // no async_hooks here: use the fallback
  }
  return asyncStore;
}

/** The chain in force for the current execution. Python: `_get_handoff_chain()`. */
export function currentHandoffChain(): readonly string[] {
  const als = store();
  if (als) return als.getStore() ?? [];
  return fallbackChain;
}

/** How deep the current execution already is. Python: `_get_handoff_depth()`. */
export function currentHandoffDepth(): number {
  return currentHandoffChain().length;
}

/**
 * Run `fn` with `chain` as the current handoff chain, restoring the previous
 * one afterwards. Python's `_push_handoff`/`_pop_handoff` pair, expressed as a
 * scope so no `finally` can be forgotten, and copy-on-write for the same
 * reason Python is: a push inside a nested handoff must not leak back out.
 */
export function runWithHandoffChain<T>(chain: readonly string[], fn: () => Promise<T>): Promise<T> {
  const als = store();
  if (als) return als.run(chain, fn);

  const previous = fallbackChain;
  fallbackChain = chain;
  activeScopes++;
  const close = () => {
    activeScopes--;
    // One shared chain cannot survive interleaving intact: a sibling may have
    // restored over this scope's value already. Emptying it once the last
    // scope closes at least stops a stale chain from being read as real depth
    // by the next, unrelated handoff.
    fallbackChain = activeScopes === 0 ? [] : previous;
  };

  try {
    return fn().finally(close);
  } catch (error) {
    close();
    throw error;
  }
}

/** Test helper: forget any chain left behind by the fallback path. */
export function resetHandoffChain(): void {
  fallbackChain = [];
  activeScopes = 0;
}
