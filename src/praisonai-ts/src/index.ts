// Export all public modules
export * from './agent';
export * from './knowledge';
export * from './llm';
export * from './memory';
export * from './process';

// Export tools (excluding conflicting types)
export { 
  Tool, BaseTool, 
  FunctionTool, tool, ToolRegistry, getRegistry, registerTool, getTool,
  type ToolConfig, type ToolContext, type ToolParameters
} from './tools';
export * from './tools/arxivTools';
export * from './tools/mcpSse';

// Export session management
export * from './session';

// Export database adapters
export * from './db';

// Export workflows
export * from './workflows';

// Export guardrails
export * from './guardrails';

// Export handoff
export { Handoff, handoff, handoffFilters, type HandoffConfig, type HandoffContext, type HandoffResult } from './agent/handoff';

// Export router agent
export { RouterAgent, createRouter, routeConditions, type RouterConfig, type RouteConfig, type RouteContext } from './agent/router';

// Export context agent
export { ContextAgent, createContextAgent, type ContextAgentConfig, type ContextMessage } from './agent/context';

// Export knowledge base (RAG)
export { KnowledgeBase, createKnowledgeBase, type Document, type SearchResult, type EmbeddingProvider, type KnowledgeBaseConfig } from './knowledge/rag';

// Export evaluation framework
export { accuracyEval, performanceEval, reliabilityEval, EvalSuite, type EvalResult, type PerformanceResult, type AccuracyEvalConfig, type PerformanceEvalConfig, type ReliabilityEvalConfig } from './eval';

// Export observability
export { MemoryObservabilityAdapter, ConsoleObservabilityAdapter, setObservabilityAdapter, getObservabilityAdapter, type ObservabilityAdapter, type TraceContext, type SpanContext, type SpanData, type TraceData } from './observability';

// Export skills
export { SkillManager, createSkillManager, parseSkillFile, type Skill, type SkillMetadata, type SkillDiscoveryOptions } from './skills';

// Export CLI
export { chat, listProviders, version, help } from './cli';

// Export providers with explicit names to avoid conflicts
export {
  createProvider,
  getDefaultProvider,
  parseModelString,
  isProviderAvailable,
  getAvailableProviders,
  OpenAIProvider,
  AnthropicProvider,
  GoogleProvider,
  BaseProvider,
  type LLMProvider,
  type ProviderConfig,
  type ProviderFactory,
  type GenerateTextOptions,
  type GenerateTextResult,
  type StreamTextOptions,
  type StreamChunk,
  type GenerateObjectOptions,
  type GenerateObjectResult,
  type TokenUsage,
  type Message as ProviderMessage,
  type ToolCall,
  type ToolDefinition as ProviderToolDefinition,
} from './llm/providers';