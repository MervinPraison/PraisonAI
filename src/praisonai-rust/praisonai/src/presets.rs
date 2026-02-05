//! Preset configurations for PraisonAI
//!
//! This module provides preset configurations that match the Python SDK's presets.py.
//! Presets allow users to configure features using simple string names.
//!
//! # Example
//!
//! ```rust,ignore
//! use praisonai::presets::{MEMORY_PRESETS, resolve_memory_preset};
//!
//! // Get preset by name
//! if let Some(config) = resolve_memory_preset("sqlite") {
//!     println!("Backend: {}", config.backend);
//! }
//! ```

use crate::config::{
    AutonomyConfig, AutonomyLevel, CachingConfig, ChunkingStrategy, ExecutionConfig,
    GuardrailAction, GuardrailConfig, KnowledgeConfig, MemoryConfig, MultiAgentExecutionConfig,
    MultiAgentOutputConfig, OutputConfig, PlanningConfig, ReflectionConfig, WebConfig,
    WebSearchProvider,
};
use once_cell::sync::Lazy;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// =============================================================================
// MEMORY PRESETS
// =============================================================================

/// Memory preset configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryPreset {
    /// Memory backend type
    pub backend: String,
    /// Additional configuration options
    #[serde(flatten)]
    pub options: HashMap<String, serde_json::Value>,
}

impl MemoryPreset {
    /// Create a new memory preset
    pub fn new(backend: impl Into<String>) -> Self {
        Self {
            backend: backend.into(),
            options: HashMap::new(),
        }
    }

    /// Add an option
    pub fn option(mut self, key: impl Into<String>, value: impl Into<serde_json::Value>) -> Self {
        self.options.insert(key.into(), value.into());
        self
    }
}

/// Memory presets matching Python SDK
pub static MEMORY_PRESETS: Lazy<HashMap<&'static str, MemoryPreset>> = Lazy::new(|| {
    let mut presets = HashMap::new();
    presets.insert("file", MemoryPreset::new("file"));
    presets.insert("sqlite", MemoryPreset::new("sqlite"));
    presets.insert("postgres", MemoryPreset::new("postgres"));
    presets.insert("redis", MemoryPreset::new("redis"));
    presets.insert("chroma", MemoryPreset::new("chroma"));
    presets.insert("qdrant", MemoryPreset::new("qdrant"));
    presets.insert("pinecone", MemoryPreset::new("pinecone"));
    presets.insert("weaviate", MemoryPreset::new("weaviate"));
    presets.insert("milvus", MemoryPreset::new("milvus"));
    presets.insert("mongodb", MemoryPreset::new("mongodb"));
    presets.insert("mem0", MemoryPreset::new("mem0"));
    presets.insert("memory", MemoryPreset::new("memory"));
    presets
});

/// Memory URL schemes for automatic backend detection
pub static MEMORY_URL_SCHEMES: Lazy<HashMap<&'static str, &'static str>> = Lazy::new(|| {
    let mut schemes = HashMap::new();
    schemes.insert("file://", "file");
    schemes.insert("sqlite://", "sqlite");
    schemes.insert("postgres://", "postgres");
    schemes.insert("postgresql://", "postgres");
    schemes.insert("redis://", "redis");
    schemes.insert("rediss://", "redis");
    schemes.insert("chroma://", "chroma");
    schemes.insert("qdrant://", "qdrant");
    schemes.insert("pinecone://", "pinecone");
    schemes.insert("weaviate://", "weaviate");
    schemes.insert("milvus://", "milvus");
    schemes.insert("mongodb://", "mongodb");
    schemes.insert("mongodb+srv://", "mongodb");
    schemes
});

/// Resolve a memory preset by name
pub fn resolve_memory_preset(name: &str) -> Option<MemoryPreset> {
    MEMORY_PRESETS.get(name).cloned()
}

/// Detect memory backend from URL
pub fn detect_memory_backend(url: &str) -> Option<&'static str> {
    for (scheme, backend) in MEMORY_URL_SCHEMES.iter() {
        if url.starts_with(scheme) {
            return Some(backend);
        }
    }
    None
}

// =============================================================================
// OUTPUT PRESETS
// =============================================================================

/// Output preset configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OutputPreset {
    /// Verbose output
    pub verbose: bool,
    /// Markdown formatting
    pub markdown: bool,
    /// Show tool calls
    pub show_tool_calls: bool,
    /// Show reasoning
    pub show_reasoning: bool,
    /// Stream output
    pub stream: bool,
}

impl Default for OutputPreset {
    fn default() -> Self {
        Self {
            verbose: true,
            markdown: true,
            show_tool_calls: true,
            show_reasoning: false,
            stream: true,
        }
    }
}

/// Output presets matching Python SDK
pub static OUTPUT_PRESETS: Lazy<HashMap<&'static str, OutputPreset>> = Lazy::new(|| {
    let mut presets = HashMap::new();
    
    presets.insert("silent", OutputPreset {
        verbose: false,
        markdown: false,
        show_tool_calls: false,
        show_reasoning: false,
        stream: false,
    });
    
    presets.insert("minimal", OutputPreset {
        verbose: false,
        markdown: false,
        show_tool_calls: false,
        show_reasoning: false,
        stream: true,
    });
    
    presets.insert("verbose", OutputPreset {
        verbose: true,
        markdown: true,
        show_tool_calls: true,
        show_reasoning: false,
        stream: true,
    });
    
    presets.insert("debug", OutputPreset {
        verbose: true,
        markdown: true,
        show_tool_calls: true,
        show_reasoning: true,
        stream: true,
    });
    
    presets.insert("json", OutputPreset {
        verbose: false,
        markdown: false,
        show_tool_calls: false,
        show_reasoning: false,
        stream: false,
    });
    
    presets
});

/// Default output mode
pub const DEFAULT_OUTPUT_MODE: &str = "verbose";

/// Resolve an output preset by name
pub fn resolve_output_preset(name: &str) -> Option<OutputPreset> {
    OUTPUT_PRESETS.get(name).cloned()
}

// =============================================================================
// EXECUTION PRESETS
// =============================================================================

/// Execution preset configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutionPreset {
    /// Maximum iterations
    pub max_iter: usize,
    /// Maximum retries
    pub max_retries: usize,
    /// Timeout in seconds
    pub timeout_secs: u64,
    /// Allow parallel execution
    pub allow_parallel: bool,
}

impl Default for ExecutionPreset {
    fn default() -> Self {
        Self {
            max_iter: 10,
            max_retries: 3,
            timeout_secs: 300,
            allow_parallel: true,
        }
    }
}

/// Execution presets matching Python SDK
pub static EXECUTION_PRESETS: Lazy<HashMap<&'static str, ExecutionPreset>> = Lazy::new(|| {
    let mut presets = HashMap::new();
    
    presets.insert("default", ExecutionPreset::default());
    
    presets.insert("fast", ExecutionPreset {
        max_iter: 5,
        max_retries: 1,
        timeout_secs: 60,
        allow_parallel: true,
    });
    
    presets.insert("thorough", ExecutionPreset {
        max_iter: 20,
        max_retries: 5,
        timeout_secs: 600,
        allow_parallel: true,
    });
    
    presets.insert("safe", ExecutionPreset {
        max_iter: 10,
        max_retries: 3,
        timeout_secs: 300,
        allow_parallel: false,
    });
    
    presets.insert("unlimited", ExecutionPreset {
        max_iter: 100,
        max_retries: 10,
        timeout_secs: 3600,
        allow_parallel: true,
    });
    
    presets
});

/// Resolve an execution preset by name
pub fn resolve_execution_preset(name: &str) -> Option<ExecutionPreset> {
    EXECUTION_PRESETS.get(name).cloned()
}

// =============================================================================
// WEB PRESETS
// =============================================================================

/// Web preset configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WebPreset {
    /// Enable search
    pub search: bool,
    /// Enable fetch
    pub fetch: bool,
    /// Search provider
    pub provider: String,
    /// Max results
    pub max_results: usize,
}

impl Default for WebPreset {
    fn default() -> Self {
        Self {
            search: true,
            fetch: true,
            provider: "duckduckgo".to_string(),
            max_results: 5,
        }
    }
}

/// Web presets matching Python SDK
pub static WEB_PRESETS: Lazy<HashMap<&'static str, WebPreset>> = Lazy::new(|| {
    let mut presets = HashMap::new();
    
    presets.insert("default", WebPreset::default());
    
    presets.insert("duckduckgo", WebPreset {
        search: true,
        fetch: true,
        provider: "duckduckgo".to_string(),
        max_results: 5,
    });
    
    presets.insert("google", WebPreset {
        search: true,
        fetch: true,
        provider: "google".to_string(),
        max_results: 10,
    });
    
    presets.insert("tavily", WebPreset {
        search: true,
        fetch: true,
        provider: "tavily".to_string(),
        max_results: 10,
    });
    
    presets.insert("serper", WebPreset {
        search: true,
        fetch: true,
        provider: "serper".to_string(),
        max_results: 10,
    });
    
    presets.insert("search_only", WebPreset {
        search: true,
        fetch: false,
        provider: "duckduckgo".to_string(),
        max_results: 5,
    });
    
    presets.insert("fetch_only", WebPreset {
        search: false,
        fetch: true,
        provider: "duckduckgo".to_string(),
        max_results: 5,
    });
    
    presets.insert("disabled", WebPreset {
        search: false,
        fetch: false,
        provider: "duckduckgo".to_string(),
        max_results: 0,
    });
    
    presets
});

/// Resolve a web preset by name
pub fn resolve_web_preset(name: &str) -> Option<WebPreset> {
    WEB_PRESETS.get(name).cloned()
}

// =============================================================================
// PLANNING PRESETS
// =============================================================================

/// Planning preset configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlanningPreset {
    /// Enable planning
    pub enabled: bool,
    /// Read-only mode
    pub read_only: bool,
    /// Enable reasoning
    pub reasoning: bool,
    /// Auto-approve plans
    pub auto_approve: bool,
    /// Max reasoning steps
    pub max_reasoning_steps: usize,
}

impl Default for PlanningPreset {
    fn default() -> Self {
        Self {
            enabled: true,
            read_only: false,
            reasoning: false,
            auto_approve: false,
            max_reasoning_steps: 5,
        }
    }
}

/// Planning presets matching Python SDK
pub static PLANNING_PRESETS: Lazy<HashMap<&'static str, PlanningPreset>> = Lazy::new(|| {
    let mut presets = HashMap::new();
    
    presets.insert("default", PlanningPreset::default());
    
    presets.insert("read_only", PlanningPreset {
        enabled: true,
        read_only: true,
        reasoning: false,
        auto_approve: false,
        max_reasoning_steps: 5,
    });
    
    presets.insert("reasoning", PlanningPreset {
        enabled: true,
        read_only: false,
        reasoning: true,
        auto_approve: false,
        max_reasoning_steps: 10,
    });
    
    presets.insert("auto", PlanningPreset {
        enabled: true,
        read_only: false,
        reasoning: false,
        auto_approve: true,
        max_reasoning_steps: 5,
    });
    
    presets.insert("full_auto", PlanningPreset {
        enabled: true,
        read_only: false,
        reasoning: true,
        auto_approve: true,
        max_reasoning_steps: 10,
    });
    
    presets.insert("disabled", PlanningPreset {
        enabled: false,
        read_only: false,
        reasoning: false,
        auto_approve: false,
        max_reasoning_steps: 0,
    });
    
    presets
});

/// Resolve a planning preset by name
pub fn resolve_planning_preset(name: &str) -> Option<PlanningPreset> {
    PLANNING_PRESETS.get(name).cloned()
}

// =============================================================================
// REFLECTION PRESETS
// =============================================================================

/// Reflection preset configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReflectionPreset {
    /// Enable reflection
    pub enabled: bool,
    /// Minimum iterations
    pub min_iterations: usize,
    /// Maximum iterations
    pub max_iterations: usize,
}

impl Default for ReflectionPreset {
    fn default() -> Self {
        Self {
            enabled: true,
            min_iterations: 1,
            max_iterations: 3,
        }
    }
}

/// Reflection presets matching Python SDK
pub static REFLECTION_PRESETS: Lazy<HashMap<&'static str, ReflectionPreset>> = Lazy::new(|| {
    let mut presets = HashMap::new();
    
    presets.insert("default", ReflectionPreset::default());
    
    presets.insert("minimal", ReflectionPreset {
        enabled: true,
        min_iterations: 1,
        max_iterations: 1,
    });
    
    presets.insert("thorough", ReflectionPreset {
        enabled: true,
        min_iterations: 2,
        max_iterations: 5,
    });
    
    presets.insert("extensive", ReflectionPreset {
        enabled: true,
        min_iterations: 3,
        max_iterations: 10,
    });
    
    presets.insert("disabled", ReflectionPreset {
        enabled: false,
        min_iterations: 0,
        max_iterations: 0,
    });
    
    presets
});

/// Resolve a reflection preset by name
pub fn resolve_reflection_preset(name: &str) -> Option<ReflectionPreset> {
    REFLECTION_PRESETS.get(name).cloned()
}

// =============================================================================
// GUARDRAIL PRESETS
// =============================================================================

/// Guardrail preset configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GuardrailPreset {
    /// Enable guardrails
    pub enabled: bool,
    /// Maximum retries
    pub max_retries: usize,
    /// Action on failure
    pub on_fail: String,
    /// Policies to apply
    pub policies: Vec<String>,
}

impl Default for GuardrailPreset {
    fn default() -> Self {
        Self {
            enabled: true,
            max_retries: 3,
            on_fail: "retry".to_string(),
            policies: vec![],
        }
    }
}

/// Guardrail presets matching Python SDK
pub static GUARDRAIL_PRESETS: Lazy<HashMap<&'static str, GuardrailPreset>> = Lazy::new(|| {
    let mut presets = HashMap::new();
    
    presets.insert("default", GuardrailPreset::default());
    
    presets.insert("strict", GuardrailPreset {
        enabled: true,
        max_retries: 1,
        on_fail: "raise".to_string(),
        policies: vec!["pii:redact".to_string(), "profanity:block".to_string()],
    });
    
    presets.insert("lenient", GuardrailPreset {
        enabled: true,
        max_retries: 5,
        on_fail: "skip".to_string(),
        policies: vec![],
    });
    
    presets.insert("pii_safe", GuardrailPreset {
        enabled: true,
        max_retries: 3,
        on_fail: "retry".to_string(),
        policies: vec!["pii:redact".to_string(), "ssn:block".to_string(), "credit_card:block".to_string()],
    });
    
    presets.insert("content_safe", GuardrailPreset {
        enabled: true,
        max_retries: 3,
        on_fail: "retry".to_string(),
        policies: vec!["profanity:block".to_string(), "harmful:block".to_string()],
    });
    
    presets.insert("disabled", GuardrailPreset {
        enabled: false,
        max_retries: 0,
        on_fail: "skip".to_string(),
        policies: vec![],
    });
    
    presets
});

/// Resolve a guardrail preset by name
pub fn resolve_guardrail_preset(name: &str) -> Option<GuardrailPreset> {
    GUARDRAIL_PRESETS.get(name).cloned()
}

// =============================================================================
// CONTEXT PRESETS
// =============================================================================

/// Context preset configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextPreset {
    /// Maximum context tokens
    pub max_tokens: usize,
    /// Context window strategy
    pub strategy: String,
    /// Include system prompt in context
    pub include_system: bool,
    /// Include tool results in context
    pub include_tools: bool,
}

impl Default for ContextPreset {
    fn default() -> Self {
        Self {
            max_tokens: 8000,
            strategy: "sliding_window".to_string(),
            include_system: true,
            include_tools: true,
        }
    }
}

/// Context presets matching Python SDK
pub static CONTEXT_PRESETS: Lazy<HashMap<&'static str, ContextPreset>> = Lazy::new(|| {
    let mut presets = HashMap::new();
    
    presets.insert("default", ContextPreset::default());
    
    presets.insert("small", ContextPreset {
        max_tokens: 4000,
        strategy: "sliding_window".to_string(),
        include_system: true,
        include_tools: false,
    });
    
    presets.insert("large", ContextPreset {
        max_tokens: 16000,
        strategy: "sliding_window".to_string(),
        include_system: true,
        include_tools: true,
    });
    
    presets.insert("unlimited", ContextPreset {
        max_tokens: 128000,
        strategy: "full".to_string(),
        include_system: true,
        include_tools: true,
    });
    
    presets.insert("minimal", ContextPreset {
        max_tokens: 2000,
        strategy: "truncate".to_string(),
        include_system: true,
        include_tools: false,
    });
    
    presets
});

/// Resolve a context preset by name
pub fn resolve_context_preset(name: &str) -> Option<ContextPreset> {
    CONTEXT_PRESETS.get(name).cloned()
}

// =============================================================================
// AUTONOMY PRESETS
// =============================================================================

/// Autonomy preset configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AutonomyPreset {
    /// Autonomy level
    pub level: String,
    /// Require approval for destructive actions
    pub require_approval: bool,
    /// Maximum autonomous actions
    pub max_actions: Option<usize>,
}

impl Default for AutonomyPreset {
    fn default() -> Self {
        Self {
            level: "suggest".to_string(),
            require_approval: true,
            max_actions: None,
        }
    }
}

/// Autonomy presets matching Python SDK
pub static AUTONOMY_PRESETS: Lazy<HashMap<&'static str, AutonomyPreset>> = Lazy::new(|| {
    let mut presets = HashMap::new();
    
    presets.insert("suggest", AutonomyPreset {
        level: "suggest".to_string(),
        require_approval: true,
        max_actions: None,
    });
    
    presets.insert("auto_edit", AutonomyPreset {
        level: "auto_edit".to_string(),
        require_approval: true,
        max_actions: Some(10),
    });
    
    presets.insert("full_auto", AutonomyPreset {
        level: "full_auto".to_string(),
        require_approval: false,
        max_actions: None,
    });
    
    presets.insert("safe", AutonomyPreset {
        level: "suggest".to_string(),
        require_approval: true,
        max_actions: Some(5),
    });
    
    presets
});

/// Resolve an autonomy preset by name
pub fn resolve_autonomy_preset(name: &str) -> Option<AutonomyPreset> {
    AUTONOMY_PRESETS.get(name).cloned()
}

// =============================================================================
// CACHING PRESETS
// =============================================================================

/// Caching preset configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CachingPreset {
    /// Enable caching
    pub enabled: bool,
    /// Enable prompt caching
    pub prompt_caching: bool,
    /// Cache TTL in seconds
    pub ttl_secs: Option<u64>,
}

impl Default for CachingPreset {
    fn default() -> Self {
        Self {
            enabled: true,
            prompt_caching: false,
            ttl_secs: None,
        }
    }
}

/// Caching presets matching Python SDK
pub static CACHING_PRESETS: Lazy<HashMap<&'static str, CachingPreset>> = Lazy::new(|| {
    let mut presets = HashMap::new();
    
    presets.insert("default", CachingPreset::default());
    
    presets.insert("aggressive", CachingPreset {
        enabled: true,
        prompt_caching: true,
        ttl_secs: Some(3600),
    });
    
    presets.insert("minimal", CachingPreset {
        enabled: true,
        prompt_caching: false,
        ttl_secs: Some(300),
    });
    
    presets.insert("disabled", CachingPreset {
        enabled: false,
        prompt_caching: false,
        ttl_secs: None,
    });
    
    presets
});

/// Resolve a caching preset by name
pub fn resolve_caching_preset(name: &str) -> Option<CachingPreset> {
    CACHING_PRESETS.get(name).cloned()
}

// =============================================================================
// MULTI-AGENT OUTPUT PRESETS
// =============================================================================

/// Multi-agent output preset configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MultiAgentOutputPreset {
    /// Verbosity level
    pub verbose: u8,
    /// Enable streaming
    pub stream: bool,
}

impl Default for MultiAgentOutputPreset {
    fn default() -> Self {
        Self {
            verbose: 1,
            stream: true,
        }
    }
}

/// Multi-agent output presets matching Python SDK
pub static MULTI_AGENT_OUTPUT_PRESETS: Lazy<HashMap<&'static str, MultiAgentOutputPreset>> = Lazy::new(|| {
    let mut presets = HashMap::new();
    
    presets.insert("default", MultiAgentOutputPreset::default());
    
    presets.insert("silent", MultiAgentOutputPreset {
        verbose: 0,
        stream: false,
    });
    
    presets.insert("verbose", MultiAgentOutputPreset {
        verbose: 2,
        stream: true,
    });
    
    presets.insert("debug", MultiAgentOutputPreset {
        verbose: 3,
        stream: true,
    });
    
    presets
});

/// Resolve a multi-agent output preset by name
pub fn resolve_multi_agent_output_preset(name: &str) -> Option<MultiAgentOutputPreset> {
    MULTI_AGENT_OUTPUT_PRESETS.get(name).cloned()
}

// =============================================================================
// MULTI-AGENT EXECUTION PRESETS
// =============================================================================

/// Multi-agent execution preset configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MultiAgentExecutionPreset {
    /// Maximum iterations
    pub max_iter: usize,
    /// Maximum retries
    pub max_retries: usize,
}

impl Default for MultiAgentExecutionPreset {
    fn default() -> Self {
        Self {
            max_iter: 10,
            max_retries: 5,
        }
    }
}

/// Multi-agent execution presets matching Python SDK
pub static MULTI_AGENT_EXECUTION_PRESETS: Lazy<HashMap<&'static str, MultiAgentExecutionPreset>> = Lazy::new(|| {
    let mut presets = HashMap::new();
    
    presets.insert("default", MultiAgentExecutionPreset::default());
    
    presets.insert("fast", MultiAgentExecutionPreset {
        max_iter: 5,
        max_retries: 2,
    });
    
    presets.insert("thorough", MultiAgentExecutionPreset {
        max_iter: 20,
        max_retries: 10,
    });
    
    presets
});

/// Resolve a multi-agent execution preset by name
pub fn resolve_multi_agent_execution_preset(name: &str) -> Option<MultiAgentExecutionPreset> {
    MULTI_AGENT_EXECUTION_PRESETS.get(name).cloned()
}

// =============================================================================
// WORKFLOW STEP EXECUTION PRESETS
// =============================================================================

/// Workflow step execution preset configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkflowStepExecutionPreset {
    /// Maximum iterations per step
    pub max_iter: usize,
    /// Maximum retries per step
    pub max_retries: usize,
    /// Timeout per step in seconds
    pub timeout_secs: u64,
}

impl Default for WorkflowStepExecutionPreset {
    fn default() -> Self {
        Self {
            max_iter: 10,
            max_retries: 3,
            timeout_secs: 300,
        }
    }
}

/// Workflow step execution presets matching Python SDK
pub static WORKFLOW_STEP_EXECUTION_PRESETS: Lazy<HashMap<&'static str, WorkflowStepExecutionPreset>> = Lazy::new(|| {
    let mut presets = HashMap::new();
    
    presets.insert("default", WorkflowStepExecutionPreset::default());
    
    presets.insert("fast", WorkflowStepExecutionPreset {
        max_iter: 5,
        max_retries: 1,
        timeout_secs: 60,
    });
    
    presets.insert("thorough", WorkflowStepExecutionPreset {
        max_iter: 20,
        max_retries: 5,
        timeout_secs: 600,
    });
    
    presets
});

/// Resolve a workflow step execution preset by name
pub fn resolve_workflow_step_execution_preset(name: &str) -> Option<WorkflowStepExecutionPreset> {
    WORKFLOW_STEP_EXECUTION_PRESETS.get(name).cloned()
}

// =============================================================================
// KNOWLEDGE PRESETS
// =============================================================================

/// Knowledge preset configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KnowledgePreset {
    /// Embedder model
    pub embedder: String,
    /// Chunking strategy
    pub chunking_strategy: String,
    /// Chunk size
    pub chunk_size: usize,
    /// Chunk overlap
    pub chunk_overlap: usize,
    /// Retrieval k
    pub retrieval_k: usize,
    /// Enable reranking
    pub rerank: bool,
}

impl Default for KnowledgePreset {
    fn default() -> Self {
        Self {
            embedder: "openai".to_string(),
            chunking_strategy: "semantic".to_string(),
            chunk_size: 1000,
            chunk_overlap: 200,
            retrieval_k: 5,
            rerank: false,
        }
    }
}

/// Knowledge presets matching Python SDK
pub static KNOWLEDGE_PRESETS: Lazy<HashMap<&'static str, KnowledgePreset>> = Lazy::new(|| {
    let mut presets = HashMap::new();
    
    presets.insert("default", KnowledgePreset::default());
    
    presets.insert("fast", KnowledgePreset {
        embedder: "openai".to_string(),
        chunking_strategy: "fixed".to_string(),
        chunk_size: 500,
        chunk_overlap: 50,
        retrieval_k: 3,
        rerank: false,
    });
    
    presets.insert("accurate", KnowledgePreset {
        embedder: "openai".to_string(),
        chunking_strategy: "semantic".to_string(),
        chunk_size: 1000,
        chunk_overlap: 200,
        retrieval_k: 10,
        rerank: true,
    });
    
    presets.insert("large_docs", KnowledgePreset {
        embedder: "openai".to_string(),
        chunking_strategy: "paragraph".to_string(),
        chunk_size: 2000,
        chunk_overlap: 400,
        retrieval_k: 5,
        rerank: true,
    });
    
    presets
});

/// Resolve a knowledge preset by name
pub fn resolve_knowledge_preset(name: &str) -> Option<KnowledgePreset> {
    KNOWLEDGE_PRESETS.get(name).cloned()
}

// =============================================================================
// TESTS
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_memory_presets() {
        assert!(MEMORY_PRESETS.contains_key("sqlite"));
        assert!(MEMORY_PRESETS.contains_key("chroma"));
        assert!(MEMORY_PRESETS.contains_key("memory"));
        
        let preset = resolve_memory_preset("sqlite").unwrap();
        assert_eq!(preset.backend, "sqlite");
    }

    #[test]
    fn test_memory_url_schemes() {
        assert_eq!(detect_memory_backend("sqlite:///path/to/db"), Some("sqlite"));
        assert_eq!(detect_memory_backend("postgres://localhost/db"), Some("postgres"));
        assert_eq!(detect_memory_backend("redis://localhost:6379"), Some("redis"));
        assert_eq!(detect_memory_backend("unknown://host"), None);
    }

    #[test]
    fn test_output_presets() {
        assert!(OUTPUT_PRESETS.contains_key("silent"));
        assert!(OUTPUT_PRESETS.contains_key("verbose"));
        
        let preset = resolve_output_preset("silent").unwrap();
        assert!(!preset.verbose);
        assert!(!preset.stream);
    }

    #[test]
    fn test_execution_presets() {
        let preset = resolve_execution_preset("fast").unwrap();
        assert_eq!(preset.max_iter, 5);
        assert_eq!(preset.timeout_secs, 60);
    }

    #[test]
    fn test_web_presets() {
        let preset = resolve_web_preset("tavily").unwrap();
        assert_eq!(preset.provider, "tavily");
        assert!(preset.search);
    }

    #[test]
    fn test_planning_presets() {
        let preset = resolve_planning_preset("read_only").unwrap();
        assert!(preset.read_only);
        assert!(preset.enabled);
    }

    #[test]
    fn test_reflection_presets() {
        let preset = resolve_reflection_preset("thorough").unwrap();
        assert_eq!(preset.max_iterations, 5);
    }

    #[test]
    fn test_guardrail_presets() {
        let preset = resolve_guardrail_preset("strict").unwrap();
        assert_eq!(preset.on_fail, "raise");
        assert!(!preset.policies.is_empty());
    }

    #[test]
    fn test_context_presets() {
        let preset = resolve_context_preset("large").unwrap();
        assert_eq!(preset.max_tokens, 16000);
    }

    #[test]
    fn test_autonomy_presets() {
        let preset = resolve_autonomy_preset("full_auto").unwrap();
        assert_eq!(preset.level, "full_auto");
        assert!(!preset.require_approval);
    }

    #[test]
    fn test_caching_presets() {
        let preset = resolve_caching_preset("aggressive").unwrap();
        assert!(preset.prompt_caching);
        assert_eq!(preset.ttl_secs, Some(3600));
    }

    #[test]
    fn test_multi_agent_output_presets() {
        let preset = resolve_multi_agent_output_preset("debug").unwrap();
        assert_eq!(preset.verbose, 3);
    }

    #[test]
    fn test_multi_agent_execution_presets() {
        let preset = resolve_multi_agent_execution_preset("thorough").unwrap();
        assert_eq!(preset.max_iter, 20);
    }

    #[test]
    fn test_workflow_step_execution_presets() {
        let preset = resolve_workflow_step_execution_preset("fast").unwrap();
        assert_eq!(preset.timeout_secs, 60);
    }

    #[test]
    fn test_knowledge_presets() {
        let preset = resolve_knowledge_preset("accurate").unwrap();
        assert!(preset.rerank);
        assert_eq!(preset.retrieval_k, 10);
    }
}
