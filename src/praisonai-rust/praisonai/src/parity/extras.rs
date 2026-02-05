//! Extra parity types and functions
//!
//! This module implements additional Python SDK features for full parity:
//! - Deep Research types (DeepResearchResponse, ReasoningStep, etc.)
//! - RAG types (RAGCitation, RetrievalPolicy, etc.)
//! - Guardrail types (LLMGuardrail)
//! - Handoff errors
//! - App protocols
//! - Embedding functions
//! - Module re-exports

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::{Arc, RwLock};

// =============================================================================
// Deep Research Types
// =============================================================================

/// Represents a citation in the research report
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Citation {
    /// Title of the source
    pub title: String,
    /// URL of the source
    pub url: String,
    /// Start index in the report text
    #[serde(default)]
    pub start_index: usize,
    /// End index in the report text
    #[serde(default)]
    pub end_index: usize,
}

impl Citation {
    /// Create a new citation
    pub fn new(title: impl Into<String>, url: impl Into<String>) -> Self {
        Self {
            title: title.into(),
            url: url.into(),
            start_index: 0,
            end_index: 0,
        }
    }
}

/// Represents a reasoning step in the research process
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReasoningStep {
    /// The reasoning text
    pub text: String,
    /// Type of reasoning step
    #[serde(default = "default_reasoning_type")]
    pub step_type: String,
}

fn default_reasoning_type() -> String {
    "reasoning".to_string()
}

impl ReasoningStep {
    /// Create a new reasoning step
    pub fn new(text: impl Into<String>) -> Self {
        Self {
            text: text.into(),
            step_type: "reasoning".to_string(),
        }
    }
}

/// Represents a web search call made during research
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WebSearchCall {
    /// The search query
    pub query: String,
    /// Status of the search
    pub status: String,
}

impl WebSearchCall {
    /// Create a new web search call
    pub fn new(query: impl Into<String>, status: impl Into<String>) -> Self {
        Self {
            query: query.into(),
            status: status.into(),
        }
    }
}

/// Represents a code execution step during research
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CodeExecutionStep {
    /// The input code
    pub input_code: String,
    /// The output (if any)
    pub output: Option<String>,
}

impl CodeExecutionStep {
    /// Create a new code execution step
    pub fn new(input_code: impl Into<String>) -> Self {
        Self {
            input_code: input_code.into(),
            output: None,
        }
    }
    
    /// Create with output
    pub fn with_output(input_code: impl Into<String>, output: impl Into<String>) -> Self {
        Self {
            input_code: input_code.into(),
            output: Some(output.into()),
        }
    }
}

/// Represents a file search call (Gemini-specific)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileSearchCall {
    /// Store names to search
    pub store_names: Vec<String>,
}

impl FileSearchCall {
    /// Create a new file search call
    pub fn new(store_names: Vec<String>) -> Self {
        Self { store_names }
    }
}

/// Supported Deep Research providers
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Provider {
    /// OpenAI Deep Research
    OpenAI,
    /// Gemini Deep Research
    Gemini,
    /// LiteLLM unified interface
    LiteLLM,
}

impl Default for Provider {
    fn default() -> Self {
        Self::OpenAI
    }
}

impl std::fmt::Display for Provider {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::OpenAI => write!(f, "openai"),
            Self::Gemini => write!(f, "gemini"),
            Self::LiteLLM => write!(f, "litellm"),
        }
    }
}

/// Complete response from a Deep Research query
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeepResearchResponse {
    /// The final research report text
    pub report: String,
    /// List of citations with source metadata
    #[serde(default)]
    pub citations: Vec<Citation>,
    /// List of reasoning steps taken
    #[serde(default)]
    pub reasoning_steps: Vec<ReasoningStep>,
    /// List of web search queries executed
    #[serde(default)]
    pub web_searches: Vec<WebSearchCall>,
    /// List of code execution steps
    #[serde(default)]
    pub code_executions: Vec<CodeExecutionStep>,
    /// List of file search calls (Gemini)
    #[serde(default)]
    pub file_searches: Vec<FileSearchCall>,
    /// The provider used
    #[serde(default)]
    pub provider: Provider,
    /// Interaction ID (Gemini) or Response ID (OpenAI)
    pub interaction_id: Option<String>,
}

impl DeepResearchResponse {
    /// Create a new deep research response
    pub fn new(report: impl Into<String>) -> Self {
        Self {
            report: report.into(),
            citations: Vec::new(),
            reasoning_steps: Vec::new(),
            web_searches: Vec::new(),
            code_executions: Vec::new(),
            file_searches: Vec::new(),
            provider: Provider::default(),
            interaction_id: None,
        }
    }
    
    /// Extract the text that a citation refers to
    pub fn get_citation_text(&self, citation: &Citation) -> &str {
        if citation.start_index < citation.end_index && citation.end_index <= self.report.len() {
            &self.report[citation.start_index..citation.end_index]
        } else {
            ""
        }
    }
    
    /// Get a list of all unique sources cited
    pub fn get_all_sources(&self) -> Vec<HashMap<String, String>> {
        let mut seen = std::collections::HashSet::new();
        let mut sources = Vec::new();
        
        for c in &self.citations {
            if !seen.contains(&c.url) {
                seen.insert(c.url.clone());
                let mut source = HashMap::new();
                source.insert("title".to_string(), c.title.clone());
                source.insert("url".to_string(), c.url.clone());
                sources.push(source);
            }
        }
        
        sources
    }
}

// =============================================================================
// RAG Types
// =============================================================================

/// RAG citation (alias for Citation)
pub type RAGCitation = Citation;

/// Retrieval policy for RAG
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum RetrievalPolicy {
    /// Always retrieve context
    #[default]
    Always,
    /// Never retrieve context
    Never,
    /// Retrieve only when needed
    OnDemand,
    /// Retrieve based on similarity threshold
    Threshold,
}

/// RAG retrieval policy (alias)
pub type RagRetrievalPolicy = RetrievalPolicy;

// =============================================================================
// Guardrail Types
// =============================================================================

/// LLM-based guardrail for content validation
#[derive(Debug, Clone)]
pub struct LLMGuardrail {
    /// Name of the guardrail
    pub name: String,
    /// Description of what the guardrail checks
    pub description: String,
    /// The prompt template for the LLM check
    pub prompt_template: String,
    /// Model to use for the guardrail check
    pub model: String,
    /// Whether to block on failure
    pub block_on_failure: bool,
}

impl LLMGuardrail {
    /// Create a new LLM guardrail
    pub fn new(name: impl Into<String>, description: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            description: description.into(),
            prompt_template: String::new(),
            model: "gpt-4o-mini".to_string(),
            block_on_failure: true,
        }
    }
    
    /// Set the prompt template
    pub fn with_prompt(mut self, prompt: impl Into<String>) -> Self {
        self.prompt_template = prompt.into();
        self
    }
    
    /// Set the model
    pub fn with_model(mut self, model: impl Into<String>) -> Self {
        self.model = model.into();
        self
    }
    
    /// Set whether to block on failure
    pub fn block_on_failure(mut self, block: bool) -> Self {
        self.block_on_failure = block;
        self
    }
}

// =============================================================================
// Handoff Errors
// =============================================================================

/// Base error type for handoff operations
#[derive(Debug, Clone, thiserror::Error)]
pub enum HandoffError {
    /// Cycle detected in handoff chain
    #[error("Handoff cycle detected: {agents:?}")]
    Cycle { agents: Vec<String> },
    
    /// Maximum handoff depth exceeded
    #[error("Maximum handoff depth {max_depth} exceeded")]
    DepthExceeded { max_depth: usize },
    
    /// Handoff timeout
    #[error("Handoff timed out after {timeout_ms}ms")]
    Timeout { timeout_ms: u64 },
    
    /// Agent not found
    #[error("Agent not found: {name}")]
    AgentNotFound { name: String },
    
    /// Invalid handoff configuration
    #[error("Invalid handoff configuration: {message}")]
    InvalidConfig { message: String },
}

/// Handoff cycle error (convenience type)
pub type HandoffCycleError = HandoffError;

/// Handoff depth error (convenience type)
pub type HandoffDepthError = HandoffError;

/// Handoff timeout error (convenience type)
pub type HandoffTimeoutError = HandoffError;

// =============================================================================
// App Protocols
// =============================================================================

/// Agent application protocol
pub trait AgentAppProtocol: Send + Sync {
    /// Get the app name
    fn name(&self) -> &str;
    
    /// Get the app version
    fn version(&self) -> &str;
    
    /// Start the application
    fn start(&self) -> crate::error::Result<()>;
    
    /// Stop the application
    fn stop(&self) -> crate::error::Result<()>;
}

/// Agent OS protocol (alias)
pub trait AgentOSProtocol: AgentAppProtocol {}

/// Agent application configuration
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct AgentAppConfig {
    /// Application name
    pub name: String,
    /// Application version
    pub version: String,
    /// Host to bind to
    pub host: String,
    /// Port to bind to
    pub port: u16,
    /// Enable debug mode
    pub debug: bool,
}

impl AgentAppConfig {
    /// Create a new app config
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            version: "1.0.0".to_string(),
            host: "127.0.0.1".to_string(),
            port: 8000,
            debug: false,
        }
    }
}

// =============================================================================
// Sandbox Types
// =============================================================================

/// Security policy for sandbox execution
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct SecurityPolicy {
    /// Allow network access
    pub allow_network: bool,
    /// Allow file system access
    pub allow_filesystem: bool,
    /// Allow subprocess execution
    pub allow_subprocess: bool,
    /// Allowed domains for network access
    pub allowed_domains: Vec<String>,
    /// Allowed paths for filesystem access
    pub allowed_paths: Vec<String>,
    /// Maximum execution time in seconds
    pub max_execution_time: u64,
    /// Maximum memory in bytes
    pub max_memory: u64,
}

impl SecurityPolicy {
    /// Create a restrictive security policy
    pub fn restrictive() -> Self {
        Self {
            allow_network: false,
            allow_filesystem: false,
            allow_subprocess: false,
            allowed_domains: Vec::new(),
            allowed_paths: Vec::new(),
            max_execution_time: 30,
            max_memory: 256 * 1024 * 1024, // 256MB
        }
    }
    
    /// Create a permissive security policy
    pub fn permissive() -> Self {
        Self {
            allow_network: true,
            allow_filesystem: true,
            allow_subprocess: true,
            allowed_domains: Vec::new(),
            allowed_paths: Vec::new(),
            max_execution_time: 300,
            max_memory: 1024 * 1024 * 1024, // 1GB
        }
    }
}

// =============================================================================
// Reflection Types
// =============================================================================

/// Output from a reflection step
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReflectionOutput {
    /// The original output
    pub original: String,
    /// The reflection analysis
    pub reflection: String,
    /// The improved output (if any)
    pub improved: Option<String>,
    /// Confidence score (0.0 - 1.0)
    pub confidence: f64,
    /// Whether the output was modified
    pub was_modified: bool,
}

impl ReflectionOutput {
    /// Create a new reflection output
    pub fn new(original: impl Into<String>, reflection: impl Into<String>) -> Self {
        Self {
            original: original.into(),
            reflection: reflection.into(),
            improved: None,
            confidence: 1.0,
            was_modified: false,
        }
    }
    
    /// Create with improved output
    pub fn with_improvement(
        original: impl Into<String>,
        reflection: impl Into<String>,
        improved: impl Into<String>,
    ) -> Self {
        Self {
            original: original.into(),
            reflection: reflection.into(),
            improved: Some(improved.into()),
            confidence: 1.0,
            was_modified: true,
        }
    }
}

// =============================================================================
// Embedding Functions
// =============================================================================

/// Embedding result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EmbeddingResult {
    /// The embedding vector
    pub embedding: Vec<f32>,
    /// The model used
    pub model: String,
    /// Token usage
    pub usage: Option<EmbeddingUsage>,
}

/// Embedding usage statistics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EmbeddingUsage {
    /// Prompt tokens
    pub prompt_tokens: u32,
    /// Total tokens
    pub total_tokens: u32,
}

/// Synchronous embedding function
pub fn embed(text: &str, model: Option<&str>) -> crate::error::Result<Vec<f32>> {
    // Placeholder - actual implementation would call embedding API
    let _model = model.unwrap_or("text-embedding-3-small");
    // Return dummy embedding for now
    Ok(vec![0.0; 1536])
}

/// Synchronous embedding function (alias)
pub fn embedding(text: &str, model: Option<&str>) -> crate::error::Result<Vec<f32>> {
    embed(text, model)
}

/// Synchronous embeddings function (batch)
pub fn embeddings(texts: &[&str], model: Option<&str>) -> crate::error::Result<Vec<Vec<f32>>> {
    texts.iter().map(|t| embed(t, model)).collect()
}

/// Async embedding function
pub async fn aembed(text: &str, model: Option<&str>) -> crate::error::Result<Vec<f32>> {
    embed(text, model)
}

/// Async embedding function (alias)
pub async fn aembedding(text: &str, model: Option<&str>) -> crate::error::Result<Vec<f32>> {
    aembed(text, model).await
}

/// Async embeddings function (batch)
pub async fn aembeddings(texts: &[&str], model: Option<&str>) -> crate::error::Result<Vec<Vec<f32>>> {
    let mut results = Vec::with_capacity(texts.len());
    for text in texts {
        results.push(aembed(text, model).await?);
    }
    Ok(results)
}

// =============================================================================
// Display Callbacks
// =============================================================================

lazy_static::lazy_static! {
    /// Global sync display callbacks
    static ref SYNC_DISPLAY_CALLBACKS: RwLock<Vec<Arc<dyn Fn(&str) + Send + Sync>>> = RwLock::new(Vec::new());
    
    /// Global async display callbacks
    static ref ASYNC_DISPLAY_CALLBACKS: RwLock<Vec<Arc<dyn Fn(&str) + Send + Sync>>> = RwLock::new(Vec::new());
    
    /// Global error logs
    static ref ERROR_LOGS: RwLock<Vec<String>> = RwLock::new(Vec::new());
}

/// Get sync display callbacks
pub fn sync_display_callbacks() -> Vec<Arc<dyn Fn(&str) + Send + Sync>> {
    SYNC_DISPLAY_CALLBACKS.read().unwrap().clone()
}

/// Get async display callbacks
pub fn async_display_callbacks() -> Vec<Arc<dyn Fn(&str) + Send + Sync>> {
    ASYNC_DISPLAY_CALLBACKS.read().unwrap().clone()
}

/// Get error logs
pub fn error_logs() -> Vec<String> {
    ERROR_LOGS.read().unwrap().clone()
}

// =============================================================================
// Presets
// =============================================================================

lazy_static::lazy_static! {
    /// Autonomy presets
    pub static ref AUTONOMY_PRESETS: HashMap<String, HashMap<String, serde_json::Value>> = {
        let mut presets = HashMap::new();
        
        // Full autonomy preset
        let mut full = HashMap::new();
        full.insert("level".to_string(), serde_json::json!("full"));
        full.insert("require_approval".to_string(), serde_json::json!(false));
        full.insert("max_iterations".to_string(), serde_json::json!(100));
        presets.insert("full".to_string(), full);
        
        // Supervised preset
        let mut supervised = HashMap::new();
        supervised.insert("level".to_string(), serde_json::json!("supervised"));
        supervised.insert("require_approval".to_string(), serde_json::json!(true));
        supervised.insert("max_iterations".to_string(), serde_json::json!(10));
        presets.insert("supervised".to_string(), supervised);
        
        // Minimal preset
        let mut minimal = HashMap::new();
        minimal.insert("level".to_string(), serde_json::json!("minimal"));
        minimal.insert("require_approval".to_string(), serde_json::json!(true));
        minimal.insert("max_iterations".to_string(), serde_json::json!(1));
        presets.insert("minimal".to_string(), minimal);
        
        presets
    };
}

/// Recommended prompt prefix for handoff instructions
pub const RECOMMENDED_PROMPT_PREFIX: &str = r#"You are a helpful assistant that can hand off tasks to other specialized agents.

When you need to hand off a task:
1. Clearly state which agent you're handing off to
2. Provide all relevant context
3. Specify what you expect back

"#;

// =============================================================================
// Resolver Functions
// =============================================================================

/// Resolve guardrail policies
pub fn resolve_guardrail_policies(
    policies: Option<&[&str]>,
    config: Option<&serde_json::Value>,
) -> Vec<String> {
    if let Some(p) = policies {
        return p.iter().map(|s| s.to_string()).collect();
    }
    
    if let Some(c) = config {
        if let Some(arr) = c.get("guardrail_policies").and_then(|v| v.as_array()) {
            return arr
                .iter()
                .filter_map(|v| v.as_str().map(String::from))
                .collect();
        }
    }
    
    Vec::new()
}

// =============================================================================
// Trace Functions
// =============================================================================

/// Trace context for tracking operations
#[derive(Debug, Clone)]
pub struct TraceContextData {
    /// Trace ID
    pub trace_id: String,
    /// Span ID
    pub span_id: String,
    /// Parent span ID
    pub parent_span_id: Option<String>,
    /// Attributes
    pub attributes: HashMap<String, serde_json::Value>,
}

impl TraceContextData {
    /// Create a new trace context
    pub fn new() -> Self {
        Self {
            trace_id: uuid::Uuid::new_v4().to_string(),
            span_id: uuid::Uuid::new_v4().to_string(),
            parent_span_id: None,
            attributes: HashMap::new(),
        }
    }
}

impl Default for TraceContextData {
    fn default() -> Self {
        Self::new()
    }
}

/// Get or create trace context
pub fn trace_context() -> TraceContextData {
    TraceContextData::new()
}

/// Track workflow execution
pub fn track_workflow(name: &str, _context: Option<&TraceContextData>) -> TraceContextData {
    let mut ctx = TraceContextData::new();
    ctx.attributes.insert("workflow_name".to_string(), serde_json::json!(name));
    ctx
}

// =============================================================================
// Plugin Functions
// =============================================================================

/// Load a plugin from a path
pub fn load_plugin(path: &str) -> crate::error::Result<()> {
    // Placeholder - actual implementation would load plugin
    tracing::info!("Loading plugin from: {}", path);
    Ok(())
}

// =============================================================================
// Module Re-exports (for parity with Python's module access)
// =============================================================================

/// Config module placeholder
pub mod config {
    pub use super::super::config_loader::*;
    pub use super::super::param_resolver::*;
}

/// Memory module placeholder
pub mod memory {
    // Re-export memory types from main crate
}

/// Tools module placeholder
pub mod tools {
    // Re-export tool types from main crate
}

/// Workflows module placeholder
pub mod workflows {
    pub use super::super::workflow_aliases::*;
}

/// DB module placeholder
pub mod db {
    /// Database adapter trait
    pub trait DbAdapter: Send + Sync {
        /// Store a value
        fn store(&self, key: &str, value: &serde_json::Value) -> crate::error::Result<()>;
        /// Retrieve a value
        fn get(&self, key: &str) -> crate::error::Result<Option<serde_json::Value>>;
        /// Delete a value
        fn delete(&self, key: &str) -> crate::error::Result<()>;
    }
}

/// Observability module placeholder
pub mod obs {
    /// Observability collector trait
    pub trait ObsCollector: Send + Sync {
        /// Record an event
        fn record(&self, event: &str, data: &serde_json::Value);
        /// Flush pending events
        fn flush(&self);
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_citation() {
        let citation = Citation::new("Test Title", "https://example.com");
        assert_eq!(citation.title, "Test Title");
        assert_eq!(citation.url, "https://example.com");
    }
    
    #[test]
    fn test_reasoning_step() {
        let step = ReasoningStep::new("This is a reasoning step");
        assert_eq!(step.step_type, "reasoning");
    }
    
    #[test]
    fn test_web_search_call() {
        let call = WebSearchCall::new("test query", "completed");
        assert_eq!(call.query, "test query");
        assert_eq!(call.status, "completed");
    }
    
    #[test]
    fn test_code_execution_step() {
        let step = CodeExecutionStep::new("print('hello')");
        assert!(step.output.is_none());
        
        let step_with_output = CodeExecutionStep::with_output("print('hello')", "hello");
        assert_eq!(step_with_output.output, Some("hello".to_string()));
    }
    
    #[test]
    fn test_provider() {
        assert_eq!(Provider::default(), Provider::OpenAI);
        assert_eq!(format!("{}", Provider::Gemini), "gemini");
    }
    
    #[test]
    fn test_deep_research_response() {
        let mut response = DeepResearchResponse::new("Test report content");
        response.citations.push(Citation {
            title: "Source".to_string(),
            url: "https://example.com".to_string(),
            start_index: 0,
            end_index: 4,
        });
        
        let text = response.get_citation_text(&response.citations[0]);
        assert_eq!(text, "Test");
        
        let sources = response.get_all_sources();
        assert_eq!(sources.len(), 1);
    }
    
    #[test]
    fn test_retrieval_policy() {
        assert_eq!(RetrievalPolicy::default(), RetrievalPolicy::Always);
    }
    
    #[test]
    fn test_llm_guardrail() {
        let guardrail = LLMGuardrail::new("content_filter", "Filters inappropriate content")
            .with_model("gpt-4o")
            .block_on_failure(true);
        
        assert_eq!(guardrail.name, "content_filter");
        assert_eq!(guardrail.model, "gpt-4o");
        assert!(guardrail.block_on_failure);
    }
    
    #[test]
    fn test_handoff_error() {
        let err = HandoffError::Cycle { agents: vec!["a".to_string(), "b".to_string()] };
        assert!(err.to_string().contains("cycle"));
        
        let err = HandoffError::DepthExceeded { max_depth: 10 };
        assert!(err.to_string().contains("10"));
    }
    
    #[test]
    fn test_agent_app_config() {
        let config = AgentAppConfig::new("test_app");
        assert_eq!(config.name, "test_app");
        assert_eq!(config.port, 8000);
    }
    
    #[test]
    fn test_security_policy() {
        let restrictive = SecurityPolicy::restrictive();
        assert!(!restrictive.allow_network);
        
        let permissive = SecurityPolicy::permissive();
        assert!(permissive.allow_network);
    }
    
    #[test]
    fn test_reflection_output() {
        let output = ReflectionOutput::new("original", "reflection");
        assert!(!output.was_modified);
        
        let improved = ReflectionOutput::with_improvement("original", "reflection", "improved");
        assert!(improved.was_modified);
    }
    
    #[test]
    fn test_embed() {
        let result = embed("test", None);
        assert!(result.is_ok());
        assert_eq!(result.unwrap().len(), 1536);
    }
    
    #[test]
    fn test_autonomy_presets() {
        assert!(AUTONOMY_PRESETS.contains_key("full"));
        assert!(AUTONOMY_PRESETS.contains_key("supervised"));
        assert!(AUTONOMY_PRESETS.contains_key("minimal"));
    }
    
    #[test]
    fn test_recommended_prompt_prefix() {
        assert!(RECOMMENDED_PROMPT_PREFIX.contains("hand off"));
    }
    
    #[test]
    fn test_resolve_guardrail_policies() {
        let policies = resolve_guardrail_policies(Some(&["policy1", "policy2"]), None);
        assert_eq!(policies.len(), 2);
        
        let empty = resolve_guardrail_policies(None, None);
        assert!(empty.is_empty());
    }
    
    #[test]
    fn test_trace_context() {
        let ctx = trace_context();
        assert!(!ctx.trace_id.is_empty());
        assert!(!ctx.span_id.is_empty());
    }
    
    #[test]
    fn test_track_workflow() {
        let ctx = track_workflow("test_workflow", None);
        assert!(ctx.attributes.contains_key("workflow_name"));
    }
}
