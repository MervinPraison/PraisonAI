//! Configuration types for PraisonAI
//!
//! This module provides configuration structs for various features.
//! Follows the Python SDK pattern of XConfig naming convention.
//!
//! # Feature Configurations
//!
//! - [`MemoryConfig`]: Memory and session management
//! - [`KnowledgeConfig`]: RAG and knowledge retrieval
//! - [`PlanningConfig`]: Planning mode settings
//! - [`ReflectionConfig`]: Self-reflection settings
//! - [`GuardrailConfig`]: Safety and validation
//! - [`WebConfig`]: Web search and fetch
//! - [`CachingConfig`]: Response caching
//! - [`AutonomyConfig`]: Agent autonomy levels
//!
//! All configs follow the agent-centric pattern:
//! - `false`: Feature disabled (zero overhead)
//! - `true`: Feature enabled with safe defaults
//! - `Config`: Custom configuration

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Memory configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryConfig {
    /// Enable short-term memory (conversation history)
    #[serde(default = "default_true")]
    pub use_short_term: bool,

    /// Enable long-term memory (persistent storage)
    #[serde(default)]
    pub use_long_term: bool,

    /// Memory provider (e.g., "memory", "chroma", "sqlite")
    #[serde(default = "default_memory_provider")]
    pub provider: String,

    /// Maximum number of messages to keep in short-term memory
    #[serde(default = "default_max_messages")]
    pub max_messages: usize,
}

fn default_true() -> bool {
    true
}
fn default_memory_provider() -> String {
    "memory".to_string()
}
fn default_max_messages() -> usize {
    100
}

impl Default for MemoryConfig {
    fn default() -> Self {
        Self {
            use_short_term: true,
            use_long_term: false,
            provider: "memory".to_string(),
            max_messages: 100,
        }
    }
}

impl MemoryConfig {
    /// Create a new memory config with defaults
    pub fn new() -> Self {
        Self::default()
    }

    /// Enable long-term memory
    pub fn with_long_term(mut self) -> Self {
        self.use_long_term = true;
        self
    }

    /// Set the memory provider
    pub fn provider(mut self, provider: impl Into<String>) -> Self {
        self.provider = provider.into();
        self
    }

    /// Set max messages
    pub fn max_messages(mut self, max: usize) -> Self {
        self.max_messages = max;
        self
    }
}

/// Hooks configuration for before/after tool execution
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct HooksConfig {
    /// Enable hooks
    #[serde(default)]
    pub enabled: bool,
}

impl HooksConfig {
    /// Create a new hooks config
    pub fn new() -> Self {
        Self::default()
    }

    /// Enable hooks
    pub fn enabled(mut self) -> Self {
        self.enabled = true;
        self
    }
}

/// Output configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OutputConfig {
    /// Output mode: "silent", "verbose", "json"
    #[serde(default = "default_output_mode")]
    pub mode: String,

    /// Output file path (optional)
    #[serde(default)]
    pub file: Option<String>,
}

fn default_output_mode() -> String {
    "verbose".to_string()
}

impl Default for OutputConfig {
    fn default() -> Self {
        Self {
            mode: default_output_mode(),
            file: None,
        }
    }
}

impl OutputConfig {
    /// Create a new output config
    pub fn new() -> Self {
        Self::default()
    }

    /// Set silent mode
    pub fn silent(mut self) -> Self {
        self.mode = "silent".to_string();
        self
    }

    /// Set verbose mode
    pub fn verbose(mut self) -> Self {
        self.mode = "verbose".to_string();
        self
    }

    /// Set JSON output mode
    pub fn json(mut self) -> Self {
        self.mode = "json".to_string();
        self
    }

    /// Set output file
    pub fn file(mut self, path: impl Into<String>) -> Self {
        self.file = Some(path.into());
        self
    }
}

/// Execution configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutionConfig {
    /// Maximum number of iterations
    #[serde(default = "default_max_iterations")]
    pub max_iterations: usize,

    /// Timeout in seconds
    #[serde(default = "default_timeout")]
    pub timeout_secs: u64,

    /// Enable streaming output
    #[serde(default = "default_true")]
    pub stream: bool,
}

fn default_max_iterations() -> usize {
    10
}
fn default_timeout() -> u64 {
    300
}

impl Default for ExecutionConfig {
    fn default() -> Self {
        Self {
            max_iterations: default_max_iterations(),
            timeout_secs: default_timeout(),
            stream: true,
        }
    }
}

impl ExecutionConfig {
    /// Create a new execution config
    pub fn new() -> Self {
        Self::default()
    }

    /// Set max iterations
    pub fn max_iterations(mut self, max: usize) -> Self {
        self.max_iterations = max;
        self
    }

    /// Set timeout
    pub fn timeout(mut self, secs: u64) -> Self {
        self.timeout_secs = secs;
        self
    }

    /// Disable streaming
    pub fn no_stream(mut self) -> Self {
        self.stream = false;
        self
    }
}

// =============================================================================
// GUARDRAILS CONFIGURATION
// =============================================================================

/// Action to take when guardrail fails
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum GuardrailAction {
    /// Retry the operation
    #[default]
    Retry,
    /// Skip the operation
    Skip,
    /// Raise an error
    Raise,
}

/// Guardrail validation result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GuardrailResult {
    /// Whether the validation passed
    pub passed: bool,
    /// Validation message or error
    pub message: Option<String>,
    /// Modified output (if any)
    pub modified_output: Option<String>,
}

impl GuardrailResult {
    /// Create a passing result
    pub fn pass() -> Self {
        Self {
            passed: true,
            message: None,
            modified_output: None,
        }
    }

    /// Create a failing result with a message
    pub fn fail(message: impl Into<String>) -> Self {
        Self {
            passed: false,
            message: Some(message.into()),
            modified_output: None,
        }
    }

    /// Create a result with modified output
    pub fn with_modification(mut self, output: impl Into<String>) -> Self {
        self.modified_output = Some(output.into());
        self
    }
}

/// Configuration for guardrails and safety validation
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct GuardrailConfig {
    /// Enable guardrails
    #[serde(default)]
    pub enabled: bool,

    /// LLM-based validation prompt
    #[serde(default)]
    pub llm_validator: Option<String>,

    /// Maximum retries on failure
    #[serde(default = "default_guardrail_retries")]
    pub max_retries: usize,

    /// Action on failure
    #[serde(default)]
    pub on_fail: GuardrailAction,

    /// Policy strings (e.g., ["policy:strict", "pii:redact"])
    #[serde(default)]
    pub policies: Vec<String>,
}

fn default_guardrail_retries() -> usize {
    3
}

impl GuardrailConfig {
    /// Create a new guardrail config
    pub fn new() -> Self {
        Self::default()
    }

    /// Enable guardrails
    pub fn enabled(mut self) -> Self {
        self.enabled = true;
        self
    }

    /// Set LLM validator prompt
    pub fn llm_validator(mut self, prompt: impl Into<String>) -> Self {
        self.llm_validator = Some(prompt.into());
        self.enabled = true;
        self
    }

    /// Set max retries
    pub fn max_retries(mut self, retries: usize) -> Self {
        self.max_retries = retries;
        self
    }

    /// Set action on failure
    pub fn on_fail(mut self, action: GuardrailAction) -> Self {
        self.on_fail = action;
        self
    }

    /// Add a policy
    pub fn policy(mut self, policy: impl Into<String>) -> Self {
        self.policies.push(policy.into());
        self.enabled = true;
        self
    }
}

// =============================================================================
// KNOWLEDGE CONFIGURATION
// =============================================================================

/// Knowledge chunking strategies
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ChunkingStrategy {
    /// Fixed-size chunks
    Fixed,
    /// Semantic chunking
    #[default]
    Semantic,
    /// Sentence-based chunking
    Sentence,
    /// Paragraph-based chunking
    Paragraph,
}

/// Configuration for RAG and knowledge retrieval
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct KnowledgeConfig {
    /// Knowledge sources (files, directories, URLs)
    #[serde(default)]
    pub sources: Vec<String>,

    /// Embedder model
    #[serde(default = "default_embedder")]
    pub embedder: String,

    /// Chunking strategy
    #[serde(default)]
    pub chunking_strategy: ChunkingStrategy,

    /// Chunk size in characters
    #[serde(default = "default_chunk_size")]
    pub chunk_size: usize,

    /// Chunk overlap in characters
    #[serde(default = "default_chunk_overlap")]
    pub chunk_overlap: usize,

    /// Number of results to retrieve
    #[serde(default = "default_retrieval_k")]
    pub retrieval_k: usize,

    /// Retrieval threshold (0.0 - 1.0)
    #[serde(default)]
    pub retrieval_threshold: f32,

    /// Enable reranking
    #[serde(default)]
    pub rerank: bool,

    /// Rerank model
    #[serde(default)]
    pub rerank_model: Option<String>,

    /// Auto-retrieve context
    #[serde(default = "default_true")]
    pub auto_retrieve: bool,
}

fn default_embedder() -> String {
    "openai".to_string()
}

fn default_chunk_size() -> usize {
    1000
}

fn default_chunk_overlap() -> usize {
    200
}

fn default_retrieval_k() -> usize {
    5
}

impl KnowledgeConfig {
    /// Create a new knowledge config
    pub fn new() -> Self {
        Self::default()
    }

    /// Add a source
    pub fn source(mut self, source: impl Into<String>) -> Self {
        self.sources.push(source.into());
        self
    }

    /// Set sources
    pub fn sources(mut self, sources: Vec<String>) -> Self {
        self.sources = sources;
        self
    }

    /// Set embedder
    pub fn embedder(mut self, embedder: impl Into<String>) -> Self {
        self.embedder = embedder.into();
        self
    }

    /// Set chunking strategy
    pub fn chunking(mut self, strategy: ChunkingStrategy) -> Self {
        self.chunking_strategy = strategy;
        self
    }

    /// Set chunk size
    pub fn chunk_size(mut self, size: usize) -> Self {
        self.chunk_size = size;
        self
    }

    /// Set retrieval k
    pub fn retrieval_k(mut self, k: usize) -> Self {
        self.retrieval_k = k;
        self
    }

    /// Enable reranking
    pub fn with_rerank(mut self) -> Self {
        self.rerank = true;
        self
    }

    /// Set rerank model
    pub fn rerank_model(mut self, model: impl Into<String>) -> Self {
        self.rerank_model = Some(model.into());
        self.rerank = true;
        self
    }
}

// =============================================================================
// PLANNING CONFIGURATION
// =============================================================================

/// Configuration for planning mode
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct PlanningConfig {
    /// Enable planning
    #[serde(default)]
    pub enabled: bool,

    /// Planning LLM (if different from main)
    #[serde(default)]
    pub llm: Option<String>,

    /// Enable reasoning during planning
    #[serde(default)]
    pub reasoning: bool,

    /// Auto-approve plans without user confirmation
    #[serde(default)]
    pub auto_approve: bool,

    /// Read-only mode (only read operations allowed)
    #[serde(default)]
    pub read_only: bool,
}

impl PlanningConfig {
    /// Create a new planning config
    pub fn new() -> Self {
        Self::default()
    }

    /// Enable planning
    pub fn enabled(mut self) -> Self {
        self.enabled = true;
        self
    }

    /// Set planning LLM
    pub fn llm(mut self, llm: impl Into<String>) -> Self {
        self.llm = Some(llm.into());
        self.enabled = true;
        self
    }

    /// Enable reasoning
    pub fn with_reasoning(mut self) -> Self {
        self.reasoning = true;
        self
    }

    /// Enable auto-approve
    pub fn auto_approve(mut self) -> Self {
        self.auto_approve = true;
        self
    }

    /// Enable read-only mode
    pub fn read_only(mut self) -> Self {
        self.read_only = true;
        self
    }
}

// =============================================================================
// REFLECTION CONFIGURATION
// =============================================================================

/// Configuration for self-reflection
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReflectionConfig {
    /// Enable reflection
    #[serde(default)]
    pub enabled: bool,

    /// Minimum iterations
    #[serde(default = "default_min_iterations")]
    pub min_iterations: usize,

    /// Maximum iterations
    #[serde(default = "default_max_reflect_iterations")]
    pub max_iterations: usize,

    /// Reflection LLM (if different from main)
    #[serde(default)]
    pub llm: Option<String>,

    /// Custom reflection prompt
    #[serde(default)]
    pub prompt: Option<String>,
}

fn default_min_iterations() -> usize {
    1
}

fn default_max_reflect_iterations() -> usize {
    3
}

impl Default for ReflectionConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            min_iterations: 1,
            max_iterations: 3,
            llm: None,
            prompt: None,
        }
    }
}

impl ReflectionConfig {
    /// Create a new reflection config
    pub fn new() -> Self {
        Self::default()
    }

    /// Enable reflection
    pub fn enabled(mut self) -> Self {
        self.enabled = true;
        self
    }

    /// Set min iterations
    pub fn min_iterations(mut self, min: usize) -> Self {
        self.min_iterations = min;
        self.enabled = true;
        self
    }

    /// Set max iterations
    pub fn max_iterations(mut self, max: usize) -> Self {
        self.max_iterations = max;
        self.enabled = true;
        self
    }

    /// Set reflection LLM
    pub fn llm(mut self, llm: impl Into<String>) -> Self {
        self.llm = Some(llm.into());
        self.enabled = true;
        self
    }

    /// Set custom prompt
    pub fn prompt(mut self, prompt: impl Into<String>) -> Self {
        self.prompt = Some(prompt.into());
        self.enabled = true;
        self
    }
}

// =============================================================================
// CACHING CONFIGURATION
// =============================================================================

/// Configuration for caching behavior
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CachingConfig {
    /// Enable response caching
    #[serde(default = "default_true")]
    pub enabled: bool,

    /// Enable prompt caching (provider-specific)
    #[serde(default)]
    pub prompt_caching: bool,

    /// Cache TTL in seconds
    #[serde(default)]
    pub ttl_secs: Option<u64>,
}

impl Default for CachingConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            prompt_caching: false,
            ttl_secs: None,
        }
    }
}

impl CachingConfig {
    /// Create a new caching config
    pub fn new() -> Self {
        Self::default()
    }

    /// Disable caching
    pub fn disabled(mut self) -> Self {
        self.enabled = false;
        self
    }

    /// Enable prompt caching
    pub fn with_prompt_caching(mut self) -> Self {
        self.prompt_caching = true;
        self
    }

    /// Set TTL
    pub fn ttl(mut self, secs: u64) -> Self {
        self.ttl_secs = Some(secs);
        self
    }
}

// =============================================================================
// WEB CONFIGURATION
// =============================================================================

/// Web search providers
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum WebSearchProvider {
    /// DuckDuckGo search
    #[default]
    DuckDuckGo,
    /// Google search
    Google,
    /// Bing search
    Bing,
    /// Tavily search
    Tavily,
    /// Serper search
    Serper,
}

/// Configuration for web search and fetch capabilities
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WebConfig {
    /// Enable web search
    #[serde(default = "default_true")]
    pub search: bool,

    /// Enable web fetch (retrieve full page content)
    #[serde(default = "default_true")]
    pub fetch: bool,

    /// Search provider
    #[serde(default)]
    pub search_provider: WebSearchProvider,

    /// Maximum search results
    #[serde(default = "default_max_results")]
    pub max_results: usize,
}

fn default_max_results() -> usize {
    5
}

impl Default for WebConfig {
    fn default() -> Self {
        Self {
            search: true,
            fetch: true,
            search_provider: WebSearchProvider::default(),
            max_results: 5,
        }
    }
}

impl WebConfig {
    /// Create a new web config
    pub fn new() -> Self {
        Self::default()
    }

    /// Disable search
    pub fn no_search(mut self) -> Self {
        self.search = false;
        self
    }

    /// Disable fetch
    pub fn no_fetch(mut self) -> Self {
        self.fetch = false;
        self
    }

    /// Set search provider
    pub fn provider(mut self, provider: WebSearchProvider) -> Self {
        self.search_provider = provider;
        self
    }

    /// Set max results
    pub fn max_results(mut self, max: usize) -> Self {
        self.max_results = max;
        self
    }
}

// =============================================================================
// AUTONOMY CONFIGURATION
// =============================================================================

/// Autonomy levels for agent behavior
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AutonomyLevel {
    /// Suggest actions, wait for approval
    #[default]
    Suggest,
    /// Auto-edit with confirmation
    AutoEdit,
    /// Full autonomous operation
    FullAuto,
}

/// Configuration for agent autonomy
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct AutonomyConfig {
    /// Autonomy level
    #[serde(default)]
    pub level: AutonomyLevel,

    /// Require approval for destructive actions
    #[serde(default = "default_true")]
    pub require_approval: bool,

    /// Maximum autonomous actions before pause
    #[serde(default)]
    pub max_actions: Option<usize>,

    /// Allowed tools for autonomous execution
    #[serde(default)]
    pub allowed_tools: Vec<String>,

    /// Blocked tools (never run autonomously)
    #[serde(default)]
    pub blocked_tools: Vec<String>,
}

impl AutonomyConfig {
    /// Create a new autonomy config
    pub fn new() -> Self {
        Self::default()
    }

    /// Set autonomy level
    pub fn level(mut self, level: AutonomyLevel) -> Self {
        self.level = level;
        self
    }

    /// Disable approval requirement
    pub fn no_approval(mut self) -> Self {
        self.require_approval = false;
        self
    }

    /// Set max actions
    pub fn max_actions(mut self, max: usize) -> Self {
        self.max_actions = Some(max);
        self
    }

    /// Add allowed tool
    pub fn allow_tool(mut self, tool: impl Into<String>) -> Self {
        self.allowed_tools.push(tool.into());
        self
    }

    /// Add blocked tool
    pub fn block_tool(mut self, tool: impl Into<String>) -> Self {
        self.blocked_tools.push(tool.into());
        self
    }

    /// Set to full auto mode
    pub fn full_auto(mut self) -> Self {
        self.level = AutonomyLevel::FullAuto;
        self.require_approval = false;
        self
    }
}

// =============================================================================
// SKILLS CONFIGURATION
// =============================================================================

/// Configuration for agent skills
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct SkillsConfig {
    /// Direct skill paths
    #[serde(default)]
    pub paths: Vec<String>,

    /// Directories to scan for skills
    #[serde(default)]
    pub dirs: Vec<String>,

    /// Auto-discover from default locations
    #[serde(default)]
    pub auto_discover: bool,
}

impl SkillsConfig {
    /// Create a new skills config
    pub fn new() -> Self {
        Self::default()
    }

    /// Add a skill path
    pub fn path(mut self, path: impl Into<String>) -> Self {
        self.paths.push(path.into());
        self
    }

    /// Add a skills directory
    pub fn dir(mut self, dir: impl Into<String>) -> Self {
        self.dirs.push(dir.into());
        self
    }

    /// Enable auto-discovery
    pub fn auto_discover(mut self) -> Self {
        self.auto_discover = true;
        self
    }
}

// =============================================================================
// TEMPLATE CONFIGURATION
// =============================================================================

/// Configuration for prompt templates
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TemplateConfig {
    /// System template
    #[serde(default)]
    pub system: Option<String>,

    /// Prompt template
    #[serde(default)]
    pub prompt: Option<String>,

    /// Response template
    #[serde(default)]
    pub response: Option<String>,

    /// Use system prompt
    #[serde(default = "default_true")]
    pub use_system_prompt: bool,
}

impl Default for TemplateConfig {
    fn default() -> Self {
        Self {
            system: None,
            prompt: None,
            response: None,
            use_system_prompt: true,
        }
    }
}

impl TemplateConfig {
    /// Create a new template config
    pub fn new() -> Self {
        Self::default()
    }

    /// Set system template
    pub fn system(mut self, template: impl Into<String>) -> Self {
        self.system = Some(template.into());
        self
    }

    /// Set prompt template
    pub fn prompt(mut self, template: impl Into<String>) -> Self {
        self.prompt = Some(template.into());
        self
    }

    /// Set response template
    pub fn response(mut self, template: impl Into<String>) -> Self {
        self.response = Some(template.into());
        self
    }

    /// Disable system prompt
    pub fn no_system_prompt(mut self) -> Self {
        self.use_system_prompt = false;
        self
    }
}

// =============================================================================
// MULTI-AGENT CONFIGURATIONS
// =============================================================================

/// Configuration for multi-agent hooks
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct MultiAgentHooksConfig {
    /// Enable task start callback
    #[serde(default)]
    pub on_task_start: bool,

    /// Enable task complete callback
    #[serde(default)]
    pub on_task_complete: bool,

    /// Enable completion checker
    #[serde(default)]
    pub completion_checker: bool,
}

/// Configuration for multi-agent output
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct MultiAgentOutputConfig {
    /// Verbosity level (0=silent, 1=minimal, 2+=verbose)
    #[serde(default)]
    pub verbose: u8,

    /// Enable streaming output
    #[serde(default = "default_true")]
    pub stream: bool,
}

/// Configuration for multi-agent execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MultiAgentExecutionConfig {
    /// Maximum iterations per task
    #[serde(default = "default_multi_agent_iter")]
    pub max_iter: usize,

    /// Maximum retries on failure
    #[serde(default = "default_multi_agent_retries")]
    pub max_retries: usize,
}

fn default_multi_agent_iter() -> usize {
    10
}

fn default_multi_agent_retries() -> usize {
    5
}

impl Default for MultiAgentExecutionConfig {
    fn default() -> Self {
        Self {
            max_iter: 10,
            max_retries: 5,
        }
    }
}

/// Configuration for multi-agent planning
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct MultiAgentPlanningConfig {
    /// Planning LLM model
    #[serde(default)]
    pub llm: Option<String>,

    /// Auto-approve generated plans
    #[serde(default)]
    pub auto_approve: bool,

    /// Enable reasoning in planning
    #[serde(default)]
    pub reasoning: bool,
}

/// Configuration for multi-agent memory
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct MultiAgentMemoryConfig {
    /// User identification
    #[serde(default)]
    pub user_id: Option<String>,

    /// Memory provider config
    #[serde(default)]
    pub config: HashMap<String, serde_json::Value>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_memory_config_defaults() {
        let config = MemoryConfig::new();
        assert!(config.use_short_term);
        assert!(!config.use_long_term);
        assert_eq!(config.provider, "memory");
    }

    #[test]
    fn test_guardrail_config() {
        let config = GuardrailConfig::new()
            .llm_validator("Ensure response is safe")
            .max_retries(5)
            .on_fail(GuardrailAction::Raise)
            .policy("pii:redact");

        assert!(config.enabled);
        assert_eq!(
            config.llm_validator,
            Some("Ensure response is safe".to_string())
        );
        assert_eq!(config.max_retries, 5);
        assert_eq!(config.on_fail, GuardrailAction::Raise);
        assert!(config.policies.contains(&"pii:redact".to_string()));
    }

    #[test]
    fn test_guardrail_result() {
        let pass = GuardrailResult::pass();
        assert!(pass.passed);
        assert!(pass.message.is_none());

        let fail = GuardrailResult::fail("Invalid content");
        assert!(!fail.passed);
        assert_eq!(fail.message, Some("Invalid content".to_string()));

        let modified = GuardrailResult::pass().with_modification("Modified output");
        assert!(modified.passed);
        assert_eq!(
            modified.modified_output,
            Some("Modified output".to_string())
        );
    }

    #[test]
    fn test_knowledge_config() {
        let config = KnowledgeConfig::new()
            .source("docs/")
            .source("data.pdf")
            .embedder("openai")
            .chunking(ChunkingStrategy::Semantic)
            .retrieval_k(10)
            .with_rerank();

        assert_eq!(config.sources.len(), 2);
        assert_eq!(config.embedder, "openai");
        assert_eq!(config.chunking_strategy, ChunkingStrategy::Semantic);
        assert_eq!(config.retrieval_k, 10);
        assert!(config.rerank);
    }

    #[test]
    fn test_planning_config() {
        let config = PlanningConfig::new()
            .llm("gpt-4o")
            .with_reasoning()
            .auto_approve();

        assert!(config.enabled);
        assert_eq!(config.llm, Some("gpt-4o".to_string()));
        assert!(config.reasoning);
        assert!(config.auto_approve);
    }

    #[test]
    fn test_reflection_config() {
        let config = ReflectionConfig::new()
            .min_iterations(2)
            .max_iterations(5)
            .prompt("Evaluate accuracy");

        assert!(config.enabled);
        assert_eq!(config.min_iterations, 2);
        assert_eq!(config.max_iterations, 5);
        assert_eq!(config.prompt, Some("Evaluate accuracy".to_string()));
    }

    #[test]
    fn test_caching_config() {
        let config = CachingConfig::new().with_prompt_caching().ttl(3600);

        assert!(config.enabled);
        assert!(config.prompt_caching);
        assert_eq!(config.ttl_secs, Some(3600));
    }

    #[test]
    fn test_web_config() {
        let config = WebConfig::new()
            .provider(WebSearchProvider::Tavily)
            .max_results(10);

        assert!(config.search);
        assert!(config.fetch);
        assert_eq!(config.search_provider, WebSearchProvider::Tavily);
        assert_eq!(config.max_results, 10);
    }

    #[test]
    fn test_autonomy_config() {
        let config = AutonomyConfig::new()
            .level(AutonomyLevel::AutoEdit)
            .max_actions(10)
            .allow_tool("search")
            .block_tool("delete");

        assert_eq!(config.level, AutonomyLevel::AutoEdit);
        assert_eq!(config.max_actions, Some(10));
        assert!(config.allowed_tools.contains(&"search".to_string()));
        assert!(config.blocked_tools.contains(&"delete".to_string()));
    }

    #[test]
    fn test_autonomy_full_auto() {
        let config = AutonomyConfig::new().full_auto();

        assert_eq!(config.level, AutonomyLevel::FullAuto);
        assert!(!config.require_approval);
    }

    #[test]
    fn test_skills_config() {
        let config = SkillsConfig::new()
            .path("./my-skill")
            .dir("~/.praisonai/skills/")
            .auto_discover();

        assert!(config.paths.contains(&"./my-skill".to_string()));
        assert!(config.dirs.contains(&"~/.praisonai/skills/".to_string()));
        assert!(config.auto_discover);
    }

    #[test]
    fn test_template_config() {
        let config = TemplateConfig::new()
            .system("You are a helpful assistant")
            .prompt("User: {input}")
            .response("Response format");

        assert_eq!(
            config.system,
            Some("You are a helpful assistant".to_string())
        );
        assert_eq!(config.prompt, Some("User: {input}".to_string()));
        assert_eq!(config.response, Some("Response format".to_string()));
        assert!(config.use_system_prompt);
    }

    #[test]
    fn test_memory_config_builder() {
        let config = MemoryConfig::new()
            .with_long_term()
            .provider("chroma")
            .max_messages(50);

        assert!(config.use_long_term);
        assert_eq!(config.provider, "chroma");
        assert_eq!(config.max_messages, 50);
    }

    #[test]
    fn test_output_config() {
        let config = OutputConfig::new().silent().file("output.txt");
        assert_eq!(config.mode, "silent");
        assert_eq!(config.file, Some("output.txt".to_string()));
    }
}
