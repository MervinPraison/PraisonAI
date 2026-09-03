/**
 * Compaction route and strategy values.
 *
 * These live apart from `policy.ts` on purpose: `ContextManager` needs the
 * strategy names and nothing else, and importing them from `policy.ts` would
 * put that whole module (with its model tables and token estimators) on the
 * agent's graph -- 24kB that pushed praisonai/mobile past its lazy bundle
 * budget. `policy.ts` re-exports both, so every existing import still works.
 *
 * Python parity: `CompactionRoute` and `CompactionStrategy` in
 * praisonaiagents/context/protocols.py.
 */

/**
 * Routes for context handling decisions.
 * Python parity with `CompactionRoute(str, Enum)` in context/protocols.py.
 */
export const CompactionRoute = {
  /** Context fits, proceed normally. */
  FITS: 'fits',
  /** Need compaction before LLM call. */
  COMPACT_NEEDED: 'compact_needed',
  /** Truncate tool results first. */
  TRUNCATE_TOOLS: 'truncate_tools',
  /** Both compaction and truncation needed. */
  COMPACT_THEN_TRUNCATE: 'compact_then_truncate',
} as const;

export type CompactionRouteType = typeof CompactionRoute[keyof typeof CompactionRoute];

/**
 * Strategy for context compaction.
 * Python parity with `CompactionStrategy(str, Enum)` in context/protocols.py.
 */
export const CompactionStrategy = {
  /** Remove oldest messages. */
  TRUNCATE: 'truncate',
  /** Summarize old messages. */
  SUMMARISE: 'summarise',
  /** Remove old tool outputs. */
  DROP_OLDEST_TOOLS: 'drop_oldest_tools',
  /** Keep recent messages only. */
  SLIDING_WINDOW: 'sliding_window',
} as const;

export type CompactionStrategyType = typeof CompactionStrategy[keyof typeof CompactionStrategy];
