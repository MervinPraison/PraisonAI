//! Parity Module - Implements all missing Python SDK features
//!
//! This module provides full feature parity with the Python SDK by implementing:
//! - UI protocols (A2A, AGUI)
//! - Plugin protocols and functions
//! - Config types and loader functions
//! - Parameter resolver and ArrayMode
//! - Parse utilities
//! - Workflow pattern aliases
//! - Telemetry functions
//! - Display/Callback types
//! - Specialized agent types
//! - Deep Research types
//! - RAG types
//! - Guardrail types
//! - Embedding functions
//! - Module re-exports

pub mod ui;
pub mod plugins;
pub mod config_loader;
pub mod param_resolver;
pub mod parse_utils;
pub mod workflow_aliases;
pub mod telemetry_funcs;
pub mod display_types;
pub mod specialized;
pub mod extras;

// Re-export UI types
pub use ui::{
    A2A, AGUI, A2AAgentCard, A2AAgentCapabilities, A2AAgentSkill, A2ATask, A2ATaskState,
    AGUIEvent, AGUIEventType, AGUIMessage, AGUIRole, AGUIRunInput,
};

// Re-export plugin types (with renamed PluginType to avoid conflict)
pub use plugins::{
    PluginProtocol, ToolPluginProtocol, HookPluginProtocol, AgentPluginProtocol, LLMPluginProtocol,
    PluginMetadata, PluginType as ParityPluginType, PluginParseError, PluginRegistry,
    ToolDefinition as ParityToolDefinition, LLMMessage,
    parse_plugin_header, parse_plugin_header_from_file, discover_plugins, get_default_plugin_dirs,
    discover_and_load_plugins, ensure_plugin_dir, get_plugin_template,
};

// Re-export config loader types (with renamed AutoRagConfig)
pub use config_loader::{
    PraisonConfig, PluginsConfig, DefaultsConfig, ManagerConfig, 
    SessionConfig, ConfigValidationError, PluginsEnabled,
    get_config, get_config_path, get_plugins_config, get_defaults_config, get_default,
    is_plugins_enabled, get_enabled_plugins, apply_config_defaults, validate_config,
};
// Rename AutoRagConfig from config_loader to avoid conflict with specialized
pub use config_loader::AutoRagConfig as ConfigAutoRagConfig;

// Re-export param resolver types (excluding detect_url_scheme and is_path_like which are in parse_utils)
pub use param_resolver::{
    ArrayMode, ResolvedValue, ResolveOptions, StringMode,
    resolve, resolve_memory, resolve_knowledge, resolve_output, resolve_execution,
    resolve_planning, resolve_reflection, resolve_context, resolve_routing,
    resolve_hooks, resolve_guardrails, resolve_web, resolve_autonomy, resolve_caching, resolve_skills,
};

// Re-export parse utilities
pub use parse_utils::{
    detect_url_scheme, is_path_like, is_numeric_string, is_policy_string, parse_policy_string,
    suggest_similar, clean_triple_backticks, clean_whitespace, extract_json,
    validate_keys, make_preset_error, make_array_error,
};

// Re-export workflow aliases (with renamed types to avoid conflicts)
pub use workflow_aliases::{
    Workflow, Pipeline, Agents as ParityAgents, AgentManager,
    loop_step, parallel, repeat, route, when,
    HandoffConfig as ParityHandoffConfig, HandoffFilters as ParityHandoffFilters, HandoffFilter,
    handoff, handoff_filters, prompt_with_handoff_instructions,
};

// Re-export telemetry functions
pub use telemetry_funcs::{
    MinimalTelemetry, TelemetryContext,
    get_telemetry, enable_telemetry, disable_telemetry, is_telemetry_enabled,
    enable_performance_mode, disable_performance_mode, is_performance_mode, cleanup_telemetry_resources,
};

// Re-export display types
pub use display_types::{
    ErrorLog, DisplayCallback, AsyncDisplayCallback, DisplayEvent as ParityDisplayEvent, 
    DisplayEventType as ParityDisplayEventType, ApprovalCallback as ParityApprovalCallback,
    ApprovalDecision as ParityApprovalDecision, RiskLevel as ParityRiskLevel, FlowDisplay, PraisonColors,
    get_error_logs, add_error_log, clear_error_logs, log_error,
    register_display_callback as parity_register_display_callback,
    register_async_display_callback as parity_register_async_display_callback,
    add_display_callback as parity_add_display_callback,
    remove_display_callback as parity_remove_display_callback,
    execute_callback, execute_async_callback,
    register_approval_callback as parity_register_approval_callback,
    add_approval_callback as parity_add_approval_callback,
    remove_approval_callback as parity_remove_approval_callback,
    request_approval as parity_request_approval,
    WORKING_FRAMES as PARITY_WORKING_FRAMES, WORKING_PHASES as PARITY_WORKING_PHASES,
};

// Re-export specialized types
pub use specialized::{
    ContextAgent, ContextAgentConfig, ContextStrategy, ContextEntry, create_context_agent, create_context_agent_with_config,
    PlanningAgent, PlanningAgentConfig, PlanningStep, PlanningStepStatus,
    FastContext, AutoAgents, AutoAgentsConfig, AutoAgentSpec,
    AutoRagAgent, AutoRagConfig as SpecializedAutoRagConfig, TraceSinkProtocol, TraceEvent, ContextTraceSink, TraceSink,
    MemoryBackend, Tools,
};

// Re-export extras types (Deep Research, RAG, Guardrails, Embedding, etc.)
pub use extras::{
    // Deep Research types
    Citation, ReasoningStep, WebSearchCall, CodeExecutionStep, FileSearchCall,
    Provider, DeepResearchResponse,
    // RAG types
    RAGCitation, RetrievalPolicy, RagRetrievalPolicy,
    // Guardrail types
    LLMGuardrail,
    // Handoff errors
    HandoffError, HandoffCycleError, HandoffDepthError, HandoffTimeoutError,
    // App protocols
    AgentAppProtocol, AgentOSProtocol, AgentAppConfig,
    // Sandbox types
    SecurityPolicy,
    // Reflection types
    ReflectionOutput,
    // Embedding functions
    EmbeddingResult, EmbeddingUsage,
    embed, embedding, embeddings, aembed, aembedding, aembeddings,
    // Display callbacks
    sync_display_callbacks, async_display_callbacks, error_logs,
    // Presets
    AUTONOMY_PRESETS, RECOMMENDED_PROMPT_PREFIX,
    // Resolver functions
    resolve_guardrail_policies,
    // Trace functions
    TraceContextData, trace_context, track_workflow,
    // Plugin functions
    load_plugin,
};

// Re-export module placeholders for Python parity
pub use extras::config;
pub use extras::memory;
pub use extras::tools;
pub use extras::workflows;
pub use extras::db;
pub use extras::obs;

// Type alias for Agents (Python SDK compatibility)
pub type Agents = ParityAgents;
