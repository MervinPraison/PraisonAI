// Export base tool interfaces and classes
export { BaseTool, ToolResult, ToolValidationError, validateTool, createTool, type ToolParameters } from './base';

// Legacy @tool decorator registry (camelCase names reserved for this API)
export {
  tool, FunctionTool, ToolRegistry, getRegistry, registerTool, getTool,
  type ToolConfig, type ToolContext,
} from './decorator';

// Export all tool modules
export * from './arxivTools';
export * from './mcpSse';

// New AI SDK tools registry — snake_case parity names (avoid camelCase clash with decorator)
export {
  ToolsRegistry,
  getToolsRegistry,
  createToolsRegistry,
  resetToolsRegistry,
  get_registry,
  get_tool,
  register_tool,
  validate_tool,
} from './registry';
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
} from './registry';
export { MissingDependencyError, MissingEnvVarError, BudgetExceededError } from './registry';
export {
  createLoggingMiddleware,
  createTimeoutMiddleware,
  createRedactionMiddleware,
  createRateLimitMiddleware,
  createRetryMiddleware,
  createTracingMiddleware,
  createValidationMiddleware,
  composeMiddleware,
} from './registry';

// Export built-in tools
export * from './builtins';

// Export tools facade
export { tools, registerBuiltinTools } from './tools';
export type { default as ToolsFacade } from './tools';

// Export Subagent Tool (agent-as-tool pattern)
export {
    SubagentTool, createSubagentTool, createSubagentTools, createDelegator,
    type SubagentToolConfig, type SubagentToolSchema, type DelegatorConfig
} from './subagent';
