//! PraisonAI Core - High-performance, agentic AI framework for Rust
//!
//! This crate provides the core functionality for building AI agents and multi-agent workflows.
//!
//! # Quick Start
//!
//! ```rust,ignore
//! use praisonai::{Agent, tool};
//!
//! #[tool(description = "Search the web")]
//! async fn search(query: String) -> String {
//!     format!("Results for: {}", query)
//! }
//!
//! #[tokio::main]
//! async fn main() -> anyhow::Result<()> {
//!     let agent = Agent::new()
//!         .instructions("You are a helpful assistant")
//!         .build();
//!     
//!     let response = agent.chat("Hello!").await?;
//!     println!("{}", response);
//!     Ok(())
//! }
//! ```
//!
//! # Architecture
//!
//! PraisonAI follows an agent-centric design with these core components:
//!
//! - **Agent**: The core execution unit that processes prompts and uses tools
//! - **Tool**: Functions that agents can call to perform actions
//! - **AgentTeam**: Coordinates multiple agents for complex workflows
//! - **AgentFlow**: Defines workflow patterns (sequential, parallel, etc.)
//! - **Memory**: Persists conversation history and context
//!
//! # Design Principles
//!
//! - **Agent-Centric**: Every design decision centers on Agents
//! - **Protocol-Driven**: Traits define contracts, implementations are pluggable
//! - **Minimal API**: Fewer parameters, sensible defaults
//! - **Performance-First**: Lazy loading, optional dependencies
//! - **Async-Safe**: All I/O operations are async

pub mod agent;
pub mod agents;
pub mod bots;
pub mod bus;
pub mod conditions;
pub mod config;
pub mod context;
pub mod display;
pub mod embedding;
pub mod error;
pub mod eval;
pub mod failover;
pub mod gateway;
pub mod guardrails;
pub mod handoff;
pub mod hooks;
pub mod knowledge;
pub mod llm;
pub mod mcp;
pub mod memory;
pub mod planning;
pub mod plugins;
pub mod policy;
pub mod presets;
pub mod protocols;
pub mod rag;
pub mod sandbox;
pub mod session;
pub mod skills;
pub mod specialized_agents;
pub mod streaming;
pub mod task;
pub mod telemetry;
pub mod thinking;
pub mod tools;
pub mod trace;
pub mod workflows;

// Parity module - Python SDK feature parity
pub mod parity;

// Re-export core types for simple API
pub use agent::{Agent, AgentBuilder, AgentConfig};
pub use config::{
    // Feature configs
    AutonomyConfig,
    AutonomyLevel,
    CachingConfig,
    ChunkingStrategy,
    // Core configs
    ExecutionConfig,
    GuardrailAction,
    GuardrailConfig,
    GuardrailResult,
    HooksConfig,
    KnowledgeConfig,
    MemoryConfig,
    // Multi-agent configs
    MultiAgentExecutionConfig,
    MultiAgentHooksConfig,
    MultiAgentMemoryConfig,
    MultiAgentOutputConfig,
    MultiAgentPlanningConfig,
    OutputConfig,
    PlanningConfig,
    ReflectionConfig,
    SkillsConfig,
    TemplateConfig,
    WebConfig,
    WebSearchProvider,
};
pub use error::{Error, Result};
pub use hooks::{HookDecision, HookEvent, HookInput, HookRegistry, HookResult, HookRunner};
pub use llm::{
    LlmConfig, LlmProvider, LlmResponse, Message, MockLlmProvider, Role, ToolCall, Usage,
};
pub use memory::{ConversationHistory, Memory, MemoryAdapter};
pub use session::{
    FileSessionStore, InMemorySessionStore, Session, SessionData, SessionInfo, SessionMessage,
    SessionStore,
};
pub use task::{OnError, Task, TaskBuilder, TaskConfig, TaskOutput, TaskStatus, TaskType};
pub use tools::{Tool, ToolRegistry, ToolResult};
pub use workflows::{
    AgentFlow, AgentTeam, Loop, Parallel, Process, Repeat, Route, StepResult, WorkflowContext,
};

// Handoff system
pub use handoff::{
    ContextPolicy, Handoff, HandoffChain, HandoffConfig, HandoffFilters, HandoffInputData,
    HandoffResult,
};

// Context management
pub use context::{
    BudgetAllocation, ContextBudgeter, ContextConfig, ContextLedger, ContextManager,
    ContextSegment, MultiAgentContextManager, OptimizerStrategy,
};

// Plugin system
pub use plugins::{
    FunctionPlugin, Plugin, PluginHook, PluginInfo, PluginManager, PluginType,
};

// Event bus
pub use bus::{Event, EventBus, EventType};

// Specialized agents
pub use agents::{
    AudioAgent, AudioAgentBuilder, AudioConfig, CodeAgent, CodeAgentBuilder, CodeConfig,
    CodeExecutionResult, DeepResearchAgent, DeepResearchAgentBuilder, DeepResearchConfig,
    DeepResearchResult, ImageAgent, ImageAgentBuilder, ImageConfig, ImageResult, OCRAgent,
    OCRAgentBuilder, OCRConfig, OCRPage, OCRResult, RealtimeAgent, RealtimeAgentBuilder,
    RealtimeConfig, ResearchCitation, VideoAgent, VideoAgentBuilder, VideoConfig, VideoResult,
    VideoStatus, VisionAgent, VisionAgentBuilder, VisionConfig,
};

// RAG system
pub use rag::{
    build_context, deduplicate_chunks, estimate_tokens, get_model_context_window, truncate_context,
    Citation, CitationsMode, ContextChunk, ContextPack, RAGBuilder, RAGConfig, RAGResult,
    RetrievalConfig, RetrievalResult, RetrievalStrategy, TokenBudget, RAG,
};

// MCP integration
pub use mcp::{
    ConnectionStatus, MCPBuilder, MCPCall, MCPCallResult, MCPConfig, MCPContent, MCPPrompt,
    MCPResource, MCPServer, MCPTool, SecurityConfig, TransportConfig, TransportType, MCP,
};

// Protocol system
pub use protocols::{
    AgentMetrics, AgentOSConfig, AgentOSProtocol, AgentProtocol, BotAction, BotAttachment,
    BotMessage, BotProtocol, BotResponse, LlmMessage, LlmProtocol, LlmResponse as ProtocolLlmResponse,
    MemoryMessage, MemoryProtocol, RunnableAgentProtocol, TokenUsage, ToolCall as ProtocolToolCall,
    ToolProtocol, ToolSchema,
};

// Knowledge system
pub use knowledge::{
    AddResult as KnowledgeAddResult, Chunking, ChunkingConfig, ChunkingStrategy as KnowledgeChunkingStrategy,
    Document, IndexStats, IndexType, InMemoryVectorStore, Knowledge, KnowledgeBackendError,
    KnowledgeBuilder, KnowledgeConfig as KnowledgeModuleConfig, KnowledgeStoreProtocol, QueryMode, QueryResult,
    RerankerProtocol, RerankResult, RetrievalResult as KnowledgeRetrievalResult,
    RetrievalStrategy as KnowledgeRetrievalStrategy, RetrieverProtocol, ScopeRequiredError,
    SearchResult, SearchResultItem, SimpleReranker, VectorRecord, VectorStoreProtocol,
};

// Streaming system
pub use streaming::{
    AsyncStreamCallback, StreamCallback, StreamCollector, StreamEvent, StreamEventType,
    StreamHandler, StreamMetrics, ToolCallData,
};

// Guardrails system
pub use guardrails::{
    AsyncGuardrail, BlocklistGuardrail, FunctionGuardrail, Guardrail, GuardrailAction as GuardrailsAction,
    GuardrailChain, GuardrailConfig as GuardrailsConfig, GuardrailResult as GuardrailsResult,
    LengthGuardrail, PatternGuardrail,
};

// Thinking system
pub use thinking::{
    BudgetLevel, ThinkingBudget, ThinkingBudgetBuilder, ThinkingConfig, ThinkingTracker,
    ThinkingUsage,
};

// Skills system
pub use skills::{
    format_skill_for_prompt, generate_skills_xml, ParseError, SkillLoader, SkillManager,
    SkillMetadata, SkillProperties, ValidationError,
};

// Planning system
pub use planning::{
    is_read_only_tool, is_research_tool, is_restricted_tool, Plan, PlanStep, PlanStorage,
    StepStatus, TodoItem, TodoList, TodoPriority, READ_ONLY_TOOLS, RESEARCH_TOOLS,
    RESTRICTED_TOOLS,
};

// Eval system
pub use eval::{
    AccuracyEvaluator, AccuracyEvaluatorBuilder, AccuracyResult, CriteriaEvaluator,
    CriteriaEvaluatorBuilder, CriteriaResult, CriteriaScore, EvaluationScore, EvaluatorConfig,
    Judge, JudgeConfig, JudgeResult, PerformanceEvaluator, PerformanceEvaluatorBuilder,
    PerformanceMetrics, PerformanceResult, ReliabilityEvaluator, ReliabilityEvaluatorBuilder,
    ReliabilityResult, ToolCallResult as EvalToolCallResult,
};

// Telemetry system
pub use telemetry::{
    get_collector, get_monitor, get_performance_report, record_event, track_api, track_function,
    ApiStats, FunctionStats, PerformanceMonitor, PerformanceReport, TelemetryCollector,
    TelemetryEvent, TelemetryEventType,
};

// Policy system
pub use policy::{
    credit_card_rule, email_rule, phone_rule, profanity_rule, ssn_rule, PolicyAction,
    PolicyEngine, PolicyResult, PolicyRule,
};

// Trace system
pub use trace::{
    ConsoleExporter, ContextEvent, ContextEventType, ContextListSink, ContextNoOpSink,
    ContextTraceEmitter, ContextTraceSinkProtocol, JsonFileExporter, Span, SpanEvent, SpanKind,
    SpanStatus, TraceContext, TraceExporter, Tracer,
};

// Embedding system
pub use embedding::{
    cosine_similarity, get_dimensions, EmbeddingAgent, EmbeddingAgentBuilder, EmbeddingConfig,
    EmbeddingResult, EmbeddingUsage, SimilarityResult,
};

// Failover system
pub use failover::{
    AuthProfile, FailoverConfig, FailoverManager, FailoverStatus, ProviderStatus,
};

// Gateway system
pub use gateway::{
    EventType as GatewayEventType, GatewayClientProtocol, GatewayConfig, GatewayEvent,
    GatewayHealth, GatewayMessage, GatewayProtocol, GatewaySessionProtocol,
};

// Sandbox system
pub use sandbox::{
    ResourceLimits, ResourceUsage, SandboxConfig, SandboxProtocol, SandboxResult, SandboxStatus,
    SandboxStatusInfo,
};

// Conditions system
pub use conditions::{
    evaluate_condition, ClosureCondition, ConditionProtocol, DictCondition, ExpressionCondition,
    If, RoutingConditionProtocol,
};

// Bots system
pub use bots::{
    BotChannel, BotConfig, BotMessage as BotsChatMessage, BotProtocol as BotsChatProtocol,
    BotUser, MessageType,
};

// FastContext types (from context module)
pub use context::{
    FastContextConfig, FastContextResult, FileMatch, LineRange,
};

// Display system
pub use display::{
    // Types
    ApprovalDecision, ColorPalette, DisplayEvent, DisplayType, RiskLevel,
    // Callback types (re-exported for convenience)
    // Functions
    add_approval_callback, add_display_callback, callback_count, clean_display_content,
    clear_all_callbacks, clear_display_callbacks, display_error, display_generating,
    display_instruction, display_interaction, display_reasoning_steps, display_self_reflection,
    display_tool_call, display_working_status, execute_async_callbacks, execute_callbacks,
    execute_sync_callbacks, has_callbacks, register_approval_callback,
    register_async_display_callback, register_display_callback, request_approval,
    // Constants
    PRAISON_COLORS, WORKING_FRAMES, WORKING_PHASES,
};

// Presets system
pub use presets::{
    // Preset types
    AutonomyPreset, CachingPreset, ContextPreset, ExecutionPreset, GuardrailPreset,
    KnowledgePreset, MemoryPreset, MultiAgentExecutionPreset, MultiAgentOutputPreset,
    OutputPreset, PlanningPreset, ReflectionPreset, WebPreset, WorkflowStepExecutionPreset,
    // Static preset maps
    AUTONOMY_PRESETS, CACHING_PRESETS, CONTEXT_PRESETS, EXECUTION_PRESETS, GUARDRAIL_PRESETS,
    KNOWLEDGE_PRESETS, MEMORY_PRESETS, MEMORY_URL_SCHEMES, MULTI_AGENT_EXECUTION_PRESETS,
    MULTI_AGENT_OUTPUT_PRESETS, OUTPUT_PRESETS, PLANNING_PRESETS, REFLECTION_PRESETS,
    WEB_PRESETS, WORKFLOW_STEP_EXECUTION_PRESETS,
    // Resolve functions
    detect_memory_backend, resolve_autonomy_preset, resolve_caching_preset,
    resolve_context_preset, resolve_execution_preset, resolve_guardrail_preset,
    resolve_knowledge_preset, resolve_memory_preset, resolve_multi_agent_execution_preset,
    resolve_multi_agent_output_preset, resolve_output_preset, resolve_planning_preset,
    resolve_reflection_preset, resolve_web_preset, resolve_workflow_step_execution_preset,
    // Constants
    DEFAULT_OUTPUT_MODE,
};

// Specialized agents
pub use specialized_agents::{
    // PromptExpanderAgent
    ExpandPrompts, ExpandResult, ExpandStrategy, PromptExpanderAgent, PromptExpanderAgentBuilder,
    PromptExpanderConfig,
    // QueryRewriterAgent
    QueryRewriterAgent, QueryRewriterAgentBuilder, QueryRewriterConfig, RewritePrompts,
    RewriteResult, RewriteStrategy,
};

// Parity module - Python SDK feature parity exports
pub use parity::{
    // UI protocols
    A2A, AGUI, A2AAgentCard, A2AAgentCapabilities, A2AAgentSkill, A2ATask, A2ATaskState,
    AGUIEvent, AGUIEventType, AGUIMessage, AGUIRole, AGUIRunInput,
    // Plugin protocols (ParityPluginType to avoid conflict with existing PluginType)
    PluginProtocol, ToolPluginProtocol, HookPluginProtocol, AgentPluginProtocol, LLMPluginProtocol,
    PluginMetadata, ParityPluginType, PluginParseError, PluginRegistry as ParityPluginRegistry,
    ParityToolDefinition, LLMMessage,
    parse_plugin_header, parse_plugin_header_from_file, discover_plugins, get_default_plugin_dirs,
    discover_and_load_plugins, ensure_plugin_dir, get_plugin_template,
    // Config loader (SessionConfig renamed to avoid conflict)
    PraisonConfig, PluginsConfig, DefaultsConfig, ManagerConfig, 
    SessionConfig as ParitySessionConfig, ConfigValidationError, PluginsEnabled,
    ConfigAutoRagConfig, SpecializedAutoRagConfig,
    get_config, get_config_path, get_plugins_config, get_defaults_config, get_default,
    is_plugins_enabled, get_enabled_plugins, apply_config_defaults, validate_config,
    // Parameter resolver
    ArrayMode, ResolvedValue, ResolveOptions, StringMode,
    resolve, resolve_memory, resolve_knowledge, resolve_output, resolve_execution,
    resolve_planning, resolve_reflection, resolve_context, resolve_routing,
    resolve_hooks, resolve_guardrails, resolve_web, resolve_autonomy, resolve_caching, resolve_skills,
    // Parse utilities
    detect_url_scheme, is_path_like, is_numeric_string, is_policy_string, parse_policy_string,
    suggest_similar, clean_triple_backticks, clean_whitespace, extract_json,
    validate_keys, make_preset_error, make_array_error,
    // Workflow aliases (renamed to avoid conflicts with existing types)
    Workflow, Pipeline, ParityAgents, AgentManager, Agents,
    loop_step, parallel as parallel_step, repeat as repeat_step, route as route_step, when,
    ParityHandoffConfig, ParityHandoffFilters, HandoffFilter, handoff, handoff_filters, prompt_with_handoff_instructions,
    // Telemetry functions
    MinimalTelemetry, TelemetryContext,
    get_telemetry, enable_telemetry, disable_telemetry, is_telemetry_enabled,
    enable_performance_mode, disable_performance_mode, is_performance_mode, cleanup_telemetry_resources,
    // Display types
    ErrorLog, DisplayCallback, AsyncDisplayCallback, ParityDisplayEvent, 
    ParityDisplayEventType, ParityApprovalCallback,
    ParityApprovalDecision, ParityRiskLevel, FlowDisplay, PraisonColors,
    get_error_logs, add_error_log, clear_error_logs, log_error,
    parity_register_display_callback, parity_register_async_display_callback,
    parity_add_display_callback, parity_remove_display_callback,
    execute_callback, execute_async_callback,
    parity_register_approval_callback, parity_add_approval_callback,
    parity_remove_approval_callback, parity_request_approval,
    PARITY_WORKING_FRAMES, PARITY_WORKING_PHASES,
    // Specialized types
    ContextAgent, ContextAgentConfig, ContextStrategy, ContextEntry, create_context_agent, create_context_agent_with_config,
    PlanningAgent, PlanningAgentConfig, PlanningStep, PlanningStepStatus,
    FastContext, AutoAgents, AutoAgentsConfig, AutoAgentSpec,
    AutoRagAgent, TraceSinkProtocol, TraceEvent, ContextTraceSink, TraceSink,
    MemoryBackend, Tools,
    // Deep Research types (extras) - renamed to avoid conflicts
    Citation as DeepResearchCitation, ReasoningStep, WebSearchCall, CodeExecutionStep, FileSearchCall,
    Provider, DeepResearchResponse,
    // RAG types (extras)
    RAGCitation, RetrievalPolicy, RagRetrievalPolicy,
    // Guardrail types (extras)
    LLMGuardrail,
    // Handoff errors (extras)
    HandoffError, HandoffCycleError, HandoffDepthError, HandoffTimeoutError,
    // App protocols (extras) - renamed to avoid conflicts
    AgentAppProtocol, AgentOSProtocol as ParityAgentOSProtocol, AgentAppConfig,
    // Sandbox types (extras)
    SecurityPolicy,
    // Reflection types (extras)
    ReflectionOutput,
    // Embedding functions (extras) - renamed to avoid conflicts
    EmbeddingResult as ParityEmbeddingResult, EmbeddingUsage as ParityEmbeddingUsage,
    embed, embedding, embeddings, aembed, aembedding, aembeddings,
    // Display callbacks (extras)
    sync_display_callbacks, async_display_callbacks, error_logs,
    // Presets (extras) - renamed to avoid conflicts
    AUTONOMY_PRESETS as PARITY_AUTONOMY_PRESETS, RECOMMENDED_PROMPT_PREFIX,
    // Resolver functions (extras)
    resolve_guardrail_policies,
    // Trace functions (extras)
    TraceContextData, trace_context, track_workflow,
    // Plugin functions (extras)
    load_plugin,
};

// Note: The following Python SDK items have Rust equivalents:
// - `AUTONOMY_PRESETS` - exported from presets module
// - `RAGCitation` - exported as Citation from rag module  
// - `Workflow` - exported from parity module
// - `loop` is a reserved keyword in Rust, use `loop_step` instead
// - `config`, `db`, `obs`, `memory`, `tools`, `workflows` are modules in Python
//   that already exist in Rust as pub mod declarations

// Re-export the tool macro from praisonai-derive
pub use praisonai_derive::tool;

/// Prelude module for convenient imports
pub mod prelude {
    pub use crate::{
        tool, Agent, AgentBuilder, AgentConfig, AgentFlow, AgentTeam, Error, HookEvent,
        HookRegistry, HookResult, LlmConfig, LlmProvider, Loop, Memory, MemoryConfig, Message,
        Parallel, Process, Repeat, Result, Role, Route, Session, Task, TaskOutput, Tool,
        ToolRegistry, ToolResult,
    };
}
