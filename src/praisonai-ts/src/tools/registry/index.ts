/**
 * AI SDK Tools Registry - Main Exports
 * 
 * Lazy-loaded exports for the tools registry system.
 */

// Types
export type {
  ToolExecutionContext,
  ToolLimits,
  RedactionHooks,
  ToolLogger,
  ToolCapabilities,
  InstallHints,
  ToolMetadata,
  ToolExecutionResult,
  PraisonTool,
  ToolParameterSchema,
  ToolParameterProperty,
  ToolMiddleware,
  ToolHooks,
  ToolFactory,
  RegisteredTool,
  ToolInstallStatus,
} from './types';

// Errors
export { MissingDependencyError, MissingEnvVarError, BudgetExceededError } from './types';

// Registry — factory-registry names. The snake_case Python parity names
// (get_registry / register_tool / get_tool / validate_tool) belong to the
// name-keyed registry in ../decorator and ../base, not to this module.
export {
  ToolsRegistry,
  getToolsRegistry,
  createToolsRegistry,
  resetToolsRegistry,
  registerToolFactory,
  createToolInstance,
  tryCreateToolInstance,
  validateToolInstall,
  ToolNotRegisteredError,
  ToolConstructionError,
  /** @deprecated use tryCreateToolInstance */
  getTool,
} from './registry';

// Middleware
export {
  createLoggingMiddleware,
  createTimeoutMiddleware,
  createRedactionMiddleware,
  createRateLimitMiddleware,
  createRetryMiddleware,
  createTracingMiddleware,
  createValidationMiddleware,
  composeMiddleware,
} from './middleware';
