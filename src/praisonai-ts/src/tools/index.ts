// Export base tool interfaces and classes
export {
  BaseTool, ToolResult, ToolValidationError, createTool, type ToolParameters,
  // `validate_tool(tool)` in Python takes the tool object and raises
  // ToolValidationError — that is this function, not the factory registry's
  // install/env report.
  validateTool, validate_tool,
} from './base';

// The Python-equivalent tool registry: ready-to-run tools looked up BY NAME
// (praisonaiagents/tools/registry.py + tools/decorator.py). The snake_case
// parity names resolve here.
export {
  tool, FunctionTool, ToolRegistry,
  functionToTool, coerceToFunctionTool,
  TOOL_TRUST_LEVELS,
  getRegistry, registerTool, getTool, hasTool, removeTool, listTools, getToolDefinitions,
  get_registry, register_tool, get_tool, has_tool, remove_tool, list_tools,
  get_tool_definitions, add_tool,
  type ToolConfig, type ToolContext, type RegisterableTool, type RegisterToolOptions,
  type ToolTrustLevel,
} from './decorator';

// Export all tool modules
export * from './arxivTools';
export * from './mcpSse';

// The AI SDK tools registry: tool FACTORIES keyed by install id, which BUILDS
// instances. A different contract from Python's registry, so it carries names
// that say so rather than borrowing the snake_case parity ones.
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
