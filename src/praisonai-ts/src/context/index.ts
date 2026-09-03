/**
 * Context Module Index - Export all context management utilities
 * 
 * Python parity with praisonaiagents/context/__init__.py
 */

export {
    ContextManager,
    createContextManager,
    type ContextItem,
    type ContextBudget,
    type ContextManagerConfig,
} from './manager';

export {
    ContextBudgeter,
    createContextBudgeter,
    type BudgetAllocation as ContextBudgeterAllocation,
    type ContextBudgeterConfig,
} from './budgeter';

export {
    ContextOptimizer,
    createContextOptimizer,
    type OptimizableItem,
    type OptimizationResult as ContextOptimizationResult,
    type OptimizationStrategy,
    type ContextOptimizerConfig,
} from './optimizer';

// Python parity models
export {
    ContextSegment,
    type ContextSegmentType,
    OptimizerStrategy,
    type OptimizerStrategyType,
    type ContextLedger,
    createContextLedger,
    getLedgerTotal,
    type BudgetAllocation,
    createBudgetAllocation,
    getUsableBudget,
    getHistoryBudget,
    type MonitorConfig,
    createMonitorConfig,
    type ContextConfig,
    createContextConfig,
    createRecipeContextConfig,
    type OptimizationResult,
    createOptimizationResult,
    getReductionPercent,
    type ContextSnapshot,
    createContextSnapshot,
    type ManagerConfig,
    createManagerConfig,
    compactionStrategyToOptimizerStrategy,
    applyCompactionPolicy,
} from './models';

// Context compaction policy (Python parity with context/policy.py,
// context/protocols.py and context/adapters.py)
export {
    CompactionRoute,
    type CompactionRouteType,
    CompactionStrategy,
    type CompactionStrategyType,
    toCompactionStrategy,
    ContextBudgetResult,
    type ContextBudgetResultInit,
    type ContextCompactionPolicyProtocol,
    isContextCompactionPolicy,
    ContextCompactionPolicy,
    type ContextCompactionPolicyConfig,
    type ContextMessage,
    type ToolSchema,
    type ModelOverrides,
    CONSERVATIVE_POLICY,
    BALANCED_POLICY,
    AGGRESSIVE_POLICY,
    getDefaultPolicy,
} from './policy';

// Default export
export { default } from './manager';
