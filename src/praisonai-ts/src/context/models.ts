/**
 * Context Management Data Models for PraisonAI TypeScript SDK.
 * 
 * Python parity with praisonaiagents/context/models.py:
 * - ContextSegment enum
 * - ContextLedger class
 * - BudgetAllocation class
 * - ContextSnapshot class
 * - OptimizerStrategy enum
 * - OptimizationResult class
 * - MonitorConfig class
 * - ContextConfig class
 */

// ============================================================================
// Context Segment Enum
// ============================================================================

/**
 * Segments that contribute to context.
 * Python parity with ContextSegment enum.
 */
export const ContextSegment = {
  SYSTEM_PROMPT: 'system_prompt',
  RULES: 'rules',
  SKILLS: 'skills',
  MEMORY: 'memory',
  TOOLS_SCHEMA: 'tools_schema',
  HISTORY: 'history',
  TOOL_OUTPUTS: 'tool_outputs',
  BUFFER: 'buffer',
} as const;

export type ContextSegmentType = typeof ContextSegment[keyof typeof ContextSegment];

// ============================================================================
// Optimizer Strategy Enum
// ============================================================================

/**
 * Context optimization strategies.
 * Python parity with OptimizerStrategy enum.
 */
export const OptimizerStrategy = {
  TRUNCATE: 'truncate',
  SLIDING_WINDOW: 'sliding_window',
  SUMMARIZE: 'summarize',
  PRUNE_TOOLS: 'prune_tools',
  NON_DESTRUCTIVE: 'non_destructive',
  SMART: 'smart',
} as const;

export type OptimizerStrategyType = typeof OptimizerStrategy[keyof typeof OptimizerStrategy];

// ============================================================================
// Context Ledger
// ============================================================================

/**
 * Tracks token usage across context segments.
 * Python parity with ContextLedger dataclass.
 */
export interface ContextLedger {
  systemPrompt: number;
  rules: number;
  skills: number;
  memory: number;
  toolsSchema: number;
  history: number;
  toolOutputs: number;
  buffer: number;
  turnCount: number;
  messageCount: number;
  toolCallCount: number;
}

/**
 * Create a new ContextLedger with defaults.
 */
export function createContextLedger(partial?: Partial<ContextLedger>): ContextLedger {
  return {
    systemPrompt: 0,
    rules: 0,
    skills: 0,
    memory: 0,
    toolsSchema: 0,
    history: 0,
    toolOutputs: 0,
    buffer: 0,
    turnCount: 0,
    messageCount: 0,
    toolCallCount: 0,
    ...partial,
  };
}

/**
 * Get total tokens from ledger.
 */
export function getLedgerTotal(ledger: ContextLedger): number {
  return (
    ledger.systemPrompt +
    ledger.rules +
    ledger.skills +
    ledger.memory +
    ledger.toolsSchema +
    ledger.history +
    ledger.toolOutputs +
    ledger.buffer
  );
}

// ============================================================================
// Budget Allocation
// ============================================================================

/**
 * Token budget allocation across segments.
 * Python parity with BudgetAllocation dataclass.
 */
export interface BudgetAllocation {
  modelLimit: number;
  outputReserve: number;
  systemPrompt: number;
  rules: number;
  skills: number;
  memory: number;
  toolsSchema: number;
  history: number;
  toolOutputs: number;
  buffer: number;
}

/**
 * Create a new BudgetAllocation with defaults.
 */
export function createBudgetAllocation(partial?: Partial<BudgetAllocation>): BudgetAllocation {
  return {
    modelLimit: 128000,
    outputReserve: 8000,
    systemPrompt: 2000,
    rules: 500,
    skills: 500,
    memory: 1000,
    toolsSchema: 2000,
    history: -1, // Dynamic: fills remaining
    toolOutputs: 20000,
    buffer: 1000,
    ...partial,
  };
}

/**
 * Get usable tokens after output reserve.
 */
export function getUsableBudget(budget: BudgetAllocation): number {
  return budget.modelLimit - budget.outputReserve;
}

/**
 * Get computed history budget.
 */
export function getHistoryBudget(budget: BudgetAllocation): number {
  if (budget.history > 0) {
    return budget.history;
  }
  const fixedTotal =
    budget.systemPrompt +
    budget.rules +
    budget.skills +
    budget.memory +
    budget.toolsSchema +
    budget.toolOutputs +
    budget.buffer;
  return Math.max(0, getUsableBudget(budget) - fixedTotal);
}

// ============================================================================
// Monitor Config
// ============================================================================

/**
 * Configuration for context monitoring.
 * Python parity with MonitorConfig dataclass.
 */
export interface MonitorConfig {
  enabled: boolean;
  path: string;
  format: 'human' | 'json';
  frequency: 'turn' | 'tool_call' | 'manual' | 'overflow';
  redactSensitive: boolean;
  multiAgentFiles: boolean;
}

/**
 * Create a new MonitorConfig with defaults.
 */
export function createMonitorConfig(partial?: Partial<MonitorConfig>): MonitorConfig {
  return {
    enabled: false,
    path: './context.txt',
    format: 'human',
    frequency: 'turn',
    redactSensitive: true,
    multiAgentFiles: true,
    ...partial,
  };
}

// ============================================================================
// Context Config
// ============================================================================

/**
 * Complete context management configuration.
 * Python parity with ContextConfig dataclass.
 */
export interface ContextConfig {
  // Auto-compaction
  autoCompact: boolean;
  compactThreshold: number;
  strategy: OptimizerStrategyType;

  // Budget overrides
  outputReserve: number;
  historyRatio: number;
  toolOutputMax: number;
  defaultToolOutputMax: number;

  // Pruning
  pruneAfterTokens: number;
  protectedTools: string[];

  // Per-tool output limits
  toolLimits: Record<string, number>;

  // Monitoring
  monitor: MonitorConfig;

  // Sliding window
  keepRecentTurns: number;

  // LLM-powered summarization
  llmSummarize: boolean;
  smartToolSummarize: boolean;

  // Session tracking (Agno pattern)
  sessionTracking: boolean;
  trackSummary: boolean;
  trackGoal: boolean;
  trackPlan: boolean;
  trackProgress: boolean;

  // Multi-memory aggregation (CrewAI pattern)
  aggregateMemory: boolean;
  aggregateSources: string[];
  aggregateMaxTokens: number;

  // Internal fields
  compressionMinGainPct: number;
  compressionMaxAttempts: number;
  toolBudgets: Record<string, any>;
  toolSummarizeLimits: Record<string, number>;
  estimationMode: string;
  logEstimationMismatch: boolean;
  mismatchThresholdPct: number;
  monitorEnabled: boolean;
  monitorPath: string;
  monitorFormat: string;
  monitorFrequency: string;
  monitorWriteMode: string;
  redactSensitive: boolean;
  snapshotTiming: string;
  allowAbsolutePaths: boolean;
  source: string;
}

/**
 * Create a new ContextConfig with defaults.
 */
export function createContextConfig(partial?: Partial<ContextConfig>): ContextConfig {
  return {
    autoCompact: true,
    compactThreshold: 0.8,
    strategy: OptimizerStrategy.SMART,
    outputReserve: 8000,
    historyRatio: 0.6,
    toolOutputMax: 10000,
    defaultToolOutputMax: 10000,
    pruneAfterTokens: 40000,
    protectedTools: [],
    toolLimits: {},
    monitor: createMonitorConfig(),
    keepRecentTurns: 5,
    llmSummarize: false,
    smartToolSummarize: true,
    sessionTracking: false,
    trackSummary: true,
    trackGoal: true,
    trackPlan: true,
    trackProgress: true,
    aggregateMemory: false,
    aggregateSources: ['memory', 'knowledge', 'rag'],
    aggregateMaxTokens: 4000,
    compressionMinGainPct: 5.0,
    compressionMaxAttempts: 3,
    toolBudgets: {},
    toolSummarizeLimits: {},
    estimationMode: 'heuristic',
    logEstimationMismatch: false,
    mismatchThresholdPct: 15.0,
    monitorEnabled: false,
    monitorPath: './context.txt',
    monitorFormat: 'human',
    monitorFrequency: 'turn',
    monitorWriteMode: 'sync',
    redactSensitive: true,
    snapshotTiming: 'post_optimization',
    allowAbsolutePaths: false,
    source: 'defaults',
    ...partial,
  };
}

/**
 * Create a recipe-optimized ContextConfig.
 * Python parity with ContextConfig.for_recipe().
 */
export function createRecipeContextConfig(): ContextConfig {
  return createContextConfig({
    autoCompact: true,
    compactThreshold: 0.7,
    strategy: OptimizerStrategy.SMART,
    toolOutputMax: 2000,
    keepRecentTurns: 3,
    pruneAfterTokens: 50000,
    outputReserve: 8000,
    historyRatio: 0.6,
  });
}

// ============================================================================
// Optimization Result
// ============================================================================

/**
 * Result of context optimization.
 * Python parity with OptimizationResult dataclass.
 */
export interface OptimizationResult {
  originalTokens: number;
  optimizedTokens: number;
  tokensSaved: number;
  strategyUsed: OptimizerStrategyType;
  messagesRemoved: number;
  messagesTagged: number;
  toolOutputsPruned: number;
  toolOutputsSummarized: number;
  tokensSavedBySummarization: number;
  tokensSavedByTruncation: number;
  summaryAdded: boolean;
}

/**
 * Create a new OptimizationResult with defaults.
 */
export function createOptimizationResult(partial?: Partial<OptimizationResult>): OptimizationResult {
  return {
    originalTokens: 0,
    optimizedTokens: 0,
    tokensSaved: 0,
    strategyUsed: OptimizerStrategy.SMART,
    messagesRemoved: 0,
    messagesTagged: 0,
    toolOutputsPruned: 0,
    toolOutputsSummarized: 0,
    tokensSavedBySummarization: 0,
    tokensSavedByTruncation: 0,
    summaryAdded: false,
    ...partial,
  };
}

/**
 * Get reduction percentage from optimization result.
 */
export function getReductionPercent(result: OptimizationResult): number {
  if (result.originalTokens === 0) {
    return 0;
  }
  return (result.tokensSaved / result.originalTokens) * 100;
}

// ============================================================================
// Context Snapshot
// ============================================================================

/**
 * A snapshot of the current context state.
 * Python parity with ContextSnapshot dataclass.
 */
export interface ContextSnapshot {
  timestamp: string;
  sessionId: string;
  agentName: string;
  modelName: string;
  budget: BudgetAllocation | null;
  ledger: ContextLedger | null;
  utilization: number;
  systemPromptContent: string;
  rulesContent: string;
  skillsContent: string;
  memoryContent: string;
  toolsSchemaContent: string;
  historyContent: Array<Record<string, any>>;
  warnings: string[];
}

/**
 * Create a new ContextSnapshot with defaults.
 */
export function createContextSnapshot(partial?: Partial<ContextSnapshot>): ContextSnapshot {
  return {
    timestamp: '',
    sessionId: '',
    agentName: '',
    modelName: '',
    budget: null,
    ledger: null,
    utilization: 0,
    systemPromptContent: '',
    rulesContent: '',
    skillsContent: '',
    memoryContent: '',
    toolsSchemaContent: '',
    historyContent: [],
    warnings: [],
    ...partial,
  };
}

// ============================================================================
// Manager Config (from context/manager.py)
// ============================================================================

/**
 * Configuration for ContextManager.
 * Python parity with ManagerConfig dataclass.
 */
export interface ManagerConfig {
  modelLimit: number;
  outputReserve: number;
  defaultToolOutputMax: number;
  compactThreshold: number;
  strategy: OptimizerStrategyType;
  compressionMinGainPct: number;
  compressionMaxAttempts: number;
  toolBudgets: Record<string, any>;
  toolSummarizeLimits: Record<string, number>;
  estimationMode: string;
  logEstimationMismatch: boolean;
  mismatchThresholdPct: number;
  monitorEnabled: boolean;
  monitorPath: string;
  monitorFormat: string;
  monitorFrequency: string;
  monitorWriteMode: string;
  redactSensitive: boolean;
  snapshotTiming: string;
  allowAbsolutePaths: boolean;
}

/**
 * Create a new ManagerConfig with defaults.
 */
export function createManagerConfig(partial?: Partial<ManagerConfig>): ManagerConfig {
  return {
    modelLimit: 128000,
    outputReserve: 8000,
    defaultToolOutputMax: 10000,
    compactThreshold: 0.8,
    strategy: OptimizerStrategy.SMART,
    compressionMinGainPct: 5.0,
    compressionMaxAttempts: 3,
    toolBudgets: {},
    toolSummarizeLimits: {},
    estimationMode: 'heuristic',
    logEstimationMismatch: false,
    mismatchThresholdPct: 15.0,
    monitorEnabled: false,
    monitorPath: './context.txt',
    monitorFormat: 'human',
    monitorFrequency: 'turn',
    monitorWriteMode: 'sync',
    redactSensitive: true,
    snapshotTiming: 'post_optimization',
    allowAbsolutePaths: false,
    ...partial,
  };
}
