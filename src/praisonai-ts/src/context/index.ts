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
} from './models';

// Default export
export { default } from './manager';
