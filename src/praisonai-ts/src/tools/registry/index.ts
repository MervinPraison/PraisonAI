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

// Deprecated compatibility aliases.
//
// This subpath (`praisonai/tools/registry`) previously exported these names
// bound to the FACTORY registry. They had misleading semantics — the whole
// point of the rename — but the subpath is public via the package export map,
// so removing them outright breaks existing imports. Keep them pointing at the
// factory registry (their historical target) and steer callers to the new
// names. The Python-parity name-keyed registry lives at the package root and in
// `../decorator`, not here.
import {
  getToolsRegistry as _getToolsRegistry,
  registerToolFactory as _registerToolFactory,
  validateToolInstall as _validateToolInstall,
  tryCreateToolInstance as _tryCreateToolInstance,
} from './registry';

/** @deprecated use `getToolsRegistry` */
export const getRegistry = _getToolsRegistry;
/** @deprecated use `getToolsRegistry` */
export const get_registry = _getToolsRegistry;
/** @deprecated use `registerToolFactory` */
export const registerTool = _registerToolFactory;
/** @deprecated use `registerToolFactory` */
export const register_tool = _registerToolFactory;
/** @deprecated use `validateToolInstall` */
export const validateTool = _validateToolInstall;
/** @deprecated use `validateToolInstall` */
export const validate_tool = _validateToolInstall;
/** @deprecated use `tryCreateToolInstance` */
export const get_tool = _tryCreateToolInstance;

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
