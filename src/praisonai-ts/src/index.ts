// Export all public modules
export * from './agent';
export * from './knowledge';
export * from './llm';
export * from './memory';
export * from './process';

// Export tools (excluding conflicting types)
export { 
  BaseTool, ToolResult, ToolValidationError, validateTool, createTool,
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

// Export Memory
export { Memory, createMemory, type MemoryEntry, type MemoryConfig, type SearchResult as MemorySearchResult } from './memory/memory';

// Export Telemetry
export { TelemetryCollector, getTelemetry, enableTelemetry, disableTelemetry, cleanupTelemetry, type TelemetryEvent, type TelemetryConfig } from './telemetry';

// Export AutoAgents
export { AutoAgents, createAutoAgents, type AgentConfig, type TaskConfig, type TeamStructure, type AutoAgentsConfig } from './auto';

// Export ImageAgent
export { ImageAgent, createImageAgent, type ImageAgentConfig, type ImageGenerationConfig, type ImageAnalysisConfig } from './agent/image';

// Export DeepResearchAgent
export { DeepResearchAgent, createDeepResearchAgent, type DeepResearchConfig, type ResearchResponse, type Citation, type ReasoningStep } from './agent/research';

// Export QueryRewriterAgent
export { QueryRewriterAgent, createQueryRewriterAgent, type QueryRewriterConfig, type RewriteResult, type RewriteStrategy } from './agent/query-rewriter';

// Export PromptExpanderAgent
export { PromptExpanderAgent, createPromptExpanderAgent, type PromptExpanderConfig, type ExpandResult, type ExpandStrategy } from './agent/prompt-expander';

// Export Chunking
export { Chunking, createChunking, type ChunkingConfig, type Chunk, type ChunkStrategy } from './knowledge/chunking';

// Export LLMGuardrail
export { LLMGuardrail, createLLMGuardrail, type LLMGuardrailConfig, type LLMGuardrailResult } from './guardrails/llm-guardrail';

// Export Planning
export { Plan, PlanStep, TodoList, TodoItem, PlanStorage, createPlan, createTodoList, createPlanStorage, type PlanConfig, type PlanStepConfig, type TodoItemConfig, type PlanStatus, type TodoStatus } from './planning';

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