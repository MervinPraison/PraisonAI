//! Knowledge System Module
//!
//! This module provides the full knowledge management system:
//! - `Knowledge` - Main knowledge manager
//! - `KnowledgeConfig` - Configuration for knowledge
//! - `Document` - Document representation
//! - `VectorStore` - Vector store trait and implementations
//! - `Retriever` - Retrieval strategies
//! - `Reranker` - Result reranking
//!
//! # Example
//!
//! ```ignore
//! use praisonai::knowledge::{Knowledge, KnowledgeConfig};
//!
//! let knowledge = Knowledge::new()
//!     .config(KnowledgeConfig::default())
//!     .build()?;
//!
//! knowledge.add("Some document content", None)?;
//! let results = knowledge.search("query", 10)?;
//! ```

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use crate::error::Result;

// =============================================================================
// DOCUMENT
// =============================================================================

/// A document in the knowledge base.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Document {
    /// Document ID
    pub id: String,
    /// Document content
    pub content: String,
    /// Document metadata
    pub metadata: HashMap<String, String>,
    /// Source path or URL
    pub source: Option<String>,
    /// Filename if from file
    pub filename: Option<String>,
    /// Creation timestamp
    pub created_at: Option<u64>,
    /// Update timestamp
    pub updated_at: Option<u64>,
}

impl Document {
    /// Create a new document
    pub fn new(content: impl Into<String>) -> Self {
        Self {
            id: uuid::Uuid::new_v4().to_string(),
            content: content.into(),
            metadata: HashMap::new(),
            source: None,
            filename: None,
            created_at: Some(
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_secs(),
            ),
            updated_at: None,
        }
    }

    /// Set metadata
    pub fn metadata(mut self, key: impl Into<String>, value: impl Into<String>) -> Self {
        self.metadata.insert(key.into(), value.into());
        self
    }

    /// Set source
    pub fn source(mut self, source: impl Into<String>) -> Self {
        self.source = Some(source.into());
        self
    }

    /// Set filename
    pub fn filename(mut self, filename: impl Into<String>) -> Self {
        self.filename = Some(filename.into());
        self
    }
}

// =============================================================================
// SEARCH RESULT
// =============================================================================

/// A single search result item.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResultItem {
    /// Result ID
    pub id: String,
    /// Result text content
    pub text: String,
    /// Relevance score
    pub score: f32,
    /// Metadata (always a HashMap, never None)
    pub metadata: HashMap<String, String>,
    /// Source
    pub source: Option<String>,
    /// Filename
    pub filename: Option<String>,
    /// Creation timestamp
    pub created_at: Option<u64>,
    /// Update timestamp
    pub updated_at: Option<u64>,
}

impl Default for SearchResultItem {
    fn default() -> Self {
        Self {
            id: String::new(),
            text: String::new(),
            score: 0.0,
            metadata: HashMap::new(),
            source: None,
            filename: None,
            created_at: None,
            updated_at: None,
        }
    }
}

impl SearchResultItem {
    /// Create a new search result item
    pub fn new(id: impl Into<String>, text: impl Into<String>, score: f32) -> Self {
        Self {
            id: id.into(),
            text: text.into(),
            score,
            ..Default::default()
        }
    }
}

/// Container for search results.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResult {
    /// List of result items
    pub results: Vec<SearchResultItem>,
    /// Search metadata
    pub metadata: HashMap<String, String>,
    /// Original query
    pub query: String,
    /// Total count (may differ from results.len() if paginated)
    pub total_count: Option<usize>,
}

impl Default for SearchResult {
    fn default() -> Self {
        Self {
            results: Vec::new(),
            metadata: HashMap::new(),
            query: String::new(),
            total_count: None,
        }
    }
}

impl SearchResult {
    /// Create a new search result
    pub fn new(query: impl Into<String>, results: Vec<SearchResultItem>) -> Self {
        let len = results.len();
        Self {
            results,
            metadata: HashMap::new(),
            query: query.into(),
            total_count: Some(len),
        }
    }

    /// Check if empty
    pub fn is_empty(&self) -> bool {
        self.results.is_empty()
    }

    /// Get result count
    pub fn len(&self) -> usize {
        self.results.len()
    }
}

/// Result of adding content to knowledge store.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AddResult {
    /// ID of added item
    pub id: String,
    /// Whether operation succeeded
    pub success: bool,
    /// Optional message
    pub message: String,
    /// Metadata
    pub metadata: HashMap<String, String>,
}

impl Default for AddResult {
    fn default() -> Self {
        Self {
            id: String::new(),
            success: true,
            message: String::new(),
            metadata: HashMap::new(),
        }
    }
}

impl AddResult {
    /// Create a successful add result
    pub fn success(id: impl Into<String>) -> Self {
        Self {
            id: id.into(),
            success: true,
            ..Default::default()
        }
    }

    /// Create a failed add result
    pub fn failure(message: impl Into<String>) -> Self {
        Self {
            success: false,
            message: message.into(),
            ..Default::default()
        }
    }
}

// =============================================================================
// VECTOR STORE PROTOCOL
// =============================================================================

/// A vector record in the store.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VectorRecord {
    /// Record ID
    pub id: String,
    /// Text content
    pub text: String,
    /// Embedding vector
    pub embedding: Vec<f32>,
    /// Metadata
    pub metadata: HashMap<String, String>,
}

impl VectorRecord {
    /// Create a new vector record
    pub fn new(id: impl Into<String>, text: impl Into<String>, embedding: Vec<f32>) -> Self {
        Self {
            id: id.into(),
            text: text.into(),
            embedding,
            metadata: HashMap::new(),
        }
    }
}

/// Protocol for vector store implementations.
#[async_trait]
pub trait VectorStoreProtocol: Send + Sync {
    /// Add a record to the store
    async fn add(&mut self, record: VectorRecord) -> Result<String>;

    /// Search for similar records
    async fn search(&self, query_embedding: &[f32], limit: usize) -> Result<Vec<SearchResultItem>>;

    /// Get a record by ID
    async fn get(&self, id: &str) -> Result<Option<VectorRecord>>;

    /// Delete a record by ID
    async fn delete(&mut self, id: &str) -> Result<bool>;

    /// Get all records
    async fn get_all(&self, limit: usize) -> Result<Vec<VectorRecord>>;

    /// Clear all records
    async fn clear(&mut self) -> Result<()>;

    /// Get record count
    fn len(&self) -> usize;

    /// Check if empty
    fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

/// In-memory vector store implementation.
#[derive(Debug, Default)]
pub struct InMemoryVectorStore {
    records: Vec<VectorRecord>,
}

impl InMemoryVectorStore {
    /// Create a new in-memory vector store
    pub fn new() -> Self {
        Self::default()
    }

    /// Compute cosine similarity between two vectors
    fn cosine_similarity(a: &[f32], b: &[f32]) -> f32 {
        if a.len() != b.len() || a.is_empty() {
            return 0.0;
        }

        let dot: f32 = a.iter().zip(b.iter()).map(|(x, y)| x * y).sum();
        let norm_a: f32 = a.iter().map(|x| x * x).sum::<f32>().sqrt();
        let norm_b: f32 = b.iter().map(|x| x * x).sum::<f32>().sqrt();

        if norm_a == 0.0 || norm_b == 0.0 {
            return 0.0;
        }

        dot / (norm_a * norm_b)
    }
}

#[async_trait]
impl VectorStoreProtocol for InMemoryVectorStore {
    async fn add(&mut self, record: VectorRecord) -> Result<String> {
        let id = record.id.clone();
        self.records.push(record);
        Ok(id)
    }

    async fn search(&self, query_embedding: &[f32], limit: usize) -> Result<Vec<SearchResultItem>> {
        let mut scored: Vec<(f32, &VectorRecord)> = self
            .records
            .iter()
            .map(|r| (Self::cosine_similarity(query_embedding, &r.embedding), r))
            .collect();

        scored.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));

        Ok(scored
            .into_iter()
            .take(limit)
            .map(|(score, record)| SearchResultItem {
                id: record.id.clone(),
                text: record.text.clone(),
                score,
                metadata: record.metadata.clone(),
                ..Default::default()
            })
            .collect())
    }

    async fn get(&self, id: &str) -> Result<Option<VectorRecord>> {
        Ok(self.records.iter().find(|r| r.id == id).cloned())
    }

    async fn delete(&mut self, id: &str) -> Result<bool> {
        let len_before = self.records.len();
        self.records.retain(|r| r.id != id);
        Ok(self.records.len() < len_before)
    }

    async fn get_all(&self, limit: usize) -> Result<Vec<VectorRecord>> {
        Ok(self.records.iter().take(limit).cloned().collect())
    }

    async fn clear(&mut self) -> Result<()> {
        self.records.clear();
        Ok(())
    }

    fn len(&self) -> usize {
        self.records.len()
    }
}

// =============================================================================
// RETRIEVAL
// =============================================================================

/// Retrieval strategy enum.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RetrievalStrategy {
    /// Simple similarity search
    #[default]
    Similarity,
    /// Keyword-based search
    Keyword,
    /// Hybrid (similarity + keyword)
    Hybrid,
    /// Multi-query retrieval
    MultiQuery,
}

/// Retrieval result with additional metadata.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RetrievalResult {
    /// Retrieved items
    pub items: Vec<SearchResultItem>,
    /// Strategy used
    pub strategy: RetrievalStrategy,
    /// Query used
    pub query: String,
    /// Time taken in ms
    pub time_ms: u64,
}

impl RetrievalResult {
    /// Create a new retrieval result
    pub fn new(query: impl Into<String>, items: Vec<SearchResultItem>, strategy: RetrievalStrategy) -> Self {
        Self {
            items,
            strategy,
            query: query.into(),
            time_ms: 0,
        }
    }
}

/// Protocol for retriever implementations.
#[async_trait]
pub trait RetrieverProtocol: Send + Sync {
    /// Retrieve relevant documents
    async fn retrieve(&self, query: &str, limit: usize) -> Result<RetrievalResult>;

    /// Get retrieval strategy
    fn strategy(&self) -> RetrievalStrategy;
}

// =============================================================================
// RERANKER
// =============================================================================

/// Rerank result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RerankResult {
    /// Reranked items
    pub items: Vec<SearchResultItem>,
    /// Original query
    pub query: String,
}

/// Protocol for reranker implementations.
#[async_trait]
pub trait RerankerProtocol: Send + Sync {
    /// Rerank search results
    async fn rerank(&self, query: &str, items: Vec<SearchResultItem>, limit: usize) -> Result<RerankResult>;
}

/// Simple reranker that uses score-based sorting.
#[derive(Debug, Default)]
pub struct SimpleReranker;

impl SimpleReranker {
    /// Create a new simple reranker
    pub fn new() -> Self {
        Self
    }
}

#[async_trait]
impl RerankerProtocol for SimpleReranker {
    async fn rerank(&self, query: &str, mut items: Vec<SearchResultItem>, limit: usize) -> Result<RerankResult> {
        items.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap_or(std::cmp::Ordering::Equal));
        items.truncate(limit);
        Ok(RerankResult {
            items,
            query: query.to_string(),
        })
    }
}

// =============================================================================
// INDEX
// =============================================================================

/// Index type enum.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IndexType {
    /// Vector index
    #[default]
    Vector,
    /// Keyword index
    Keyword,
    /// Hybrid index
    Hybrid,
}

/// Index statistics.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IndexStats {
    /// Number of documents
    pub document_count: usize,
    /// Index type
    pub index_type: IndexType,
    /// Last updated timestamp
    pub last_updated: Option<u64>,
}

// =============================================================================
// QUERY ENGINE
// =============================================================================

/// Query mode enum.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum QueryMode {
    /// Simple query
    #[default]
    Simple,
    /// Sub-question decomposition
    SubQuestion,
    /// Tree-based query
    Tree,
}

/// Query result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QueryResult {
    /// Answer text
    pub answer: String,
    /// Source documents
    pub sources: Vec<SearchResultItem>,
    /// Query mode used
    pub mode: QueryMode,
}

// =============================================================================
// CHUNKING
// =============================================================================

/// Chunking strategy.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ChunkingStrategy {
    /// Fixed size chunks
    #[default]
    FixedSize,
    /// Sentence-based chunks
    Sentence,
    /// Paragraph-based chunks
    Paragraph,
    /// Semantic chunks
    Semantic,
}

/// Chunking configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChunkingConfig {
    /// Chunk size in characters
    pub chunk_size: usize,
    /// Overlap between chunks
    pub chunk_overlap: usize,
    /// Chunking strategy
    pub strategy: ChunkingStrategy,
}

impl Default for ChunkingConfig {
    fn default() -> Self {
        Self {
            chunk_size: 1000,
            chunk_overlap: 200,
            strategy: ChunkingStrategy::FixedSize,
        }
    }
}

/// Chunking utility.
#[derive(Debug, Default)]
pub struct Chunking {
    config: ChunkingConfig,
}

impl Chunking {
    /// Create a new chunking utility
    pub fn new(config: ChunkingConfig) -> Self {
        Self { config }
    }

    /// Chunk text into smaller pieces
    pub fn chunk(&self, text: &str) -> Vec<String> {
        match self.config.strategy {
            ChunkingStrategy::FixedSize => self.chunk_fixed_size(text),
            ChunkingStrategy::Sentence => self.chunk_by_sentence(text),
            ChunkingStrategy::Paragraph => self.chunk_by_paragraph(text),
            ChunkingStrategy::Semantic => self.chunk_fixed_size(text), // Fallback
        }
    }

    fn chunk_fixed_size(&self, text: &str) -> Vec<String> {
        let mut chunks = Vec::new();
        let chars: Vec<char> = text.chars().collect();
        let mut start = 0;

        while start < chars.len() {
            let end = (start + self.config.chunk_size).min(chars.len());
            let chunk: String = chars[start..end].iter().collect();
            chunks.push(chunk);

            if end >= chars.len() {
                break;
            }

            start = end.saturating_sub(self.config.chunk_overlap);
        }

        chunks
    }

    fn chunk_by_sentence(&self, text: &str) -> Vec<String> {
        text.split(|c| c == '.' || c == '!' || c == '?')
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect()
    }

    fn chunk_by_paragraph(&self, text: &str) -> Vec<String> {
        text.split("\n\n")
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect()
    }
}

// =============================================================================
// KNOWLEDGE CONFIG
// =============================================================================

/// Knowledge configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KnowledgeConfig {
    /// Chunking configuration
    pub chunking: ChunkingConfig,
    /// Retrieval strategy
    pub retrieval_strategy: RetrievalStrategy,
    /// Default search limit
    pub default_limit: usize,
    /// Enable reranking
    pub enable_reranking: bool,
    /// User ID for scoping
    pub user_id: Option<String>,
    /// Agent ID for scoping
    pub agent_id: Option<String>,
}

impl Default for KnowledgeConfig {
    fn default() -> Self {
        Self {
            chunking: ChunkingConfig::default(),
            retrieval_strategy: RetrievalStrategy::Similarity,
            default_limit: 10,
            enable_reranking: false,
            user_id: None,
            agent_id: None,
        }
    }
}

impl KnowledgeConfig {
    /// Create a new config
    pub fn new() -> Self {
        Self::default()
    }

    /// Set chunking config
    pub fn chunking(mut self, config: ChunkingConfig) -> Self {
        self.chunking = config;
        self
    }

    /// Set retrieval strategy
    pub fn retrieval_strategy(mut self, strategy: RetrievalStrategy) -> Self {
        self.retrieval_strategy = strategy;
        self
    }

    /// Set default limit
    pub fn default_limit(mut self, limit: usize) -> Self {
        self.default_limit = limit;
        self
    }

    /// Enable reranking
    pub fn enable_reranking(mut self, enable: bool) -> Self {
        self.enable_reranking = enable;
        self
    }

    /// Set user ID
    pub fn user_id(mut self, id: impl Into<String>) -> Self {
        self.user_id = Some(id.into());
        self
    }

    /// Set agent ID
    pub fn agent_id(mut self, id: impl Into<String>) -> Self {
        self.agent_id = Some(id.into());
        self
    }
}

// =============================================================================
// KNOWLEDGE STORE PROTOCOL
// =============================================================================

/// Protocol for knowledge store backends.
#[async_trait]
pub trait KnowledgeStoreProtocol: Send + Sync {
    /// Search for relevant content
    async fn search(
        &self,
        query: &str,
        user_id: Option<&str>,
        agent_id: Option<&str>,
        limit: usize,
    ) -> Result<SearchResult>;

    /// Add content to the store
    async fn add(
        &mut self,
        content: &str,
        user_id: Option<&str>,
        agent_id: Option<&str>,
        metadata: Option<HashMap<String, String>>,
    ) -> Result<AddResult>;

    /// Get item by ID
    async fn get(&self, item_id: &str) -> Result<Option<SearchResultItem>>;

    /// Get all items
    async fn get_all(
        &self,
        user_id: Option<&str>,
        agent_id: Option<&str>,
        limit: usize,
    ) -> Result<SearchResult>;

    /// Update an item
    async fn update(&mut self, item_id: &str, content: &str) -> Result<AddResult>;

    /// Delete an item
    async fn delete(&mut self, item_id: &str) -> Result<bool>;

    /// Delete all items
    async fn delete_all(&mut self, user_id: Option<&str>, agent_id: Option<&str>) -> Result<bool>;
}

// =============================================================================
// KNOWLEDGE
// =============================================================================

/// Main knowledge manager.
#[derive(Debug)]
pub struct Knowledge {
    /// Configuration
    pub config: KnowledgeConfig,
    /// Documents
    documents: Vec<Document>,
    /// Chunking utility
    chunking: Chunking,
}

impl Default for Knowledge {
    fn default() -> Self {
        Self {
            config: KnowledgeConfig::default(),
            documents: Vec::new(),
            chunking: Chunking::default(),
        }
    }
}

impl Knowledge {
    /// Create a new knowledge builder
    pub fn new() -> KnowledgeBuilder {
        KnowledgeBuilder::default()
    }

    /// Add content to knowledge base
    pub fn add(&mut self, content: &str, metadata: Option<HashMap<String, String>>) -> Result<AddResult> {
        let mut doc = Document::new(content);
        if let Some(meta) = metadata {
            for (k, v) in meta {
                doc.metadata.insert(k, v);
            }
        }
        let id = doc.id.clone();
        self.documents.push(doc);
        Ok(AddResult::success(id))
    }

    /// Add a document
    pub fn add_document(&mut self, document: Document) -> Result<AddResult> {
        let id = document.id.clone();
        self.documents.push(document);
        Ok(AddResult::success(id))
    }

    /// Search knowledge base (placeholder - would use embeddings in real impl)
    pub fn search(&self, query: &str, limit: usize) -> Result<SearchResult> {
        let query_lower = query.to_lowercase();
        let mut results: Vec<SearchResultItem> = self
            .documents
            .iter()
            .filter(|doc| doc.content.to_lowercase().contains(&query_lower))
            .map(|doc| SearchResultItem {
                id: doc.id.clone(),
                text: doc.content.clone(),
                score: 1.0,
                metadata: doc.metadata.clone(),
                source: doc.source.clone(),
                filename: doc.filename.clone(),
                created_at: doc.created_at,
                updated_at: doc.updated_at,
            })
            .take(limit)
            .collect();

        results.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap_or(std::cmp::Ordering::Equal));

        Ok(SearchResult::new(query, results))
    }

    /// Get document by ID
    pub fn get(&self, id: &str) -> Option<&Document> {
        self.documents.iter().find(|d| d.id == id)
    }

    /// Delete document by ID
    pub fn delete(&mut self, id: &str) -> bool {
        let len_before = self.documents.len();
        self.documents.retain(|d| d.id != id);
        self.documents.len() < len_before
    }

    /// Clear all documents
    pub fn clear(&mut self) {
        self.documents.clear();
    }

    /// Get document count
    pub fn len(&self) -> usize {
        self.documents.len()
    }

    /// Check if empty
    pub fn is_empty(&self) -> bool {
        self.documents.is_empty()
    }

    /// Chunk text using configured strategy
    pub fn chunk(&self, text: &str) -> Vec<String> {
        self.chunking.chunk(text)
    }
}

/// Builder for Knowledge
#[derive(Debug, Default)]
pub struct KnowledgeBuilder {
    config: KnowledgeConfig,
}

impl KnowledgeBuilder {
    /// Set config
    pub fn config(mut self, config: KnowledgeConfig) -> Self {
        self.config = config;
        self
    }

    /// Set chunking config
    pub fn chunking(mut self, config: ChunkingConfig) -> Self {
        self.config.chunking = config;
        self
    }

    /// Set retrieval strategy
    pub fn retrieval_strategy(mut self, strategy: RetrievalStrategy) -> Self {
        self.config.retrieval_strategy = strategy;
        self
    }

    /// Build the Knowledge instance
    pub fn build(self) -> Result<Knowledge> {
        Ok(Knowledge {
            chunking: Chunking::new(self.config.chunking.clone()),
            config: self.config,
            documents: Vec::new(),
        })
    }
}

// =============================================================================
// ERRORS
// =============================================================================

/// Knowledge backend error.
#[derive(Debug, Clone)]
pub struct KnowledgeBackendError {
    /// Error message
    pub message: String,
    /// Backend name
    pub backend: Option<String>,
}

impl std::fmt::Display for KnowledgeBackendError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        if let Some(backend) = &self.backend {
            write!(f, "Knowledge backend '{}' error: {}", backend, self.message)
        } else {
            write!(f, "Knowledge error: {}", self.message)
        }
    }
}

impl std::error::Error for KnowledgeBackendError {}

/// Scope required error.
#[derive(Debug, Clone)]
pub struct ScopeRequiredError {
    /// Backend name
    pub backend: Option<String>,
}

impl std::fmt::Display for ScopeRequiredError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "At least one of 'user_id', 'agent_id', or 'run_id' must be provided{}",
            self.backend
                .as_ref()
                .map(|b| format!(" for {} backend", b))
                .unwrap_or_default()
        )
    }
}

impl std::error::Error for ScopeRequiredError {}

// =============================================================================
// TESTS
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_document_creation() {
        let doc = Document::new("Test content")
            .source("test.txt")
            .metadata("key", "value");

        assert!(!doc.id.is_empty());
        assert_eq!(doc.content, "Test content");
        assert_eq!(doc.source, Some("test.txt".to_string()));
        assert_eq!(doc.metadata.get("key"), Some(&"value".to_string()));
    }

    #[test]
    fn test_search_result_item() {
        let item = SearchResultItem::new("id1", "text", 0.95);
        assert_eq!(item.id, "id1");
        assert_eq!(item.text, "text");
        assert_eq!(item.score, 0.95);
    }

    #[test]
    fn test_search_result() {
        let items = vec![
            SearchResultItem::new("1", "text1", 0.9),
            SearchResultItem::new("2", "text2", 0.8),
        ];
        let result = SearchResult::new("query", items);

        assert_eq!(result.query, "query");
        assert_eq!(result.len(), 2);
        assert!(!result.is_empty());
    }

    #[test]
    fn test_add_result() {
        let success = AddResult::success("id123");
        assert!(success.success);
        assert_eq!(success.id, "id123");

        let failure = AddResult::failure("Something went wrong");
        assert!(!failure.success);
        assert_eq!(failure.message, "Something went wrong");
    }

    #[tokio::test]
    async fn test_in_memory_vector_store() {
        let mut store = InMemoryVectorStore::new();

        let record = VectorRecord::new("1", "test text", vec![1.0, 0.0, 0.0]);
        store.add(record).await.unwrap();

        assert_eq!(store.len(), 1);

        let results = store.search(&[1.0, 0.0, 0.0], 10).await.unwrap();
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].id, "1");

        let record = store.get("1").await.unwrap();
        assert!(record.is_some());

        store.delete("1").await.unwrap();
        assert!(store.is_empty());
    }

    #[tokio::test]
    async fn test_simple_reranker() {
        let reranker = SimpleReranker::new();
        let items = vec![
            SearchResultItem::new("1", "text1", 0.5),
            SearchResultItem::new("2", "text2", 0.9),
            SearchResultItem::new("3", "text3", 0.7),
        ];

        let result = reranker.rerank("query", items, 2).await.unwrap();
        assert_eq!(result.items.len(), 2);
        assert_eq!(result.items[0].id, "2"); // Highest score first
        assert_eq!(result.items[1].id, "3");
    }

    #[test]
    fn test_chunking_fixed_size() {
        let config = ChunkingConfig {
            chunk_size: 10,
            chunk_overlap: 2,
            strategy: ChunkingStrategy::FixedSize,
        };
        let chunking = Chunking::new(config);
        let chunks = chunking.chunk("Hello world, this is a test");

        assert!(!chunks.is_empty());
    }

    #[test]
    fn test_chunking_by_sentence() {
        let config = ChunkingConfig {
            chunk_size: 100,
            chunk_overlap: 0,
            strategy: ChunkingStrategy::Sentence,
        };
        let chunking = Chunking::new(config);
        let chunks = chunking.chunk("First sentence. Second sentence! Third sentence?");

        assert_eq!(chunks.len(), 3);
    }

    #[test]
    fn test_knowledge_config() {
        let config = KnowledgeConfig::new()
            .default_limit(20)
            .enable_reranking(true)
            .user_id("user123");

        assert_eq!(config.default_limit, 20);
        assert!(config.enable_reranking);
        assert_eq!(config.user_id, Some("user123".to_string()));
    }

    #[test]
    fn test_knowledge_builder() {
        let knowledge = Knowledge::new()
            .config(KnowledgeConfig::new().default_limit(5))
            .build()
            .unwrap();

        assert_eq!(knowledge.config.default_limit, 5);
        assert!(knowledge.is_empty());
    }

    #[test]
    fn test_knowledge_add_and_search() {
        let mut knowledge = Knowledge::new().build().unwrap();

        knowledge.add("Hello world", None).unwrap();
        knowledge.add("Goodbye world", None).unwrap();

        let results = knowledge.search("hello", 10).unwrap();
        assert_eq!(results.len(), 1);
        assert!(results.results[0].text.contains("Hello"));
    }

    #[test]
    fn test_knowledge_delete() {
        let mut knowledge = Knowledge::new().build().unwrap();

        let result = knowledge.add("Test content", None).unwrap();
        assert_eq!(knowledge.len(), 1);

        knowledge.delete(&result.id);
        assert!(knowledge.is_empty());
    }

    #[test]
    fn test_cosine_similarity() {
        let a = vec![1.0, 0.0, 0.0];
        let b = vec![1.0, 0.0, 0.0];
        let sim = InMemoryVectorStore::cosine_similarity(&a, &b);
        assert!((sim - 1.0).abs() < 0.001);

        let c = vec![0.0, 1.0, 0.0];
        let sim2 = InMemoryVectorStore::cosine_similarity(&a, &c);
        assert!(sim2.abs() < 0.001);
    }
}
