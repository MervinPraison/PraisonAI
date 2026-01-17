// Export base tool interfaces and classes
export { BaseTool, ToolResult, ToolValidationError, validateTool, createTool, type ToolParameters } from './base';

// Export decorator and registry (legacy)
export * from './decorator';

// Export all tool modules
export * from './arxivTools';
export * from './mcpSse';

// Export new registry system
export * from './registry';

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
