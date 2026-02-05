//! RAG (Retrieval Augmented Generation) Module
//!
//! This module provides RAG capabilities for agents:
//! - `RAG` - Main RAG pipeline
//! - `RAGConfig` - Configuration for RAG
//! - `RAGResult` - Result with answer and citations
//! - `Citation` - Source citation
//! - `SmartRetriever` - Intelligent document retrieval
//!
//! # Example
//!
//! ```ignore
//! use praisonai::rag::{RAG, RAGConfig};
//!
//! let rag = RAG::new()
//!     .config(RAGConfig::default())
//!     .build()?;
//!
//! let result = rag.query("What is the main finding?")?;
//! println!("{}", result.answer);
//! ```

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use crate::error::Result;

// =============================================================================
// CITATION
// =============================================================================

/// A citation referencing a source document.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Citation {
    /// Citation ID (e.g., "[1]")
    pub id: String,
    /// Source document or URL
    pub source: String,
    /// Relevant text snippet
    pub text: String,
    /// Page number if applicable
    pub page: Option<u32>,
    /// Relevance score (0.0 to 1.0)
    pub score: Option<f32>,
    /// Additional metadata
    pub metadata: HashMap<String, String>,
}

impl Citation {
    /// Create a new citation
    pub fn new(id: impl Into<String>, source: impl Into<String>, text: impl Into<String>) -> Self {
        Self {
            id: id.into(),
            source: source.into(),
            text: text.into(),
            page: None,
            score: None,
            metadata: HashMap::new(),
        }
    }

    /// Set the page number
    pub fn page(mut self, page: u32) -> Self {
        self.page = Some(page);
        self
    }

    /// Set the relevance score
    pub fn score(mut self, score: f32) -> Self {
        self.score = Some(score);
        self
    }

    /// Add metadata
    pub fn metadata(mut self, key: impl Into<String>, value: impl Into<String>) -> Self {
        self.metadata.insert(key.into(), value.into());
        self
    }
}

// =============================================================================
// CONTEXT PACK
// =============================================================================

/// A pack of context chunks for RAG.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextPack {
    /// Retrieved chunks
    pub chunks: Vec<ContextChunk>,
    /// Total token count
    pub total_tokens: usize,
    /// Query used for retrieval
    pub query: String,
}

/// A single context chunk.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextChunk {
    /// Chunk content
    pub content: String,
    /// Source document
    pub source: String,
    /// Relevance score
    pub score: f32,
    /// Chunk index in source
    pub index: usize,
    /// Metadata
    pub metadata: HashMap<String, String>,
}

impl ContextChunk {
    /// Create a new context chunk
    pub fn new(content: impl Into<String>, source: impl Into<String>, score: f32) -> Self {
        Self {
            content: content.into(),
            source: source.into(),
            score,
            index: 0,
            metadata: HashMap::new(),
        }
    }
}

// =============================================================================
// RAG RESULT
// =============================================================================

/// Result of a RAG query.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RAGResult {
    /// Generated answer
    pub answer: String,
    /// Citations used in the answer
    pub citations: Vec<Citation>,
    /// Context chunks used
    pub context: ContextPack,
    /// Token usage
    pub tokens_used: usize,
    /// Processing time in milliseconds
    pub processing_time_ms: u64,
}

impl RAGResult {
    /// Create a new RAG result
    pub fn new(answer: impl Into<String>, context: ContextPack) -> Self {
        Self {
            answer: answer.into(),
            citations: Vec::new(),
            context,
            tokens_used: 0,
            processing_time_ms: 0,
        }
    }

    /// Add a citation
    pub fn add_citation(&mut self, citation: Citation) {
        self.citations.push(citation);
    }

    /// Get the number of citations
    pub fn citation_count(&self) -> usize {
        self.citations.len()
    }
}

// =============================================================================
// RAG CONFIG
// =============================================================================

/// Retrieval strategy for RAG.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RetrievalStrategy {
    /// Simple similarity search
    #[default]
    Similarity,
    /// Hybrid search (keyword + semantic)
    Hybrid,
    /// Multi-query expansion
    MultiQuery,
    /// Hierarchical retrieval
    Hierarchical,
    /// Contextual compression
    Compression,
}

/// Citations mode for RAG.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CitationsMode {
    /// Include inline citations
    #[default]
    Inline,
    /// Footnote-style citations
    Footnote,
    /// No citations
    None,
}

/// Configuration for RAG pipeline.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RAGConfig {
    /// Maximum number of chunks to retrieve
    pub top_k: usize,
    /// Minimum relevance score threshold
    pub score_threshold: f32,
    /// Maximum context tokens
    pub max_context_tokens: usize,
    /// Retrieval strategy
    pub strategy: RetrievalStrategy,
    /// Citations mode
    pub citations_mode: CitationsMode,
    /// Enable reranking
    pub rerank: bool,
    /// Enable context compression
    pub compress: bool,
    /// Chunk overlap for splitting
    pub chunk_overlap: usize,
    /// Chunk size for splitting
    pub chunk_size: usize,
}

impl Default for RAGConfig {
    fn default() -> Self {
        Self {
            top_k: 5,
            score_threshold: 0.7,
            max_context_tokens: 4096,
            strategy: RetrievalStrategy::default(),
            citations_mode: CitationsMode::default(),
            rerank: false,
            compress: false,
            chunk_overlap: 50,
            chunk_size: 500,
        }
    }
}

impl RAGConfig {
    /// Create a new RAGConfig
    pub fn new() -> Self {
        Self::default()
    }

    /// Set top_k
    pub fn top_k(mut self, k: usize) -> Self {
        self.top_k = k;
        self
    }

    /// Set score threshold
    pub fn score_threshold(mut self, threshold: f32) -> Self {
        self.score_threshold = threshold;
        self
    }

    /// Set max context tokens
    pub fn max_context_tokens(mut self, tokens: usize) -> Self {
        self.max_context_tokens = tokens;
        self
    }

    /// Set retrieval strategy
    pub fn strategy(mut self, strategy: RetrievalStrategy) -> Self {
        self.strategy = strategy;
        self
    }

    /// Set citations mode
    pub fn citations_mode(mut self, mode: CitationsMode) -> Self {
        self.citations_mode = mode;
        self
    }

    /// Enable reranking
    pub fn rerank(mut self, enable: bool) -> Self {
        self.rerank = enable;
        self
    }

    /// Enable compression
    pub fn compress(mut self, enable: bool) -> Self {
        self.compress = enable;
        self
    }
}

// =============================================================================
// RETRIEVAL CONFIG
// =============================================================================

/// Unified retrieval configuration (Agent-first).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RetrievalConfig {
    /// Enable RAG
    pub enabled: bool,
    /// RAG configuration
    pub rag: RAGConfig,
    /// Knowledge sources
    pub sources: Vec<String>,
    /// Auto-retrieve on every query
    pub auto_retrieve: bool,
}

impl Default for RetrievalConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            rag: RAGConfig::default(),
            sources: Vec::new(),
            auto_retrieve: true,
        }
    }
}

impl RetrievalConfig {
    /// Create a new RetrievalConfig
    pub fn new() -> Self {
        Self::default()
    }

    /// Enable retrieval
    pub fn enable(mut self) -> Self {
        self.enabled = true;
        self
    }

    /// Add a source
    pub fn source(mut self, source: impl Into<String>) -> Self {
        self.sources.push(source.into());
        self
    }

    /// Set RAG config
    pub fn rag(mut self, config: RAGConfig) -> Self {
        self.rag = config;
        self
    }
}

// =============================================================================
// TOKEN BUDGET
// =============================================================================

/// Token budget for context management.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TokenBudget {
    /// Total available tokens
    pub total: usize,
    /// Tokens for system prompt
    pub system: usize,
    /// Tokens for context
    pub context: usize,
    /// Tokens for response
    pub response: usize,
    /// Reserved tokens
    pub reserved: usize,
}

impl Default for TokenBudget {
    fn default() -> Self {
        Self {
            total: 8192,
            system: 500,
            context: 4096,
            response: 2048,
            reserved: 500,
        }
    }
}

impl TokenBudget {
    /// Create a new token budget
    pub fn new(total: usize) -> Self {
        let context = total / 2;
        let response = total / 4;
        let system = 500.min(total / 10);
        let reserved = total - context - response - system;
        Self {
            total,
            system,
            context,
            response,
            reserved,
        }
    }

    /// Get available context tokens
    pub fn available_context(&self) -> usize {
        self.context
    }

    /// Check if budget allows more context
    pub fn can_add_context(&self, tokens: usize) -> bool {
        tokens <= self.context
    }
}

/// Get model context window size.
pub fn get_model_context_window(model: &str) -> usize {
    match model {
        m if m.contains("gpt-4o") => 128000,
        m if m.contains("gpt-4-turbo") => 128000,
        m if m.contains("gpt-4") => 8192,
        m if m.contains("gpt-3.5") => 16385,
        m if m.contains("claude-3") => 200000,
        m if m.contains("claude-2") => 100000,
        m if m.contains("gemini-1.5") => 1000000,
        m if m.contains("gemini-pro") => 32768,
        _ => 8192, // Default
    }
}

/// Estimate token count for text.
pub fn estimate_tokens(text: &str) -> usize {
    // Rough estimate: ~4 characters per token
    (text.len() + 3) / 4
}

// =============================================================================
// RETRIEVAL RESULT
// =============================================================================

/// Result of a retrieval operation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RetrievalResult {
    /// Retrieved chunks
    pub chunks: Vec<ContextChunk>,
    /// Query used
    pub query: String,
    /// Strategy used
    pub strategy: RetrievalStrategy,
    /// Total documents searched
    pub total_searched: usize,
}

impl RetrievalResult {
    /// Create a new retrieval result
    pub fn new(query: impl Into<String>, strategy: RetrievalStrategy) -> Self {
        Self {
            chunks: Vec::new(),
            query: query.into(),
            strategy,
            total_searched: 0,
        }
    }

    /// Add a chunk
    pub fn add_chunk(&mut self, chunk: ContextChunk) {
        self.chunks.push(chunk);
    }

    /// Get top chunks by score
    pub fn top_chunks(&self, n: usize) -> Vec<&ContextChunk> {
        let mut sorted: Vec<_> = self.chunks.iter().collect();
        sorted.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap_or(std::cmp::Ordering::Equal));
        sorted.into_iter().take(n).collect()
    }
}

// =============================================================================
// RAG PIPELINE
// =============================================================================

/// Main RAG pipeline.
#[derive(Debug, Clone)]
pub struct RAG {
    /// Configuration
    pub config: RAGConfig,
    /// LLM model for generation
    pub model: String,
    /// Knowledge sources
    pub sources: Vec<String>,
}

impl Default for RAG {
    fn default() -> Self {
        Self {
            config: RAGConfig::default(),
            model: "gpt-4o-mini".to_string(),
            sources: Vec::new(),
        }
    }
}

impl RAG {
    /// Create a new RAG builder
    pub fn new() -> RAGBuilder {
        RAGBuilder::default()
    }

    /// Query the RAG pipeline (placeholder)
    pub fn query(&self, question: &str) -> Result<RAGResult> {
        // This is a placeholder - actual implementation would:
        // 1. Retrieve relevant chunks from knowledge base
        // 2. Build context from chunks
        // 3. Generate answer with LLM
        // 4. Extract citations

        let context = ContextPack {
            chunks: vec![ContextChunk::new(
                "Sample retrieved content for the query.",
                "knowledge_base",
                0.95,
            )],
            total_tokens: 50,
            query: question.to_string(),
        };

        let mut result = RAGResult::new(
            format!("Answer to: {} (based on retrieved context)", question),
            context,
        );

        result.add_citation(Citation::new(
            "[1]",
            "knowledge_base",
            "Sample retrieved content",
        ));

        Ok(result)
    }

    /// Add a knowledge source
    pub fn add_source(&mut self, source: impl Into<String>) {
        self.sources.push(source.into());
    }

    /// Build context from chunks
    pub fn build_context(&self, chunks: &[ContextChunk]) -> String {
        chunks
            .iter()
            .enumerate()
            .map(|(i, chunk)| format!("[{}] {}", i + 1, chunk.content))
            .collect::<Vec<_>>()
            .join("\n\n")
    }

    /// Truncate context to fit token budget
    pub fn truncate_context(&self, context: &str, max_tokens: usize) -> String {
        let estimated = estimate_tokens(context);
        if estimated <= max_tokens {
            return context.to_string();
        }

        // Truncate to approximate token limit
        let char_limit = max_tokens * 4;
        if context.len() <= char_limit {
            return context.to_string();
        }

        format!("{}...", &context[..char_limit])
    }
}

/// Builder for RAG
#[derive(Debug, Default)]
pub struct RAGBuilder {
    config: RAGConfig,
    model: Option<String>,
    sources: Vec<String>,
}

impl RAGBuilder {
    /// Set the configuration
    pub fn config(mut self, config: RAGConfig) -> Self {
        self.config = config;
        self
    }

    /// Set the model
    pub fn model(mut self, model: impl Into<String>) -> Self {
        self.model = Some(model.into());
        self
    }

    /// Add a source
    pub fn source(mut self, source: impl Into<String>) -> Self {
        self.sources.push(source.into());
        self
    }

    /// Build the RAG pipeline
    pub fn build(self) -> Result<RAG> {
        Ok(RAG {
            config: self.config,
            model: self.model.unwrap_or_else(|| "gpt-4o-mini".to_string()),
            sources: self.sources,
        })
    }
}

// =============================================================================
// CONTEXT UTILITIES
// =============================================================================

/// Build context string from chunks.
pub fn build_context(chunks: &[ContextChunk]) -> String {
    chunks
        .iter()
        .enumerate()
        .map(|(i, chunk)| format!("[{}] {}", i + 1, chunk.content))
        .collect::<Vec<_>>()
        .join("\n\n")
}

/// Truncate context to fit token limit.
pub fn truncate_context(context: &str, max_tokens: usize) -> String {
    let estimated = estimate_tokens(context);
    if estimated <= max_tokens {
        return context.to_string();
    }

    let char_limit = max_tokens * 4;
    if context.len() <= char_limit {
        return context.to_string();
    }

    format!("{}...", &context[..char_limit])
}

/// Deduplicate chunks by content similarity.
pub fn deduplicate_chunks(chunks: Vec<ContextChunk>, _threshold: f32) -> Vec<ContextChunk> {
    let mut result = Vec::new();
    for chunk in chunks {
        let is_duplicate = result.iter().any(|existing: &ContextChunk| {
            // Simple content comparison (could use more sophisticated similarity)
            existing.content == chunk.content
        });
        if !is_duplicate {
            result.push(chunk);
        }
    }
    result
}

// =============================================================================
// TESTS
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_citation_creation() {
        let citation = Citation::new("[1]", "document.pdf", "Sample text")
            .page(5)
            .score(0.95);

        assert_eq!(citation.id, "[1]");
        assert_eq!(citation.source, "document.pdf");
        assert_eq!(citation.page, Some(5));
        assert_eq!(citation.score, Some(0.95));
    }

    #[test]
    fn test_context_chunk() {
        let chunk = ContextChunk::new("Content here", "source.txt", 0.85);
        assert_eq!(chunk.content, "Content here");
        assert_eq!(chunk.score, 0.85);
    }

    #[test]
    fn test_rag_config_defaults() {
        let config = RAGConfig::default();
        assert_eq!(config.top_k, 5);
        assert_eq!(config.score_threshold, 0.7);
        assert_eq!(config.strategy, RetrievalStrategy::Similarity);
    }

    #[test]
    fn test_rag_config_builder() {
        let config = RAGConfig::new()
            .top_k(10)
            .score_threshold(0.8)
            .strategy(RetrievalStrategy::Hybrid)
            .rerank(true);

        assert_eq!(config.top_k, 10);
        assert_eq!(config.score_threshold, 0.8);
        assert_eq!(config.strategy, RetrievalStrategy::Hybrid);
        assert!(config.rerank);
    }

    #[test]
    fn test_retrieval_config() {
        let config = RetrievalConfig::new()
            .enable()
            .source("docs/")
            .source("knowledge/");

        assert!(config.enabled);
        assert_eq!(config.sources.len(), 2);
    }

    #[test]
    fn test_token_budget() {
        let budget = TokenBudget::new(16000);
        assert_eq!(budget.total, 16000);
        assert!(budget.can_add_context(4000));
    }

    #[test]
    fn test_model_context_window() {
        assert_eq!(get_model_context_window("gpt-4o"), 128000);
        assert_eq!(get_model_context_window("claude-3-opus"), 200000);
        assert_eq!(get_model_context_window("unknown-model"), 8192);
    }

    #[test]
    fn test_estimate_tokens() {
        let text = "Hello world";
        let tokens = estimate_tokens(text);
        assert!(tokens > 0);
        assert!(tokens < text.len());
    }

    #[test]
    fn test_rag_builder() {
        let rag = RAG::new()
            .model("gpt-4o")
            .source("docs/")
            .config(RAGConfig::new().top_k(10))
            .build()
            .unwrap();

        assert_eq!(rag.model, "gpt-4o");
        assert_eq!(rag.sources.len(), 1);
        assert_eq!(rag.config.top_k, 10);
    }

    #[test]
    fn test_rag_query() {
        let rag = RAG::new().build().unwrap();
        let result = rag.query("What is the answer?").unwrap();

        assert!(!result.answer.is_empty());
        assert!(!result.citations.is_empty());
    }

    #[test]
    fn test_build_context() {
        let chunks = vec![
            ContextChunk::new("First chunk", "doc1", 0.9),
            ContextChunk::new("Second chunk", "doc2", 0.8),
        ];

        let context = build_context(&chunks);
        assert!(context.contains("[1]"));
        assert!(context.contains("[2]"));
        assert!(context.contains("First chunk"));
    }

    #[test]
    fn test_truncate_context() {
        let long_text = "a".repeat(10000);
        let truncated = truncate_context(&long_text, 100);
        assert!(truncated.len() < long_text.len());
        assert!(truncated.ends_with("..."));
    }

    #[test]
    fn test_deduplicate_chunks() {
        let chunks = vec![
            ContextChunk::new("Same content", "doc1", 0.9),
            ContextChunk::new("Same content", "doc2", 0.8),
            ContextChunk::new("Different content", "doc3", 0.7),
        ];

        let deduped = deduplicate_chunks(chunks, 0.9);
        assert_eq!(deduped.len(), 2);
    }

    #[test]
    fn test_retrieval_result() {
        let mut result = RetrievalResult::new("test query", RetrievalStrategy::Similarity);
        result.add_chunk(ContextChunk::new("High score", "doc1", 0.95));
        result.add_chunk(ContextChunk::new("Low score", "doc2", 0.5));

        let top = result.top_chunks(1);
        assert_eq!(top.len(), 1);
        assert_eq!(top[0].score, 0.95);
    }

    #[test]
    fn test_rag_result() {
        let context = ContextPack {
            chunks: vec![],
            total_tokens: 0,
            query: "test".to_string(),
        };

        let mut result = RAGResult::new("Answer", context);
        result.add_citation(Citation::new("[1]", "source", "text"));

        assert_eq!(result.citation_count(), 1);
    }
}
