//! Context Management Module for PraisonAI Agents.
//!
//! This module provides comprehensive context management capabilities:
//! - Token estimation and budgeting
//! - Context composition within limits
//! - Optimization strategies (truncate, sliding window, summarize)
//! - Multi-agent context isolation
//!
//! # Example
//!
//! ```ignore
//! use praisonai::{ContextManager, ContextConfig, OptimizerStrategy};
//!
//! let config = ContextConfig::new()
//!     .model("gpt-4o")
//!     .strategy(OptimizerStrategy::Smart);
//!
//! let manager = ContextManager::new(config);
//! let budget = manager.allocate_budget();
//! ```

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// =============================================================================
// OPTIMIZER STRATEGY
// =============================================================================

/// Strategy for optimizing context when it exceeds limits.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum OptimizerStrategy {
    /// Truncate oldest messages
    Truncate,
    /// Sliding window of recent messages
    SlidingWindow,
    /// Summarize older messages
    Summarize,
    /// Prune tool-related messages
    PruneTools,
    /// Non-destructive (fail if over limit)
    NonDestructive,
    /// Smart combination of strategies
    #[default]
    Smart,
}

// =============================================================================
// CONTEXT SEGMENT
// =============================================================================

/// A segment of context with token count.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextSegment {
    /// Segment name/type
    pub name: String,
    /// Token count for this segment
    pub tokens: usize,
    /// Priority (higher = more important)
    pub priority: i32,
    /// Content of the segment
    pub content: Option<String>,
}

impl ContextSegment {
    /// Create a new context segment
    pub fn new(name: impl Into<String>, tokens: usize) -> Self {
        Self {
            name: name.into(),
            tokens,
            priority: 0,
            content: None,
        }
    }

    /// Set priority
    pub fn priority(mut self, priority: i32) -> Self {
        self.priority = priority;
        self
    }

    /// Set content
    pub fn content(mut self, content: impl Into<String>) -> Self {
        self.content = Some(content.into());
        self
    }
}

// =============================================================================
// CONTEXT LEDGER
// =============================================================================

/// Tracks token usage across different context segments.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ContextLedger {
    /// Segments in the ledger
    pub segments: Vec<ContextSegment>,
    /// Total tokens used
    pub total_tokens: usize,
    /// Maximum allowed tokens
    pub max_tokens: usize,
}

impl ContextLedger {
    /// Create a new ledger with max tokens
    pub fn new(max_tokens: usize) -> Self {
        Self {
            segments: Vec::new(),
            total_tokens: 0,
            max_tokens,
        }
    }

    /// Add a segment to the ledger
    pub fn add(&mut self, segment: ContextSegment) {
        self.total_tokens += segment.tokens;
        self.segments.push(segment);
    }

    /// Get remaining tokens
    pub fn remaining(&self) -> usize {
        self.max_tokens.saturating_sub(self.total_tokens)
    }

    /// Check if over budget
    pub fn is_over_budget(&self) -> bool {
        self.total_tokens > self.max_tokens
    }

    /// Get utilization percentage
    pub fn utilization(&self) -> f64 {
        if self.max_tokens == 0 {
            0.0
        } else {
            self.total_tokens as f64 / self.max_tokens as f64
        }
    }
}

// =============================================================================
// BUDGET ALLOCATION
// =============================================================================

/// Budget allocation for different context components.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BudgetAllocation {
    /// Total budget in tokens
    pub total: usize,
    /// Budget for system prompt
    pub system: usize,
    /// Budget for conversation history
    pub history: usize,
    /// Budget for tools
    pub tools: usize,
    /// Reserved for output
    pub output_reserve: usize,
}

impl BudgetAllocation {
    /// Create a new budget allocation
    pub fn new(total: usize) -> Self {
        // Default allocation: 10% system, 60% history, 10% tools, 20% output
        let output_reserve = total / 5;
        let available = total - output_reserve;
        Self {
            total,
            system: available / 10,
            history: available * 6 / 10,
            tools: available / 10,
            output_reserve,
        }
    }

    /// Create with custom ratios
    pub fn with_ratios(total: usize, system_pct: f64, history_pct: f64, tools_pct: f64) -> Self {
        let output_reserve = total / 5;
        let available = total - output_reserve;
        Self {
            total,
            system: (available as f64 * system_pct) as usize,
            history: (available as f64 * history_pct) as usize,
            tools: (available as f64 * tools_pct) as usize,
            output_reserve,
        }
    }
}

// =============================================================================
// CONTEXT CONFIG
// =============================================================================

/// Configuration for context management.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextConfig {
    /// Model name for token limits
    #[serde(default = "default_model")]
    pub model: String,

    /// Maximum context tokens (0 = auto from model)
    #[serde(default)]
    pub max_tokens: usize,

    /// Optimization strategy
    #[serde(default)]
    pub strategy: OptimizerStrategy,

    /// Enable context monitoring
    #[serde(default)]
    pub monitoring: bool,

    /// Output reserve percentage
    #[serde(default = "default_output_reserve_pct")]
    pub output_reserve_pct: f64,
}

fn default_model() -> String {
    "gpt-4o".to_string()
}

fn default_output_reserve_pct() -> f64 {
    0.2
}

impl Default for ContextConfig {
    fn default() -> Self {
        Self {
            model: "gpt-4o".to_string(),
            max_tokens: 0,
            strategy: OptimizerStrategy::Smart,
            monitoring: false,
            output_reserve_pct: 0.2,
        }
    }
}

impl ContextConfig {
    /// Create a new context config
    pub fn new() -> Self {
        Self::default()
    }

    /// Set model
    pub fn model(mut self, model: impl Into<String>) -> Self {
        self.model = model.into();
        self
    }

    /// Set max tokens
    pub fn max_tokens(mut self, tokens: usize) -> Self {
        self.max_tokens = tokens;
        self
    }

    /// Set optimization strategy
    pub fn strategy(mut self, strategy: OptimizerStrategy) -> Self {
        self.strategy = strategy;
        self
    }

    /// Enable monitoring
    pub fn with_monitoring(mut self) -> Self {
        self.monitoring = true;
        self
    }

    /// Set output reserve percentage
    pub fn output_reserve_pct(mut self, pct: f64) -> Self {
        self.output_reserve_pct = pct;
        self
    }
}

// =============================================================================
// MODEL LIMITS
// =============================================================================

/// Get context limit for a model.
pub fn get_model_limit(model: &str) -> usize {
    match model {
        // GPT-4 variants
        "gpt-4o" | "gpt-4o-2024-05-13" | "gpt-4o-2024-08-06" => 128_000,
        "gpt-4o-mini" | "gpt-4o-mini-2024-07-18" => 128_000,
        "gpt-4-turbo" | "gpt-4-turbo-preview" | "gpt-4-1106-preview" => 128_000,
        "gpt-4" | "gpt-4-0613" => 8_192,
        "gpt-4-32k" | "gpt-4-32k-0613" => 32_768,
        // GPT-3.5 variants
        "gpt-3.5-turbo" | "gpt-3.5-turbo-0125" => 16_385,
        "gpt-3.5-turbo-16k" => 16_385,
        // Claude variants
        "claude-3-opus" | "claude-3-opus-20240229" => 200_000,
        "claude-3-sonnet" | "claude-3-sonnet-20240229" => 200_000,
        "claude-3-haiku" | "claude-3-haiku-20240307" => 200_000,
        "claude-3-5-sonnet" | "claude-3-5-sonnet-20240620" => 200_000,
        // Gemini variants
        "gemini-pro" | "gemini-1.0-pro" => 32_760,
        "gemini-1.5-pro" => 1_000_000,
        "gemini-1.5-flash" => 1_000_000,
        // Default
        _ => 8_192,
    }
}

/// Get recommended output reserve for a model.
pub fn get_output_reserve(model: &str) -> usize {
    match model {
        "gpt-4o" | "gpt-4o-mini" => 16_384,
        "gpt-4-turbo" => 4_096,
        "gpt-4" => 2_048,
        "claude-3-opus" | "claude-3-sonnet" | "claude-3-5-sonnet" => 4_096,
        _ => 2_048,
    }
}

// =============================================================================
// TOKEN ESTIMATION
// =============================================================================

/// Estimate tokens for a string using heuristic (4 chars ≈ 1 token).
pub fn estimate_tokens_heuristic(text: &str) -> usize {
    // Rough heuristic: 4 characters per token on average
    (text.len() + 3) / 4
}

/// Estimate tokens for messages.
pub fn estimate_messages_tokens(messages: &[serde_json::Value]) -> usize {
    let mut total = 0;
    for msg in messages {
        // Base overhead per message
        total += 4;
        if let Some(content) = msg.get("content").and_then(|c| c.as_str()) {
            total += estimate_tokens_heuristic(content);
        }
        if let Some(role) = msg.get("role").and_then(|r| r.as_str()) {
            total += estimate_tokens_heuristic(role);
        }
        if let Some(name) = msg.get("name").and_then(|n| n.as_str()) {
            total += estimate_tokens_heuristic(name);
        }
    }
    total
}

/// Estimate tokens for tool schemas.
pub fn estimate_tool_schema_tokens(tools: &[serde_json::Value]) -> usize {
    let mut total = 0;
    for tool in tools {
        let json_str = serde_json::to_string(tool).unwrap_or_default();
        total += estimate_tokens_heuristic(&json_str);
    }
    total
}

// =============================================================================
// CONTEXT BUDGETER
// =============================================================================

/// Manages context budget allocation.
#[derive(Debug, Clone)]
pub struct ContextBudgeter {
    /// Model name
    pub model: String,
    /// Maximum tokens
    pub max_tokens: usize,
    /// Output reserve
    pub output_reserve: usize,
}

impl ContextBudgeter {
    /// Create a new budgeter for a model
    pub fn new(model: impl Into<String>) -> Self {
        let model = model.into();
        let max_tokens = get_model_limit(&model);
        let output_reserve = get_output_reserve(&model);
        Self {
            model,
            max_tokens,
            output_reserve,
        }
    }

    /// Create with custom limits
    pub fn with_limits(model: impl Into<String>, max_tokens: usize, output_reserve: usize) -> Self {
        Self {
            model: model.into(),
            max_tokens,
            output_reserve,
        }
    }

    /// Get available tokens (total - output reserve)
    pub fn available(&self) -> usize {
        self.max_tokens.saturating_sub(self.output_reserve)
    }

    /// Allocate budget
    pub fn allocate(&self) -> BudgetAllocation {
        BudgetAllocation::new(self.available())
    }

    /// Allocate with custom ratios
    pub fn allocate_custom(
        &self,
        system_pct: f64,
        history_pct: f64,
        tools_pct: f64,
    ) -> BudgetAllocation {
        BudgetAllocation::with_ratios(self.available(), system_pct, history_pct, tools_pct)
    }
}

// =============================================================================
// CONTEXT MANAGER
// =============================================================================

/// High-level context manager facade.
#[derive(Debug, Clone)]
pub struct ContextManager {
    /// Configuration
    pub config: ContextConfig,
    /// Budgeter
    pub budgeter: ContextBudgeter,
    /// Current ledger
    pub ledger: ContextLedger,
}

impl ContextManager {
    /// Create a new context manager
    pub fn new(config: ContextConfig) -> Self {
        let max_tokens = if config.max_tokens > 0 {
            config.max_tokens
        } else {
            get_model_limit(&config.model)
        };
        let output_reserve = (max_tokens as f64 * config.output_reserve_pct) as usize;
        let budgeter = ContextBudgeter::with_limits(&config.model, max_tokens, output_reserve);
        let ledger = ContextLedger::new(budgeter.available());

        Self {
            config,
            budgeter,
            ledger,
        }
    }

    /// Create with default config
    pub fn default_for_model(model: impl Into<String>) -> Self {
        Self::new(ContextConfig::new().model(model))
    }

    /// Get budget allocation
    pub fn allocate_budget(&self) -> BudgetAllocation {
        self.budgeter.allocate()
    }

    /// Add a segment to the ledger
    pub fn add_segment(&mut self, segment: ContextSegment) {
        self.ledger.add(segment);
    }

    /// Get remaining tokens
    pub fn remaining(&self) -> usize {
        self.ledger.remaining()
    }

    /// Check if over budget
    pub fn is_over_budget(&self) -> bool {
        self.ledger.is_over_budget()
    }

    /// Get utilization
    pub fn utilization(&self) -> f64 {
        self.ledger.utilization()
    }

    /// Reset the ledger
    pub fn reset(&mut self) {
        self.ledger = ContextLedger::new(self.budgeter.available());
    }

    /// Estimate and track system prompt
    pub fn track_system(&mut self, system_prompt: &str) {
        let tokens = estimate_tokens_heuristic(system_prompt);
        self.add_segment(ContextSegment::new("system", tokens).priority(100));
    }

    /// Estimate and track messages
    pub fn track_messages(&mut self, messages: &[serde_json::Value]) {
        let tokens = estimate_messages_tokens(messages);
        self.add_segment(ContextSegment::new("history", tokens).priority(50));
    }

    /// Estimate and track tools
    pub fn track_tools(&mut self, tools: &[serde_json::Value]) {
        let tokens = estimate_tool_schema_tokens(tools);
        self.add_segment(ContextSegment::new("tools", tokens).priority(75));
    }
}

// =============================================================================
// MULTI-AGENT CONTEXT MANAGER
// =============================================================================

/// Context manager for multi-agent scenarios.
#[derive(Debug, Default)]
pub struct MultiAgentContextManager {
    /// Per-agent managers
    managers: HashMap<String, ContextManager>,
    /// Shared context segments
    shared_segments: Vec<ContextSegment>,
}

impl MultiAgentContextManager {
    /// Create a new multi-agent context manager
    pub fn new() -> Self {
        Self::default()
    }

    /// Register an agent
    pub fn register_agent(&mut self, agent_id: impl Into<String>, config: ContextConfig) {
        let manager = ContextManager::new(config);
        self.managers.insert(agent_id.into(), manager);
    }

    /// Get manager for an agent
    pub fn get(&self, agent_id: &str) -> Option<&ContextManager> {
        self.managers.get(agent_id)
    }

    /// Get mutable manager for an agent
    pub fn get_mut(&mut self, agent_id: &str) -> Option<&mut ContextManager> {
        self.managers.get_mut(agent_id)
    }

    /// Add shared segment
    pub fn add_shared(&mut self, segment: ContextSegment) {
        self.shared_segments.push(segment);
    }

    /// Get all agent IDs
    pub fn agent_ids(&self) -> Vec<&String> {
        self.managers.keys().collect()
    }
}

// =============================================================================
// TESTS
// =============================================================================

// =============================================================================
// FAST CONTEXT TYPES
// =============================================================================

/// A line range within a file.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LineRange {
    /// Start line (1-indexed)
    pub start: usize,
    /// End line (1-indexed)
    pub end: usize,
    /// Content of the lines (optional)
    pub content: Option<String>,
    /// Relevance score (0.0 to 1.0)
    pub relevance_score: f32,
}

impl LineRange {
    /// Create a new line range.
    pub fn new(start: usize, end: usize) -> Self {
        Self {
            start,
            end,
            content: None,
            relevance_score: 1.0,
        }
    }

    /// Set content.
    pub fn content(mut self, content: impl Into<String>) -> Self {
        self.content = Some(content.into());
        self
    }

    /// Set relevance score.
    pub fn relevance_score(mut self, score: f32) -> Self {
        self.relevance_score = score;
        self
    }

    /// Get line count.
    pub fn line_count(&self) -> usize {
        self.end.saturating_sub(self.start) + 1
    }
}

/// A file match from a search.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileMatch {
    /// File path (relative to workspace)
    pub path: String,
    /// Relevance score (0.0 to 1.0)
    pub relevance_score: f32,
    /// Matching line ranges
    pub line_ranges: Vec<LineRange>,
}

impl FileMatch {
    /// Create a new file match.
    pub fn new(path: impl Into<String>) -> Self {
        Self {
            path: path.into(),
            relevance_score: 1.0,
            line_ranges: Vec::new(),
        }
    }

    /// Set relevance score.
    pub fn relevance_score(mut self, score: f32) -> Self {
        self.relevance_score = score;
        self
    }

    /// Add a line range.
    pub fn line_range(mut self, range: LineRange) -> Self {
        self.line_ranges.push(range);
        self
    }
}

/// Result of a fast context search.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct FastContextResult {
    /// Original query
    pub query: String,
    /// Matching files
    pub files: Vec<FileMatch>,
    /// Search time in milliseconds
    pub search_time_ms: u64,
    /// Number of turns used
    pub turns_used: usize,
    /// Total tool calls made
    pub total_tool_calls: usize,
    /// Whether result is from cache
    pub from_cache: bool,
}

impl FastContextResult {
    /// Create a new result.
    pub fn new(query: impl Into<String>) -> Self {
        Self {
            query: query.into(),
            ..Default::default()
        }
    }

    /// Add a file match.
    pub fn add_file(&mut self, file: FileMatch) {
        self.files.push(file);
    }

    /// Get total number of files.
    pub fn total_files(&self) -> usize {
        self.files.len()
    }

    /// Check if empty.
    pub fn is_empty(&self) -> bool {
        self.files.is_empty()
    }

    /// Convert to context string for agent injection.
    pub fn to_context_string(&self) -> String {
        if self.files.is_empty() {
            return format!("No relevant code found for: {}", self.query);
        }

        let mut lines = vec![
            format!("# Relevant Code Context for: {}", self.query),
            format!("Found {} file(s) in {}ms\n", self.files.len(), self.search_time_ms),
        ];

        for file in &self.files {
            lines.push(format!("## {}", file.path));
            for range in &file.line_ranges {
                lines.push(format!("Lines {}-{}:", range.start, range.end));
                if let Some(content) = &range.content {
                    lines.push(format!("```\n{}\n```", content));
                }
            }
            lines.push(String::new());
        }

        lines.join("\n")
    }
}

/// Configuration for FastContext.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FastContextConfig {
    /// Workspace path
    pub workspace_path: Option<String>,
    /// LLM model for intelligent search
    pub model: String,
    /// Maximum search turns
    pub max_turns: usize,
    /// Maximum parallel tool calls
    pub max_parallel: usize,
    /// Timeout per tool call in seconds
    pub timeout: f64,
    /// Enable caching
    pub cache_enabled: bool,
    /// Cache TTL in seconds
    pub cache_ttl: u64,
}

impl Default for FastContextConfig {
    fn default() -> Self {
        Self {
            workspace_path: None,
            model: "gpt-4o-mini".to_string(),
            max_turns: 4,
            max_parallel: 8,
            timeout: 30.0,
            cache_enabled: true,
            cache_ttl: 300,
        }
    }
}

impl FastContextConfig {
    /// Create a new config.
    pub fn new() -> Self {
        Self::default()
    }

    /// Set workspace path.
    pub fn workspace_path(mut self, path: impl Into<String>) -> Self {
        self.workspace_path = Some(path.into());
        self
    }

    /// Set model.
    pub fn model(mut self, model: impl Into<String>) -> Self {
        self.model = model.into();
        self
    }

    /// Set max turns.
    pub fn max_turns(mut self, turns: usize) -> Self {
        self.max_turns = turns;
        self
    }

    /// Set max parallel.
    pub fn max_parallel(mut self, parallel: usize) -> Self {
        self.max_parallel = parallel;
        self
    }

    /// Set timeout.
    pub fn timeout(mut self, timeout: f64) -> Self {
        self.timeout = timeout;
        self
    }

    /// Enable/disable caching.
    pub fn cache_enabled(mut self, enabled: bool) -> Self {
        self.cache_enabled = enabled;
        self
    }

    /// Set cache TTL.
    pub fn cache_ttl(mut self, ttl: u64) -> Self {
        self.cache_ttl = ttl;
        self
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_context_config_defaults() {
        let config = ContextConfig::new();
        assert_eq!(config.model, "gpt-4o");
        assert_eq!(config.strategy, OptimizerStrategy::Smart);
    }

    #[test]
    fn test_context_config_builder() {
        let config = ContextConfig::new()
            .model("gpt-4")
            .max_tokens(8000)
            .strategy(OptimizerStrategy::Truncate)
            .with_monitoring();

        assert_eq!(config.model, "gpt-4");
        assert_eq!(config.max_tokens, 8000);
        assert_eq!(config.strategy, OptimizerStrategy::Truncate);
        assert!(config.monitoring);
    }

    #[test]
    fn test_model_limits() {
        assert_eq!(get_model_limit("gpt-4o"), 128_000);
        assert_eq!(get_model_limit("gpt-4"), 8_192);
        assert_eq!(get_model_limit("claude-3-opus"), 200_000);
        assert_eq!(get_model_limit("unknown"), 8_192);
    }

    #[test]
    fn test_token_estimation() {
        let text = "Hello, world!"; // 13 chars
        let tokens = estimate_tokens_heuristic(text);
        assert!(tokens >= 3 && tokens <= 5);
    }

    #[test]
    fn test_context_ledger() {
        let mut ledger = ContextLedger::new(1000);
        assert_eq!(ledger.remaining(), 1000);

        ledger.add(ContextSegment::new("system", 100));
        ledger.add(ContextSegment::new("history", 500));

        assert_eq!(ledger.total_tokens, 600);
        assert_eq!(ledger.remaining(), 400);
        assert!(!ledger.is_over_budget());
        assert!((ledger.utilization() - 0.6).abs() < 0.01);
    }

    #[test]
    fn test_budget_allocation() {
        let budget = BudgetAllocation::new(10000);
        assert_eq!(budget.total, 10000);
        assert_eq!(budget.output_reserve, 2000);
        // Available = 8000, system = 800, history = 4800, tools = 800
        assert_eq!(budget.system, 800);
        assert_eq!(budget.history, 4800);
        assert_eq!(budget.tools, 800);
    }

    #[test]
    fn test_context_budgeter() {
        let budgeter = ContextBudgeter::new("gpt-4o");
        assert_eq!(budgeter.max_tokens, 128_000);
        assert!(budgeter.available() < 128_000);
    }

    #[test]
    fn test_context_manager() {
        let config = ContextConfig::new().model("gpt-4o");
        let mut manager = ContextManager::new(config);

        manager.track_system("You are a helpful assistant.");
        assert!(manager.ledger.total_tokens > 0);

        let remaining_before = manager.remaining();
        manager.track_messages(&[serde_json::json!({"role": "user", "content": "Hello"})]);
        assert!(manager.remaining() < remaining_before);
    }

    #[test]
    fn test_multi_agent_context_manager() {
        let mut multi = MultiAgentContextManager::new();

        multi.register_agent("agent_a", ContextConfig::new().model("gpt-4o"));
        multi.register_agent("agent_b", ContextConfig::new().model("gpt-4"));

        assert!(multi.get("agent_a").is_some());
        assert!(multi.get("agent_b").is_some());
        assert!(multi.get("agent_c").is_none());

        assert_eq!(multi.agent_ids().len(), 2);
    }

    #[test]
    fn test_context_segment() {
        let segment = ContextSegment::new("test", 100)
            .priority(50)
            .content("Test content");

        assert_eq!(segment.name, "test");
        assert_eq!(segment.tokens, 100);
        assert_eq!(segment.priority, 50);
        assert_eq!(segment.content, Some("Test content".to_string()));
    }
}
