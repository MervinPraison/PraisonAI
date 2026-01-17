/**
 * Context Module Index - Export all context management utilities
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
    type BudgetAllocation,
    type ContextBudgeterConfig,
} from './budgeter';

export {
    ContextOptimizer,
    createContextOptimizer,
    type OptimizableItem,
    type OptimizationResult,
    type OptimizationStrategy,
    type ContextOptimizerConfig,
} from './optimizer';

// Default export
export { default } from './manager';
