/**
 * PraisonAI TypeScript SDK
 * 
 * The primary API surface consists of three core classes:
 * - Agent: Single AI agent with instructions, tools, and optional persistence
 * - Agents: Multi-agent orchestration (sequential or parallel)
 * - Workflow: Step-based workflow execution
 * 
 * @example Quickstart (3 lines)
 * ```typescript
 * import { Agent } from 'praisonai';
 * const agent = new Agent({ instructions: "You are helpful" });
 * await agent.chat("Hello!");
 * ```
 * 
 * @example With tools (5 lines)
 * ```typescript
 * const getWeather = (city: string) => `Weather in ${city}: 20°C`;
 * const agent = new Agent({ instructions: "You provide weather", tools: [getWeather] });
 * await agent.chat("Weather in Paris?");
 * ```
 * 
 * @example With persistence (4 lines)
 * ```typescript
 * import { Agent, db } from 'praisonai';
 * const agent = new Agent({ instructions: "You are helpful", db: db("sqlite:./data.db") });
 * await agent.chat("Hello!");
 * ```
 * 
 * @example Multi-agent (6 lines)
 * ```typescript
 * import { Agent, Agents } from 'praisonai';
 * const researcher = new Agent({ instructions: "Research the topic" });
 * const writer = new Agent({ instructions: "Write based on research" });
 * const agents = new Agents([researcher, writer]);
 * await agents.start();
 * ```
 */

// ============================================================================
// CORE API - The main classes users should use
// ============================================================================

// Agent - Single agent with instructions, tools, and optional persistence
export { Agent, Agents, PraisonAIAgents, Router } from './agent';
export type { SimpleAgentConfig, PraisonAIAgentsConfig, SimpleRouterConfig, SimpleRouteConfig } from './agent';

// Workflow - Step-based workflow execution
export {
  Workflow, parallel, route, loop, repeat,
  // New: Python-parity Loop and Repeat classes
  Loop, loopPattern, Repeat, repeatPattern,
  // WorkflowStep class
  WorkflowStep,
} from './workflows';
export type {
  WorkflowContext, StepResult, WorkflowStepConfig,
  LoopConfig, LoopResult, RepeatConfig, RepeatResult, RepeatContext,
  StepContextConfig, StepOutputConfig, StepExecutionConfig, StepRoutingConfig
} from './workflows';

// Database factory - Python-like db() shortcut
export { db, createDbAdapter, getDefaultDbAdapter, setDefaultDbAdapter } from './db';
export type { DbAdapter, DbConfig, DbMessage, DbRun, DbTrace } from './db';

// ============================================================================
// TOOLS - Function tools and tool registry
// ============================================================================
export {
  BaseTool, ToolResult, ToolValidationError, validateTool, createTool,
  FunctionTool, tool, ToolRegistry, getRegistry, registerTool, getTool,
  // Subagent Tool (agent-as-tool pattern)
  SubagentTool, createSubagentTool, createSubagentTools, createDelegator,
  type ToolConfig, type ToolContext, type ToolParameters,
  type SubagentToolConfig, type DelegatorConfig
} from './tools';
export * from './tools/arxivTools';
export * from './tools/mcpSse';

// AI SDK Tools Registry
export { tools, registerBuiltinTools } from './tools/tools';
export { getToolsRegistry, createToolsRegistry, resetToolsRegistry, ToolsRegistry } from './tools/registry';
export type {
  ToolExecutionContext, ToolLimits, RedactionHooks, ToolLogger,
  ToolCapabilities, InstallHints, ToolMetadata, ToolExecutionResult,
  PraisonTool, ToolParameterSchema, ToolParameterProperty,
  ToolMiddleware, ToolHooks, ToolFactory, RegisteredTool, ToolInstallStatus
} from './tools/registry';
export { MissingDependencyError, MissingEnvVarError } from './tools/registry';
export {
  createLoggingMiddleware, createTimeoutMiddleware, createRedactionMiddleware,
  createRateLimitMiddleware, createRetryMiddleware, createTracingMiddleware,
  createValidationMiddleware, composeMiddleware
} from './tools/registry';

// Built-in tool factories
export {
  codeExecution, tavilySearch, tavilyExtract, tavilyCrawl,
  exaSearch, perplexitySearch, parallelSearch,
  firecrawlScrape, firecrawlCrawl,
  superagentGuard, superagentRedact, superagentVerify,
  valyuWebSearch, valyuFinanceSearch, valyuPaperSearch, valyuBioSearch,
  valyuPatentSearch, valyuSecSearch, valyuEconomicsSearch, valyuCompanyResearch,
  bedrockCodeInterpreter, bedrockBrowserNavigate, bedrockBrowserClick, bedrockBrowserFill,
  airweaveSearch, codeMode,
  registerCustomTool, createCustomTool, registerNpmTool, registerLocalTool
} from './tools/builtins';

// ============================================================================
// SESSION & MEMORY
// ============================================================================
export * from './session';

// ============================================================================
// KNOWLEDGE & RAG
// ============================================================================
export * from './knowledge';

// ============================================================================
// CONTEXT MANAGEMENT
// ============================================================================
export * from './context';

// ============================================================================
// MCP (Model Context Protocol) - Client and Server Classes
// ============================================================================
export {
  MCPClient, createMCPClient, getMCPTools,
  MCPServer, createMCPServer,
  MCPSession as MCPSessionManager, createMCPSession,
  MCPSecurity, createMCPSecurity, createApiKeyPolicy, createRateLimitPolicy,
  type MCPClientConfig, type MCPSession, type MCPTransportType,
  type MCPServerConfig, type MCPServerTool,
  type SecurityPolicy, type SecurityResult
} from './mcp';

// ============================================================================
// LLM PROVIDERS
// ============================================================================
export * from './llm';
export * from './process';

// ============================================================================
// WORKFLOWS (additional exports)
// ============================================================================

// Export guardrails
export * from './guardrails';

// Export handoff
export { Handoff, handoff, handoffFilters, type HandoffConfig, type HandoffContext, type HandoffResult } from './agent/handoff';

// Export router agent
export { RouterAgent, createRouter, routeConditions, type RouterConfig, type RouteConfig, type RouteContext } from './agent/router';

// Export context agent
export { ContextAgent, createContextAgent, type ContextAgentConfig, type ContextMessage } from './agent/context';


// Export evaluation framework
export {
  accuracyEval, performanceEval, reliabilityEval, EvalSuite,
  Evaluator, createEvaluator, createDefaultEvaluator,
  EvalResults, createEvalResults,
  relevanceCriterion, lengthCriterion, containsKeywordsCriterion, noHarmfulContentCriterion,
  type EvalResult, type PerformanceResult, type AccuracyEvalConfig,
  type PerformanceEvalConfig, type ReliabilityEvalConfig, type EvalCriteria, type EvaluatorConfig,
  type TestResult, type AggregatedResults
} from './eval';

// Note: Observability exports are at the bottom of this file with the full 14+ integrations

// Export skills
export { SkillManager, createSkillManager, parseSkillFile, type Skill, type SkillMetadata, type SkillDiscoveryOptions } from './skills';

// Export CLI
export { parseArgs, executeCommand, CLI_SPEC_VERSION } from './cli';

// Export Memory (explicit for convenience)
export { Memory, createMemory } from './memory/memory';
export type { MemoryEntry, MemoryConfig } from './memory/memory';

// Export FileMemory
export { FileMemory, createFileMemory, type FileMemoryConfig, type FileMemoryEntry } from './memory/file-memory';

// Export AutoMemory
export {
  AutoMemory, createAutoMemory, createLLMSummarizer,
  DEFAULT_POLICIES,
  type AutoMemoryConfig, type AutoMemoryPolicy, type AutoMemoryContext,
  type VectorStoreAdapter as AutoMemoryVectorStore, type KnowledgeBaseAdapter as AutoMemoryKnowledgeBase
} from './memory/auto-memory';

// Export MemoryHooks (pre/post hooks for memory operations)
export {
  MemoryHooks, createMemoryHooks, createLoggingHooks, createValidationHooks, createEncryptionHooks,
  type MemoryHooksConfig, type BeforeStoreHook, type AfterStoreHook,
  type BeforeRetrieveHook, type AfterRetrieveHook,
  type BeforeDeleteHook, type AfterDeleteHook,
  type BeforeSearchHook, type AfterSearchHook
} from './memory/hooks';

// Export RulesManager (agent rules and policies)
export {
  RulesManager, createRulesManager, createSafetyRules,
  type Rule, type RuleAction, type RulePriority, type RuleContext, type RuleResult,
  type RulesEvaluation, type RulesManagerConfig
} from './memory/rules-manager';

// Export DocsManager (document management)
export {
  DocsManager, createDocsManager,
  type Doc, type DocChunk, type DocSearchResult, type DocsManagerConfig
} from './memory/docs-manager';

// ============================================================================
// HOOKS - Complete hooks and callbacks system (Python + CrewAI/Agno parity)
// ============================================================================

// HooksManager - Cascade hooks for operations (20 hook events)
export {
  HooksManager, createHooksManager,
  createLoggingHooks as createLoggingOperationHooks,
  createValidationHooks as createValidationOperationHooks,
  type HookEvent, type HookHandler, type HookResult, type HookConfig, type HooksManagerConfig
} from './hooks';

// Callback Registry - Display and approval callbacks
export {
  registerDisplayCallback, unregisterDisplayCallback,
  registerApprovalCallback, clearApprovalCallback,
  executeSyncCallback, executeCallback, requestApproval,
  hasApprovalCallback, getRegisteredDisplayTypes, clearAllCallbacks,
  DisplayTypes,
  type DisplayCallbackFn, type DisplayCallbackData,
  type ApprovalRequest, type ApprovalDecision, type ApprovalCallbackFn, type DisplayType
} from './hooks';

// Workflow Hooks - Lifecycle hooks
export {
  WorkflowHooksExecutor, createWorkflowHooks,
  createLoggingWorkflowHooks, createTimingWorkflowHooks,
  type WorkflowHooksConfig, type WorkflowRef, type StepContext
} from './hooks';

// Export Telemetry (Agent-focused)

export {
  TelemetryCollector, AgentTelemetry,
  getTelemetry, enableTelemetry, disableTelemetry, cleanupTelemetry, createAgentTelemetry,
  PerformanceMonitor, createPerformanceMonitor,
  TelemetryIntegration, createTelemetryIntegration, createConsoleSink, createHTTPSink,
  type TelemetryEvent, type TelemetryConfig, type AgentStats,
  type MetricEntry, type PerformanceStats, type PerformanceMonitorConfig,
  type TelemetryRecord, type TelemetrySink
} from './telemetry';

// Export AutoAgents
export { AutoAgents, createAutoAgents, type AgentConfig, type TaskConfig, type TeamStructure, type AutoAgentsConfig } from './auto';

// Export ImageAgent
export { ImageAgent, createImageAgent, type ImageAgentConfig, type ImageGenerationConfig, type ImageAnalysisConfig } from './agent/image';

// Export AudioAgent (AI SDK TTS/STT wrapper)
export { AudioAgent, createAudioAgent } from './agent/audio';
export type {
  AudioAgentConfig,
  SpeakOptions as AudioSpeakOptions,
  TranscribeOptions as AudioTranscribeOptions,
  SpeakResult as AudioSpeakResult,
  TranscribeResult as AudioTranscribeResult,
  AudioProvider
} from './agent/audio';

// Export DeepResearchAgent
export { DeepResearchAgent, createDeepResearchAgent, type DeepResearchConfig, type ResearchResponse, type Citation, type ReasoningStep } from './agent/research';

// Export QueryRewriterAgent
export { QueryRewriterAgent, createQueryRewriterAgent, type QueryRewriterConfig, type RewriteResult, type RewriteStrategy } from './agent/query-rewriter';

// Export PromptExpanderAgent
export { PromptExpanderAgent, createPromptExpanderAgent, type PromptExpanderConfig, type ExpandResult, type ExpandStrategy } from './agent/prompt-expander';


// Export LLMGuardrail
export { LLMGuardrail, createLLMGuardrail, type LLMGuardrailConfig, type LLMGuardrailResult } from './guardrails/llm-guardrail';

// Export Planning (simplified API)
export {
  Plan, PlanStep, TodoList, TodoItem, PlanStorage,
  PlanningAgent, TaskAgent,
  createPlan, createTodoList, createPlanStorage, createPlanningAgent, createTaskAgent,
  type PlanConfig, type PlanStepConfig, type TodoItemConfig, type PlanStatus, type TodoStatus,
  type PlanningAgentConfig, type PlanResult
} from './planning';

// Export Cache
export { BaseCache, MemoryCache, FileCache, createMemoryCache, createFileCache, type CacheConfig, type CacheEntry } from './cache';

// Export Events
export { PubSub, EventEmitterPubSub, AgentEventBus, AgentEvents, createEventBus, createPubSub, type Event, type EventHandler } from './events';

// Export YAML Workflow Parser
export { parseYAMLWorkflow, createWorkflowFromYAML, loadWorkflowFromFile, validateWorkflowDefinition, type YAMLWorkflowDefinition, type YAMLStepDefinition, type ParsedWorkflow } from './workflows/yaml-parser';

// Export SQLite Adapter
export { SQLiteAdapter, createSQLiteAdapter, type SQLiteConfig } from './db/sqlite';

// Export Redis Adapter
export {
  UpstashRedisAdapter, MemoryRedisAdapter,
  createUpstashRedis, createMemoryRedis,
  type RedisConfig, type RedisAdapter
} from './db/redis';

// Export PostgreSQL Adapter
export {
  NeonPostgresAdapter, MemoryPostgresAdapter, PostgresSessionStorage,
  createNeonPostgres, createMemoryPostgres, createPostgresSessionStorage,
  type PostgresConfig, type PostgresAdapter
} from './db/postgres';

// Export Integrations - Vector Stores
export {
  BaseVectorStore, MemoryVectorStore, createMemoryVectorStore,
  PineconeVectorStore, createPineconeStore,
  WeaviateVectorStore, createWeaviateStore,
  QdrantVectorStore, createQdrantStore,
  ChromaVectorStore, createChromaStore,
  type VectorDocument, type QueryResult as VectorQueryResult, type IndexStats
} from './integrations/vector';

// Export Integrations - Observability
export {
  BaseObservabilityProvider, ConsoleObservabilityProvider, MemoryObservabilityProvider,
  LangfuseObservabilityProvider,
  createConsoleObservability, createMemoryObservability, createLangfuseObservability,
  type Span, type TraceContext as ObservabilityTraceContext, type LogEntry, type Metric
} from './integrations/observability';

// Export Integrations - Voice
export {
  BaseVoiceProvider, OpenAIVoiceProvider, ElevenLabsVoiceProvider,
  createOpenAIVoice, createElevenLabsVoice,
  type VoiceConfig, type SpeakOptions, type ListenOptions, type Speaker
} from './integrations/voice';

// Export Reranker
export {
  BaseReranker, CohereReranker, CrossEncoderReranker, LLMReranker,
  createCohereReranker, createCrossEncoderReranker, createLLMReranker,
  type RerankResult, type RerankConfig
} from './knowledge/reranker';

// Export Graph RAG
export {
  GraphStore, GraphRAG, createGraphRAG,
  type GraphNode, type GraphEdge, type GraphQueryResult, type GraphRAGConfig
} from './knowledge/graph-rag';

// Export providers with explicit names to avoid conflicts
export {
  // Provider factory and utilities
  createProvider,
  getDefaultProvider,
  parseModelString,
  isProviderAvailable,
  getAvailableProviders,
  // Provider classes
  OpenAIProvider,
  AnthropicProvider,
  GoogleProvider,
  BaseProvider,
  // Provider registry (extensibility API)
  ProviderRegistry,
  registerProvider,
  unregisterProvider,
  hasProvider,
  listProviders,
  getDefaultRegistry,
  createProviderRegistry,
  registerBuiltinProviders,
  // Types
  type LLMProvider,
  type ProviderConfig,
  type ProviderFactory,
  type ProviderConstructor,
  type ProviderLoader,
  type RegisterOptions,
  type IProviderRegistry,
  type ProviderInput,
  type CreateProviderOptions,
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

// Export Observability (14+ integrations)
export {
  // Types
  type SpanKind,
  type SpanStatus,
  type SpanData,
  type SpanEvent,
  type TraceData,
  type TraceContext,
  type SpanContext,
  type ObservabilityAdapter,
  type AttributionContext,
  type ProviderMetadata,
  type ObservabilityToolConfig,
  type ObservabilityToolName,
  type ObservabilityToolInfo,
  // Constants
  OBSERVABILITY_TOOLS,
  getObservabilityToolInfo,
  listObservabilityTools,
  hasObservabilityToolEnvVar,
  // Adapters
  NoopObservabilityAdapter,
  noopAdapter,
  MemoryObservabilityAdapter,
  createMemoryAdapter,
  ConsoleObservabilityAdapter,
  createConsoleAdapter,
  createObservabilityAdapter,
  clearAdapterCache,
  // Global adapter management
  setObservabilityAdapter,
  getObservabilityAdapter,
  resetObservabilityAdapter,
  trace,
} from './observability';

// Export AI SDK Provider Types (60+ providers)
export {
  AISDK_PROVIDERS,
  PROVIDER_ALIASES,
  COMMUNITY_PROVIDERS,
  ADAPTERS,
  type ProviderInfo,
  type ProviderModalities,
  type CommunityProvider,
  type AdapterInfo,
} from './llm/providers/ai-sdk/types';

// Export CLI Features
export {
  // Slash Commands
  SlashCommandHandler, createSlashCommandHandler, registerCommand, parseSlashCommand,
  executeSlashCommand, isSlashCommand,
  type SlashCommand, type SlashCommandContext, type SlashCommandResult,
  // Cost Tracker
  CostTracker, createCostTracker, estimateTokens, formatCost, MODEL_PRICING,
  type ModelPricing, type TokenUsage as CostTokenUsage, type RequestStats, type SessionStats,
  // Interactive TUI
  InteractiveTUI, createInteractiveTUI, StatusDisplay, createStatusDisplay,
  HistoryManager, createHistoryManager,
  type TUIConfig, type TUIState,
  // Repo Map
  RepoMap, createRepoMap, getRepoTree, DEFAULT_IGNORE_PATTERNS,
  type RepoMapConfig, type FileInfo, type SymbolInfo, type RepoMapResult,
  // Git Integration
  GitManager, createGitManager, DiffViewer, createDiffViewer,
  type GitConfig, type GitStatus, type GitCommit, type GitDiff, type GitDiffFile,
  // Sandbox Executor
  SandboxExecutor, createSandboxExecutor, sandboxExec, CommandValidator,
  DEFAULT_BLOCKED_COMMANDS, DEFAULT_BLOCKED_PATHS,
  type SandboxMode, type SandboxConfig, type ExecutionResult,
  // Autonomy Mode
  AutonomyManager, createAutonomyManager, cliApprovalPrompt, MODE_POLICIES,
  type AutonomyMode, type ActionType, type ApprovalPolicy, type AutonomyConfig,
  type ActionRequest, type ActionDecision,
  // Scheduler
  Scheduler, createScheduler, cronExpressions,
  type ScheduleConfig, type ScheduledTask, type SchedulerStats,
  // Background Jobs
  JobQueue, createJobQueue, MemoryJobStorage, FileJobStorage, createFileJobStorage,
  type Job, type JobStatus, type JobPriority, type JobQueueConfig,
  type JobStorageAdapter, type JobHandler, type JobContext,
  // Checkpoints
  CheckpointManager, createCheckpointManager, MemoryCheckpointStorage,
  FileCheckpointStorage, createFileCheckpointStorage,
  type CheckpointData, type CheckpointConfig, type CheckpointStorage,
  // Flow Display
  FlowDisplay, createFlowDisplay, renderWorkflow,
  type FlowNode, type FlowGraph, type FlowDisplayConfig,
  // External Agents
  BaseExternalAgent, ClaudeCodeAgent, GeminiCliAgent, CodexCliAgent, AiderAgent,
  GenericExternalAgent, getExternalAgentRegistry, createExternalAgent, externalAgentAsTool,
  type ExternalAgentConfig, type ExternalAgentResult,
  // N8N Integration
  N8NIntegration, createN8NIntegration, triggerN8NWebhook,
  type N8NConfig, type N8NWebhookPayload, type N8NWorkflow, type N8NWorkflowNode,
  // Fast Context
  FastContext, createFastContext, getQuickContext,
  type FastContextConfig, type ContextSource, type FastContextResult
} from './cli/features';

// ============================================================================
// AI SDK WRAPPER MODULE - Core execution primitives
// ============================================================================
export {
  // Text generation (renamed to avoid conflicts with provider exports)
  generateText as aiGenerateText,
  streamText as aiStreamText,
  type GenerateTextOptions as AIGenerateTextOptions,
  type GenerateTextResult as AIGenerateTextResult,
  type StreamTextOptions as AIStreamTextOptions,
  type StreamTextResult as AIStreamTextResult,
  type TextStreamPart,
  // Object generation
  generateObject as aiGenerateObject,
  streamObject as aiStreamObject,
  type GenerateObjectOptions as AIGenerateObjectOptions,
  type GenerateObjectResult as AIGenerateObjectResult,
  type StreamObjectOptions as AIStreamObjectOptions,
  type StreamObjectResult as AIStreamObjectResult,
  // Image generation
  generateImage as aiGenerateImage,
  type GenerateImageOptions as AIGenerateImageOptions,
  type GenerateImageResult as AIGenerateImageResult,
  // Embeddings (renamed to avoid conflicts)
  embed as aiEmbed,
  embedMany as aiEmbedMany,
  type EmbedOptions as AIEmbedOptions,
  type EmbedResult as AIEmbedResult,
  type EmbedManyResult as AIEmbedManyResult,
  // Tools
  defineTool,
  createToolSet,
  functionToTool,
  type ToolDefinition as AIToolDefinition,
  type ToolExecuteFunction,
  type ToolInput,
  type ToolOutput,
  // Models
  createModel,
  getModel,
  parseModel,
  MODEL_ALIASES,
  listModelAliases,
  hasModelAlias,
  resolveModelAlias,
  type ModelConfig,
  type ModelId,
  // Middleware (renamed to avoid conflicts)
  createCachingMiddleware,
  createLoggingMiddleware as createAILoggingMiddleware,
  wrapModel,
  applyMiddleware,
  clearCache as clearAICache,
  getCacheStats as getAICacheStats,
  type Middleware as AIMiddleware,
  type MiddlewareConfig as AIMiddlewareConfig,
  type MiddlewareRequest,
  type MiddlewareResponse,
  // Multimodal
  createImagePart,
  createFilePart,
  createPdfPart,
  createTextPart,
  createMultimodalMessage,
  toMessageContent,
  base64ToUint8Array,
  uint8ArrayToBase64,
  isUrl,
  isDataUrl,
  type InputPart,
  type ImagePart as AIImagePart,
  type FilePart as AIFilePart,
  type PdfPart,
  type TextPart as AITextPart,
  // MCP
  createMCP,
  getMCPClient,
  closeMCPClient,
  closeAllMCPClients,
  mcpToolsToAITools,
  type MCPConfig,
  type MCPClient as MCPClientType,
  type MCPTool,
  type MCPResource,
  type MCPPrompt,
  // Server adapters
  createHttpHandler,
  createExpressHandler,
  createHonoHandler,
  createFastifyHandler,
  createNestHandler,
  type ServerHandler,
  type ServerHandlerConfig,
  // Next.js
  createRouteHandler,
  createPagesHandler,
  type RouteHandlerConfig,
  type UseChatConfig,
  // Agent loop
  createAgentLoop,
  AgentLoop,
  stopAfterSteps,
  stopWhenNoToolCalls,
  stopWhen,
  type AgentLoopConfig,
  type AgentStep as AIAgentStep,
  type AgentLoopResult,
  type StopCondition,
  // UI Message (AI SDK v6 parity)
  convertToModelMessages,
  convertToUIMessages,
  validateUIMessages,
  safeValidateUIMessages,
  createTextMessage,
  createSystemMessage,
  hasPendingApprovals,
  getToolsNeedingApproval,
  createApprovalResponse,
  toUIMessageStreamResponse,
  pipeUIMessageStreamToResponse,
  type UIMessage,
  type UIMessagePart,
  type TextUIPart,
  type ReasoningUIPart,
  type ToolUIPart,
  type FileUIPart,
  type DataUIPart,
  type ModelMessage as AIModelMessage,
  type UIMessageStreamOptions,
  // Tool Approval (AI SDK v6 parity)
  ApprovalManager,
  getApprovalManager,
  setApprovalManager,
  withApproval,
  ToolApprovalDeniedError,
  ToolApprovalTimeoutError,
  DANGEROUS_PATTERNS,
  isDangerous,
  createDangerousPatternChecker,
  type ToolApprovalConfig,
  type ToolApprovalRequest,
  type ToolApprovalResponse,
  type ApprovalState,
  type ApprovalHandler,
  // Speech & Transcription
  generateSpeech,
  transcribe,
  SPEECH_MODELS,
  TRANSCRIPTION_MODELS,
  type GenerateSpeechOptions,
  type GenerateSpeechResult,
  type TranscribeOptions,
  type TranscribeResult,
  type TranscriptionSegment,
  // DevTools
  enableDevTools,
  disableDevTools,
  isDevToolsEnabled,
  getDevToolsState,
  getDevToolsUrl,
  createDevToolsMiddleware,
  autoEnableDevTools,
  type DevToolsConfig,
  type DevToolsState,
  // Telemetry (AI SDK v6 parity)
  configureTelemetry,
  getTelemetrySettings,
  enableAITelemetry,
  disableAITelemetry,
  isTelemetryEnabled,
  initOpenTelemetry,
  getTracer,
  createAISpan,
  withSpan,
  createTelemetryMiddleware,
  recordEvent,
  getEvents,
  clearEvents,
  createTelemetrySettings,
  type TelemetrySettings as AITelemetrySettings,
  type Tracer as AITracer,
  type Span as AISpan,
  type SpanOptions as AISpanOptions,
  type SpanKind as AISpanKind,
  type SpanStatus as AISpanStatus,
  type TelemetryEvent as AITelemetryEvent,
  // OAuth for MCP
  type OAuthClientProvider,
} from './ai';

// ============================================================================
// INTEGRATIONS - Slack, Postgres, Computer Use
// ============================================================================
export {
  // Slack
  createSlackBot,
  SlackBot,
  verifySlackSignature,
  parseSlackMessage,
  type SlackConfig,
  type SlackMessage,
  type SlackResponse,
  type SlackEventHandler,
} from './integrations/slack';

export {
  // Natural Language Postgres
  createNLPostgres,
  NLPostgresClient,
  createPostgresTool,
  type PostgresConfig as NLPostgresConfig,
  type TableSchema,
  type ColumnSchema,
  type QueryResult,
  type NLQueryResult,
} from './integrations/postgres';

export {
  // Computer Use
  createComputerUse,
  ComputerUseClient,
  createComputerUseAgent,
  createCLIApprovalPrompt,
  type ComputerUseConfig,
  type ComputerUseTools,
  type ComputerAction,
  type ScreenshotResult,
} from './integrations/computer-use';