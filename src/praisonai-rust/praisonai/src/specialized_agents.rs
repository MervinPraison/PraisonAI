//! Specialized agents for PraisonAI
//!
//! This module provides specialized agent types matching the Python SDK:
//! - `PromptExpanderAgent`: Expands short prompts into detailed, comprehensive prompts
//! - `QueryRewriterAgent`: Transforms queries to improve retrieval quality in RAG
//!
//! # Example
//!
//! ```rust,ignore
//! use praisonai::specialized_agents::{PromptExpanderAgent, ExpandStrategy};
//!
//! let expander = PromptExpanderAgent::new()
//!     .model("gpt-4o-mini")
//!     .build();
//!
//! let result = expander.expand("Write a blog post", ExpandStrategy::Detailed, None).await?;
//! println!("Expanded: {}", result.expanded_prompt);
//! ```

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// =============================================================================
// PROMPT EXPANDER AGENT
// =============================================================================

/// Expansion strategy for prompts
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ExpandStrategy {
    /// Basic expansion with minimal additions
    Basic,
    /// Detailed expansion with comprehensive context
    Detailed,
    /// Structured expansion with clear sections
    Structured,
    /// Creative expansion with imaginative elements
    Creative,
    /// Auto-detect best strategy based on prompt
    #[default]
    Auto,
}

impl std::fmt::Display for ExpandStrategy {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ExpandStrategy::Basic => write!(f, "basic"),
            ExpandStrategy::Detailed => write!(f, "detailed"),
            ExpandStrategy::Structured => write!(f, "structured"),
            ExpandStrategy::Creative => write!(f, "creative"),
            ExpandStrategy::Auto => write!(f, "auto"),
        }
    }
}

impl ExpandStrategy {
    /// Get all available strategies
    pub fn all() -> Vec<ExpandStrategy> {
        vec![
            ExpandStrategy::Basic,
            ExpandStrategy::Detailed,
            ExpandStrategy::Structured,
            ExpandStrategy::Creative,
            ExpandStrategy::Auto,
        ]
    }

    /// Parse from string
    pub fn from_str(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "basic" => Some(ExpandStrategy::Basic),
            "detailed" => Some(ExpandStrategy::Detailed),
            "structured" => Some(ExpandStrategy::Structured),
            "creative" => Some(ExpandStrategy::Creative),
            "auto" => Some(ExpandStrategy::Auto),
            _ => None,
        }
    }
}

/// Result of prompt expansion
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExpandResult {
    /// Original prompt
    pub original_prompt: String,
    /// Expanded prompt
    pub expanded_prompt: String,
    /// Strategy used for expansion
    pub strategy_used: ExpandStrategy,
    /// Additional metadata
    pub metadata: HashMap<String, serde_json::Value>,
}

impl ExpandResult {
    /// Create a new expand result
    pub fn new(
        original: impl Into<String>,
        expanded: impl Into<String>,
        strategy: ExpandStrategy,
    ) -> Self {
        Self {
            original_prompt: original.into(),
            expanded_prompt: expanded.into(),
            strategy_used: strategy,
            metadata: HashMap::new(),
        }
    }

    /// Add metadata
    pub fn with_metadata(mut self, key: impl Into<String>, value: impl Into<serde_json::Value>) -> Self {
        self.metadata.insert(key.into(), value.into());
        self
    }

    /// Get expansion ratio (expanded length / original length)
    pub fn expansion_ratio(&self) -> f64 {
        if self.original_prompt.is_empty() {
            0.0
        } else {
            self.expanded_prompt.len() as f64 / self.original_prompt.len() as f64
        }
    }
}

/// Prompt expansion prompts for each strategy
pub struct ExpandPrompts;

impl ExpandPrompts {
    /// Basic expansion prompt
    pub const BASIC: &'static str = r#"Expand the following prompt with additional context and clarity while maintaining the original intent. Add relevant details that would help an AI assistant understand and respond better.

Original prompt: {prompt}

Expanded prompt:"#;

    /// Detailed expansion prompt
    pub const DETAILED: &'static str = r#"Transform the following prompt into a comprehensive, detailed request. Include:
- Clear objectives and expected outcomes
- Relevant context and background information
- Specific requirements or constraints
- Quality criteria for the response
- Any relevant examples or references

Original prompt: {prompt}

Detailed expanded prompt:"#;

    /// Structured expansion prompt
    pub const STRUCTURED: &'static str = r#"Restructure the following prompt into a well-organized format with clear sections:

1. **Objective**: What needs to be accomplished
2. **Context**: Background information
3. **Requirements**: Specific needs and constraints
4. **Output Format**: Expected format of the response
5. **Success Criteria**: How to evaluate the response

Original prompt: {prompt}

Structured expanded prompt:"#;

    /// Creative expansion prompt
    pub const CREATIVE: &'static str = r#"Expand the following prompt with creative and imaginative elements while maintaining the core intent. Add engaging context, vivid descriptions, and innovative angles that could inspire a more creative response.

Original prompt: {prompt}

Creative expanded prompt:"#;

    /// Auto-detection prompt
    pub const AUTO: &'static str = r#"Analyze the following prompt and expand it using the most appropriate strategy. Consider:
- The type of task (creative, technical, analytical, etc.)
- The level of detail needed
- The expected output format

First, briefly identify the best expansion approach, then provide the expanded prompt.

Original prompt: {prompt}

Analysis and expanded prompt:"#;

    /// Get prompt for strategy
    pub fn get(strategy: ExpandStrategy) -> &'static str {
        match strategy {
            ExpandStrategy::Basic => Self::BASIC,
            ExpandStrategy::Detailed => Self::DETAILED,
            ExpandStrategy::Structured => Self::STRUCTURED,
            ExpandStrategy::Creative => Self::CREATIVE,
            ExpandStrategy::Auto => Self::AUTO,
        }
    }
}

/// Configuration for PromptExpanderAgent
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PromptExpanderConfig {
    /// Agent name
    pub name: String,
    /// LLM model to use
    pub model: String,
    /// Custom instructions
    pub instructions: Option<String>,
    /// Verbose output
    pub verbose: bool,
    /// Temperature for LLM
    pub temperature: f32,
    /// Max tokens for response
    pub max_tokens: usize,
}

impl Default for PromptExpanderConfig {
    fn default() -> Self {
        Self {
            name: "PromptExpanderAgent".to_string(),
            model: "gpt-4o-mini".to_string(),
            instructions: None,
            verbose: false,
            temperature: 0.7,
            max_tokens: 1000,
        }
    }
}

/// Builder for PromptExpanderAgent
#[derive(Debug, Clone, Default)]
pub struct PromptExpanderAgentBuilder {
    config: PromptExpanderConfig,
}

impl PromptExpanderAgentBuilder {
    /// Create a new builder
    pub fn new() -> Self {
        Self::default()
    }

    /// Set agent name
    pub fn name(mut self, name: impl Into<String>) -> Self {
        self.config.name = name.into();
        self
    }

    /// Set LLM model
    pub fn model(mut self, model: impl Into<String>) -> Self {
        self.config.model = model.into();
        self
    }

    /// Set custom instructions
    pub fn instructions(mut self, instructions: impl Into<String>) -> Self {
        self.config.instructions = Some(instructions.into());
        self
    }

    /// Enable verbose output
    pub fn verbose(mut self) -> Self {
        self.config.verbose = true;
        self
    }

    /// Set temperature
    pub fn temperature(mut self, temp: f32) -> Self {
        self.config.temperature = temp;
        self
    }

    /// Set max tokens
    pub fn max_tokens(mut self, tokens: usize) -> Self {
        self.config.max_tokens = tokens;
        self
    }

    /// Build the agent
    pub fn build(self) -> PromptExpanderAgent {
        PromptExpanderAgent {
            config: self.config,
        }
    }
}

/// Agent for expanding prompts
#[derive(Debug, Clone)]
pub struct PromptExpanderAgent {
    config: PromptExpanderConfig,
}

impl PromptExpanderAgent {
    /// Create a new builder
    pub fn new() -> PromptExpanderAgentBuilder {
        PromptExpanderAgentBuilder::new()
    }

    /// Get agent name
    pub fn name(&self) -> &str {
        &self.config.name
    }

    /// Get model
    pub fn model(&self) -> &str {
        &self.config.model
    }

    /// Detect the best expansion strategy for a prompt
    pub fn detect_strategy(&self, prompt: &str) -> ExpandStrategy {
        let prompt_lower = prompt.to_lowercase();
        let word_count = prompt.split_whitespace().count();

        // Creative indicators
        if prompt_lower.contains("creative")
            || prompt_lower.contains("story")
            || prompt_lower.contains("imagine")
            || prompt_lower.contains("write a poem")
            || prompt_lower.contains("fiction")
        {
            return ExpandStrategy::Creative;
        }

        // Structured indicators
        if prompt_lower.contains("analyze")
            || prompt_lower.contains("compare")
            || prompt_lower.contains("evaluate")
            || prompt_lower.contains("report")
            || prompt_lower.contains("document")
        {
            return ExpandStrategy::Structured;
        }

        // Detailed indicators
        if prompt_lower.contains("explain")
            || prompt_lower.contains("describe in detail")
            || prompt_lower.contains("comprehensive")
            || prompt_lower.contains("thorough")
        {
            return ExpandStrategy::Detailed;
        }

        // Short prompts benefit from detailed expansion
        if word_count < 10 {
            return ExpandStrategy::Detailed;
        }

        // Default to basic for longer, clear prompts
        ExpandStrategy::Basic
    }

    /// Expand a prompt (sync placeholder - actual implementation would use LLM)
    pub fn expand_sync(
        &self,
        prompt: &str,
        strategy: ExpandStrategy,
        context: Option<&str>,
    ) -> ExpandResult {
        let actual_strategy = if strategy == ExpandStrategy::Auto {
            self.detect_strategy(prompt)
        } else {
            strategy
        };

        // Build the expansion prompt
        let expansion_prompt = ExpandPrompts::get(actual_strategy).replace("{prompt}", prompt);

        // Add context if provided
        let full_prompt = if let Some(ctx) = context {
            format!("{}\n\nAdditional context: {}", expansion_prompt, ctx)
        } else {
            expansion_prompt
        };

        // Placeholder: In real implementation, this would call the LLM
        // For now, return a simple expansion
        let expanded = format!(
            "## Expanded Prompt\n\n{}\n\n### Original Intent\n{}\n\n### Additional Context\nThis prompt has been expanded using the {} strategy.",
            prompt,
            prompt,
            actual_strategy
        );

        ExpandResult::new(prompt, expanded, actual_strategy)
            .with_metadata("expansion_prompt", full_prompt)
            .with_metadata("model", self.config.model.clone())
    }
}

impl Default for PromptExpanderAgent {
    fn default() -> Self {
        Self::new().build()
    }
}

// =============================================================================
// QUERY REWRITER AGENT
// =============================================================================

/// Rewriting strategy for queries
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RewriteStrategy {
    /// Basic query rewriting
    Basic,
    /// HyDE (Hypothetical Document Embeddings)
    Hyde,
    /// Step-back prompting
    StepBack,
    /// Break into sub-queries
    SubQueries,
    /// Generate multiple query variations
    MultiQuery,
    /// Context-aware rewriting
    Contextual,
    /// Auto-detect best strategy
    #[default]
    Auto,
}

impl std::fmt::Display for RewriteStrategy {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            RewriteStrategy::Basic => write!(f, "basic"),
            RewriteStrategy::Hyde => write!(f, "hyde"),
            RewriteStrategy::StepBack => write!(f, "step_back"),
            RewriteStrategy::SubQueries => write!(f, "sub_queries"),
            RewriteStrategy::MultiQuery => write!(f, "multi_query"),
            RewriteStrategy::Contextual => write!(f, "contextual"),
            RewriteStrategy::Auto => write!(f, "auto"),
        }
    }
}

impl RewriteStrategy {
    /// Get all available strategies
    pub fn all() -> Vec<RewriteStrategy> {
        vec![
            RewriteStrategy::Basic,
            RewriteStrategy::Hyde,
            RewriteStrategy::StepBack,
            RewriteStrategy::SubQueries,
            RewriteStrategy::MultiQuery,
            RewriteStrategy::Contextual,
            RewriteStrategy::Auto,
        ]
    }

    /// Parse from string
    pub fn from_str(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "basic" => Some(RewriteStrategy::Basic),
            "hyde" => Some(RewriteStrategy::Hyde),
            "step_back" | "stepback" => Some(RewriteStrategy::StepBack),
            "sub_queries" | "subqueries" => Some(RewriteStrategy::SubQueries),
            "multi_query" | "multiquery" => Some(RewriteStrategy::MultiQuery),
            "contextual" => Some(RewriteStrategy::Contextual),
            "auto" => Some(RewriteStrategy::Auto),
            _ => None,
        }
    }
}

/// Result of query rewriting
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RewriteResult {
    /// Original query
    pub original_query: String,
    /// Rewritten queries
    pub rewritten_queries: Vec<String>,
    /// Strategy used
    pub strategy_used: RewriteStrategy,
    /// Hypothetical document (for HyDE strategy)
    pub hypothetical_document: Option<String>,
    /// Step-back question (for step-back strategy)
    pub step_back_question: Option<String>,
    /// Sub-queries (for sub-queries strategy)
    pub sub_queries: Option<Vec<String>>,
    /// Additional metadata
    pub metadata: HashMap<String, serde_json::Value>,
}

impl RewriteResult {
    /// Create a new rewrite result
    pub fn new(
        original: impl Into<String>,
        rewritten: Vec<String>,
        strategy: RewriteStrategy,
    ) -> Self {
        Self {
            original_query: original.into(),
            rewritten_queries: rewritten,
            strategy_used: strategy,
            hypothetical_document: None,
            step_back_question: None,
            sub_queries: None,
            metadata: HashMap::new(),
        }
    }

    /// Set hypothetical document
    pub fn with_hypothetical_document(mut self, doc: impl Into<String>) -> Self {
        self.hypothetical_document = Some(doc.into());
        self
    }

    /// Set step-back question
    pub fn with_step_back_question(mut self, question: impl Into<String>) -> Self {
        self.step_back_question = Some(question.into());
        self
    }

    /// Set sub-queries
    pub fn with_sub_queries(mut self, queries: Vec<String>) -> Self {
        self.sub_queries = Some(queries);
        self
    }

    /// Add metadata
    pub fn with_metadata(mut self, key: impl Into<String>, value: impl Into<serde_json::Value>) -> Self {
        self.metadata.insert(key.into(), value.into());
        self
    }

    /// Get the primary rewritten query
    pub fn primary_query(&self) -> Option<&str> {
        self.rewritten_queries.first().map(|s| s.as_str())
    }

    /// Get all queries for retrieval
    pub fn all_queries(&self) -> Vec<&str> {
        let mut queries: Vec<&str> = self.rewritten_queries.iter().map(|s| s.as_str()).collect();
        if let Some(sub) = &self.sub_queries {
            queries.extend(sub.iter().map(|s| s.as_str()));
        }
        queries
    }
}

/// Query rewriting prompts for each strategy
pub struct RewritePrompts;

impl RewritePrompts {
    /// Basic rewriting prompt
    pub const BASIC: &'static str = r#"Rewrite the following query to be clearer and more specific for information retrieval. Maintain the original intent while improving clarity.

Original query: {query}

Rewritten query:"#;

    /// HyDE prompt
    pub const HYDE: &'static str = r#"Given the following query, write a hypothetical document that would perfectly answer this query. This document will be used to find similar real documents.

Query: {query}

Hypothetical document that answers this query:"#;

    /// Step-back prompt
    pub const STEP_BACK: &'static str = r#"Given the following specific query, generate a more general "step-back" question that would provide broader context helpful for answering the original query.

Original query: {query}

Step-back question (more general):"#;

    /// Sub-queries prompt
    pub const SUB_QUERIES: &'static str = r#"Break down the following complex query into simpler sub-queries that together would help answer the original question. Generate 2-4 sub-queries.

Original query: {query}

Sub-queries (one per line):
1."#;

    /// Multi-query prompt
    pub const MULTI_QUERY: &'static str = r#"Generate {num_queries} different variations of the following query. Each variation should approach the question from a different angle while maintaining the same intent.

Original query: {query}

Query variations:
1."#;

    /// Contextual prompt
    pub const CONTEXTUAL: &'static str = r#"Given the chat history and the current query, rewrite the query to be self-contained and clear without requiring the chat history for context.

Chat history:
{chat_history}

Current query: {query}

Self-contained rewritten query:"#;

    /// Auto-detection prompt
    pub const AUTO: &'static str = r#"Analyze the following query and determine the best rewriting strategy, then apply it.

Query: {query}

First identify if this query would benefit from:
- Basic rewriting (simple clarification)
- HyDE (generating a hypothetical answer document)
- Step-back (asking a broader question first)
- Sub-queries (breaking into smaller questions)
- Multi-query (generating variations)

Then provide the rewritten query/queries."#;

    /// Get prompt for strategy
    pub fn get(strategy: RewriteStrategy) -> &'static str {
        match strategy {
            RewriteStrategy::Basic => Self::BASIC,
            RewriteStrategy::Hyde => Self::HYDE,
            RewriteStrategy::StepBack => Self::STEP_BACK,
            RewriteStrategy::SubQueries => Self::SUB_QUERIES,
            RewriteStrategy::MultiQuery => Self::MULTI_QUERY,
            RewriteStrategy::Contextual => Self::CONTEXTUAL,
            RewriteStrategy::Auto => Self::AUTO,
        }
    }
}

/// Configuration for QueryRewriterAgent
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QueryRewriterConfig {
    /// Agent name
    pub name: String,
    /// LLM model to use
    pub model: String,
    /// Custom instructions
    pub instructions: Option<String>,
    /// Verbose output
    pub verbose: bool,
    /// Max queries to generate
    pub max_queries: usize,
    /// Abbreviations to expand
    pub abbreviations: HashMap<String, String>,
    /// Temperature for LLM
    pub temperature: f32,
    /// Max tokens for response
    pub max_tokens: usize,
}

impl Default for QueryRewriterConfig {
    fn default() -> Self {
        Self {
            name: "QueryRewriterAgent".to_string(),
            model: "gpt-4o-mini".to_string(),
            instructions: None,
            verbose: false,
            max_queries: 5,
            abbreviations: HashMap::new(),
            temperature: 0.3,
            max_tokens: 500,
        }
    }
}

/// Builder for QueryRewriterAgent
#[derive(Debug, Clone, Default)]
pub struct QueryRewriterAgentBuilder {
    config: QueryRewriterConfig,
}

impl QueryRewriterAgentBuilder {
    /// Create a new builder
    pub fn new() -> Self {
        Self::default()
    }

    /// Set agent name
    pub fn name(mut self, name: impl Into<String>) -> Self {
        self.config.name = name.into();
        self
    }

    /// Set LLM model
    pub fn model(mut self, model: impl Into<String>) -> Self {
        self.config.model = model.into();
        self
    }

    /// Set custom instructions
    pub fn instructions(mut self, instructions: impl Into<String>) -> Self {
        self.config.instructions = Some(instructions.into());
        self
    }

    /// Enable verbose output
    pub fn verbose(mut self) -> Self {
        self.config.verbose = true;
        self
    }

    /// Set max queries
    pub fn max_queries(mut self, max: usize) -> Self {
        self.config.max_queries = max;
        self
    }

    /// Add abbreviation expansion
    pub fn abbreviation(mut self, abbrev: impl Into<String>, expansion: impl Into<String>) -> Self {
        self.config.abbreviations.insert(abbrev.into(), expansion.into());
        self
    }

    /// Set abbreviations map
    pub fn abbreviations(mut self, abbrevs: HashMap<String, String>) -> Self {
        self.config.abbreviations = abbrevs;
        self
    }

    /// Set temperature
    pub fn temperature(mut self, temp: f32) -> Self {
        self.config.temperature = temp;
        self
    }

    /// Set max tokens
    pub fn max_tokens(mut self, tokens: usize) -> Self {
        self.config.max_tokens = tokens;
        self
    }

    /// Build the agent
    pub fn build(self) -> QueryRewriterAgent {
        QueryRewriterAgent {
            config: self.config,
        }
    }
}

/// Agent for rewriting queries
#[derive(Debug, Clone)]
pub struct QueryRewriterAgent {
    config: QueryRewriterConfig,
}

impl QueryRewriterAgent {
    /// Create a new builder
    pub fn new() -> QueryRewriterAgentBuilder {
        QueryRewriterAgentBuilder::new()
    }

    /// Get agent name
    pub fn name(&self) -> &str {
        &self.config.name
    }

    /// Get model
    pub fn model(&self) -> &str {
        &self.config.model
    }

    /// Expand abbreviations in query
    pub fn expand_abbreviations(&self, query: &str) -> String {
        let mut result = query.to_string();
        for (abbrev, expansion) in &self.config.abbreviations {
            result = result.replace(abbrev, expansion);
        }
        result
    }

    /// Detect the best rewriting strategy for a query
    pub fn detect_strategy(&self, query: &str, has_chat_history: bool) -> RewriteStrategy {
        let query_lower = query.to_lowercase();
        let word_count = query.split_whitespace().count();

        // If we have chat history, use contextual
        if has_chat_history {
            return RewriteStrategy::Contextual;
        }

        // Complex queries benefit from sub-queries
        if query_lower.contains(" and ")
            || query_lower.contains(" or ")
            || word_count > 20
            || query.contains("?") && query.matches("?").count() > 1
        {
            return RewriteStrategy::SubQueries;
        }

        // Questions about concepts benefit from step-back
        if query_lower.starts_with("what is")
            || query_lower.starts_with("how does")
            || query_lower.starts_with("why")
            || query_lower.contains("explain")
        {
            return RewriteStrategy::StepBack;
        }

        // Specific factual queries benefit from HyDE
        if query_lower.starts_with("who")
            || query_lower.starts_with("when")
            || query_lower.starts_with("where")
            || query_lower.contains("specific")
        {
            return RewriteStrategy::Hyde;
        }

        // Short ambiguous queries benefit from multi-query
        if word_count < 5 {
            return RewriteStrategy::MultiQuery;
        }

        // Default to basic
        RewriteStrategy::Basic
    }

    /// Rewrite a query (sync placeholder - actual implementation would use LLM)
    pub fn rewrite_sync(
        &self,
        query: &str,
        strategy: RewriteStrategy,
        chat_history: Option<&[HashMap<String, String>]>,
        context: Option<&str>,
        num_queries: Option<usize>,
    ) -> RewriteResult {
        // Expand abbreviations first
        let expanded_query = self.expand_abbreviations(query);

        let has_history = chat_history.map(|h| !h.is_empty()).unwrap_or(false);
        let actual_strategy = if strategy == RewriteStrategy::Auto {
            self.detect_strategy(&expanded_query, has_history)
        } else {
            strategy
        };

        let num = num_queries.unwrap_or(self.config.max_queries);

        // Build result based on strategy
        let mut result = match actual_strategy {
            RewriteStrategy::Basic => {
                let rewritten = format!("{} (clarified and optimized for retrieval)", expanded_query);
                RewriteResult::new(query, vec![rewritten], actual_strategy)
            }
            RewriteStrategy::Hyde => {
                let hypothetical = format!(
                    "This document discusses {}. It provides detailed information about the topic, \
                    including key concepts, examples, and practical applications.",
                    expanded_query
                );
                RewriteResult::new(query, vec![expanded_query.clone()], actual_strategy)
                    .with_hypothetical_document(hypothetical)
            }
            RewriteStrategy::StepBack => {
                let step_back = format!("What are the fundamental concepts related to: {}", expanded_query);
                RewriteResult::new(query, vec![expanded_query.clone(), step_back.clone()], actual_strategy)
                    .with_step_back_question(step_back)
            }
            RewriteStrategy::SubQueries => {
                let sub = vec![
                    format!("What is {}?", expanded_query.split_whitespace().take(3).collect::<Vec<_>>().join(" ")),
                    format!("How does {} work?", expanded_query.split_whitespace().take(3).collect::<Vec<_>>().join(" ")),
                    format!("Examples of {}", expanded_query.split_whitespace().take(3).collect::<Vec<_>>().join(" ")),
                ];
                RewriteResult::new(query, vec![expanded_query.clone()], actual_strategy)
                    .with_sub_queries(sub)
            }
            RewriteStrategy::MultiQuery => {
                let variations: Vec<String> = (0..num.min(5))
                    .map(|i| format!("{} (variation {})", expanded_query, i + 1))
                    .collect();
                RewriteResult::new(query, variations, actual_strategy)
            }
            RewriteStrategy::Contextual => {
                let rewritten = format!("{} (contextualized from chat history)", expanded_query);
                RewriteResult::new(query, vec![rewritten], actual_strategy)
            }
            RewriteStrategy::Auto => {
                // Should not reach here as we detect above
                RewriteResult::new(query, vec![expanded_query], actual_strategy)
            }
        };

        // Add context to metadata if provided
        if let Some(ctx) = context {
            result = result.with_metadata("context", ctx.to_string());
        }

        result.with_metadata("model", self.config.model.clone())
    }
}

impl Default for QueryRewriterAgent {
    fn default() -> Self {
        Self::new().build()
    }
}

// =============================================================================
// TESTS
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    // PromptExpanderAgent tests
    #[test]
    fn test_expand_strategy_display() {
        assert_eq!(ExpandStrategy::Basic.to_string(), "basic");
        assert_eq!(ExpandStrategy::Detailed.to_string(), "detailed");
        assert_eq!(ExpandStrategy::Auto.to_string(), "auto");
    }

    #[test]
    fn test_expand_strategy_from_str() {
        assert_eq!(ExpandStrategy::from_str("basic"), Some(ExpandStrategy::Basic));
        assert_eq!(ExpandStrategy::from_str("DETAILED"), Some(ExpandStrategy::Detailed));
        assert_eq!(ExpandStrategy::from_str("invalid"), None);
    }

    #[test]
    fn test_expand_result() {
        let result = ExpandResult::new("test", "expanded test", ExpandStrategy::Basic)
            .with_metadata("key", "value");

        assert_eq!(result.original_prompt, "test");
        assert_eq!(result.expanded_prompt, "expanded test");
        assert_eq!(result.strategy_used, ExpandStrategy::Basic);
        assert!(result.metadata.contains_key("key"));
    }

    #[test]
    fn test_expand_result_ratio() {
        let result = ExpandResult::new("test", "expanded test content", ExpandStrategy::Basic);
        assert!(result.expansion_ratio() > 1.0);

        let empty = ExpandResult::new("", "expanded", ExpandStrategy::Basic);
        assert_eq!(empty.expansion_ratio(), 0.0);
    }

    #[test]
    fn test_prompt_expander_builder() {
        let agent = PromptExpanderAgent::new()
            .name("TestExpander")
            .model("gpt-4")
            .temperature(0.5)
            .verbose()
            .build();

        assert_eq!(agent.name(), "TestExpander");
        assert_eq!(agent.model(), "gpt-4");
    }

    #[test]
    fn test_prompt_expander_detect_strategy() {
        let agent = PromptExpanderAgent::default();

        // Creative detection
        assert_eq!(
            agent.detect_strategy("Write a creative story about dragons"),
            ExpandStrategy::Creative
        );

        // Structured detection
        assert_eq!(
            agent.detect_strategy("Analyze the market trends"),
            ExpandStrategy::Structured
        );

        // Short prompts get detailed
        assert_eq!(
            agent.detect_strategy("Hello"),
            ExpandStrategy::Detailed
        );
    }

    #[test]
    fn test_prompt_expander_expand_sync() {
        let agent = PromptExpanderAgent::default();
        let result = agent.expand_sync("Write a blog post", ExpandStrategy::Basic, None);

        assert_eq!(result.original_prompt, "Write a blog post");
        assert!(!result.expanded_prompt.is_empty());
        assert_eq!(result.strategy_used, ExpandStrategy::Basic);
    }

    // QueryRewriterAgent tests
    #[test]
    fn test_rewrite_strategy_display() {
        assert_eq!(RewriteStrategy::Basic.to_string(), "basic");
        assert_eq!(RewriteStrategy::Hyde.to_string(), "hyde");
        assert_eq!(RewriteStrategy::StepBack.to_string(), "step_back");
    }

    #[test]
    fn test_rewrite_strategy_from_str() {
        assert_eq!(RewriteStrategy::from_str("basic"), Some(RewriteStrategy::Basic));
        assert_eq!(RewriteStrategy::from_str("hyde"), Some(RewriteStrategy::Hyde));
        assert_eq!(RewriteStrategy::from_str("step_back"), Some(RewriteStrategy::StepBack));
        assert_eq!(RewriteStrategy::from_str("stepback"), Some(RewriteStrategy::StepBack));
        assert_eq!(RewriteStrategy::from_str("invalid"), None);
    }

    #[test]
    fn test_rewrite_result() {
        let result = RewriteResult::new("test query", vec!["rewritten".to_string()], RewriteStrategy::Basic)
            .with_hypothetical_document("hypothetical doc")
            .with_step_back_question("broader question")
            .with_sub_queries(vec!["sub1".to_string(), "sub2".to_string()])
            .with_metadata("key", "value");

        assert_eq!(result.original_query, "test query");
        assert_eq!(result.primary_query(), Some("rewritten"));
        assert!(result.hypothetical_document.is_some());
        assert!(result.step_back_question.is_some());
        assert!(result.sub_queries.is_some());
    }

    #[test]
    fn test_rewrite_result_all_queries() {
        let result = RewriteResult::new("test", vec!["q1".to_string(), "q2".to_string()], RewriteStrategy::Basic)
            .with_sub_queries(vec!["sub1".to_string(), "sub2".to_string()]);

        let all = result.all_queries();
        assert_eq!(all.len(), 4);
    }

    #[test]
    fn test_query_rewriter_builder() {
        let agent = QueryRewriterAgent::new()
            .name("TestRewriter")
            .model("gpt-4")
            .max_queries(3)
            .abbreviation("ML", "Machine Learning")
            .temperature(0.2)
            .verbose()
            .build();

        assert_eq!(agent.name(), "TestRewriter");
        assert_eq!(agent.model(), "gpt-4");
    }

    #[test]
    fn test_query_rewriter_expand_abbreviations() {
        let agent = QueryRewriterAgent::new()
            .abbreviation("ML", "Machine Learning")
            .abbreviation("AI", "Artificial Intelligence")
            .build();

        let expanded = agent.expand_abbreviations("What is ML and AI?");
        assert!(expanded.contains("Machine Learning"));
        assert!(expanded.contains("Artificial Intelligence"));
    }

    #[test]
    fn test_query_rewriter_detect_strategy() {
        let agent = QueryRewriterAgent::default();

        // Complex query -> SubQueries
        assert_eq!(
            agent.detect_strategy("What is X and how does Y relate to Z?", false),
            RewriteStrategy::SubQueries
        );

        // Concept question -> StepBack
        assert_eq!(
            agent.detect_strategy("What is machine learning?", false),
            RewriteStrategy::StepBack
        );

        // Factual query -> Hyde
        assert_eq!(
            agent.detect_strategy("Who invented the telephone?", false),
            RewriteStrategy::Hyde
        );

        // With chat history -> Contextual
        assert_eq!(
            agent.detect_strategy("Tell me more", true),
            RewriteStrategy::Contextual
        );

        // Short query -> MultiQuery
        assert_eq!(
            agent.detect_strategy("Python", false),
            RewriteStrategy::MultiQuery
        );
    }

    #[test]
    fn test_query_rewriter_rewrite_sync() {
        let agent = QueryRewriterAgent::default();
        let result = agent.rewrite_sync("What is Rust?", RewriteStrategy::Basic, None, None, None);

        assert_eq!(result.original_query, "What is Rust?");
        assert!(!result.rewritten_queries.is_empty());
        assert_eq!(result.strategy_used, RewriteStrategy::Basic);
    }

    #[test]
    fn test_query_rewriter_hyde_strategy() {
        let agent = QueryRewriterAgent::default();
        let result = agent.rewrite_sync("What is Rust?", RewriteStrategy::Hyde, None, None, None);

        assert!(result.hypothetical_document.is_some());
    }

    #[test]
    fn test_query_rewriter_sub_queries_strategy() {
        let agent = QueryRewriterAgent::default();
        let result = agent.rewrite_sync("Complex query", RewriteStrategy::SubQueries, None, None, None);

        assert!(result.sub_queries.is_some());
        assert!(!result.sub_queries.as_ref().unwrap().is_empty());
    }
}
