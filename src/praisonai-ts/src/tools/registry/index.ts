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

// Registry
export {
  ToolsRegistry,
  getToolsRegistry,
  createToolsRegistry,
  resetToolsRegistry,
  get_registry,
  getRegistry,
  get_tool,
  getTool,
  register_tool,
  registerTool,
  validate_tool,
  validateTool,
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
