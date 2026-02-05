//! Embedding Module for PraisonAI Rust SDK
//!
//! Provides text embedding capabilities with support for multiple providers.
//!
//! # Example
//!
//! ```rust,ignore
//! use praisonai::{EmbeddingAgent, EmbeddingConfig};
//!
//! let agent = EmbeddingAgent::new()
//!     .model("text-embedding-3-small")
//!     .build()?;
//!
//! let embedding = agent.embed("Hello world").await?;
//! println!("Dimension: {}", embedding.len());
//! ```

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;

use crate::error::{Error, Result};

/// Configuration for embedding generation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EmbeddingConfig {
    /// Number of dimensions for the embedding (model-dependent)
    pub dimensions: Option<usize>,
    /// Encoding format: "float" or "base64"
    pub encoding_format: String,
    /// Timeout in seconds
    pub timeout: u64,
    /// Custom API base URL
    pub api_base: Option<String>,
    /// API key for authentication
    pub api_key: Option<String>,
}

impl Default for EmbeddingConfig {
    fn default() -> Self {
        Self {
            dimensions: None,
            encoding_format: "float".to_string(),
            timeout: 60,
            api_base: None,
            api_key: None,
        }
    }
}

impl EmbeddingConfig {
    /// Create a new EmbeddingConfig with defaults
    pub fn new() -> Self {
        Self::default()
    }

    /// Set dimensions
    pub fn dimensions(mut self, dimensions: usize) -> Self {
        self.dimensions = Some(dimensions);
        self
    }

    /// Set encoding format
    pub fn encoding_format(mut self, format: impl Into<String>) -> Self {
        self.encoding_format = format.into();
        self
    }

    /// Set timeout
    pub fn timeout(mut self, timeout: u64) -> Self {
        self.timeout = timeout;
        self
    }

    /// Set API base URL
    pub fn api_base(mut self, url: impl Into<String>) -> Self {
        self.api_base = Some(url.into());
        self
    }

    /// Set API key
    pub fn api_key(mut self, key: impl Into<String>) -> Self {
        self.api_key = Some(key.into());
        self
    }
}

/// Result of an embedding operation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EmbeddingResult {
    /// The embedding vectors
    pub embeddings: Vec<Vec<f32>>,
    /// Model used for embedding
    pub model: String,
    /// Token usage information
    pub usage: EmbeddingUsage,
}

impl EmbeddingResult {
    /// Get the first embedding vector
    pub fn first(&self) -> Option<&Vec<f32>> {
        self.embeddings.first()
    }

    /// Get the number of embeddings
    pub fn len(&self) -> usize {
        self.embeddings.len()
    }

    /// Check if empty
    pub fn is_empty(&self) -> bool {
        self.embeddings.is_empty()
    }

    /// Get embedding dimension
    pub fn dimension(&self) -> usize {
        self.embeddings.first().map(|e| e.len()).unwrap_or(0)
    }
}

/// Token usage for embedding operations.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct EmbeddingUsage {
    /// Number of prompt tokens
    pub prompt_tokens: u32,
    /// Total tokens used
    pub total_tokens: u32,
}

/// Similarity search result.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SimilarityResult {
    /// The text that was compared
    pub text: String,
    /// Similarity score (0.0 to 1.0)
    pub score: f32,
    /// Index in the original list
    pub index: usize,
}

/// Builder for EmbeddingAgent.
#[derive(Debug, Clone)]
pub struct EmbeddingAgentBuilder {
    name: String,
    model: String,
    config: EmbeddingConfig,
    verbose: bool,
}

impl Default for EmbeddingAgentBuilder {
    fn default() -> Self {
        Self::new()
    }
}

impl EmbeddingAgentBuilder {
    /// Create a new builder
    pub fn new() -> Self {
        Self {
            name: "EmbeddingAgent".to_string(),
            model: std::env::var("PRAISONAI_EMBEDDING_MODEL")
                .unwrap_or_else(|_| "text-embedding-3-small".to_string()),
            config: EmbeddingConfig::default(),
            verbose: true,
        }
    }

    /// Set agent name
    pub fn name(mut self, name: impl Into<String>) -> Self {
        self.name = name.into();
        self
    }

    /// Set model name
    pub fn model(mut self, model: impl Into<String>) -> Self {
        self.model = model.into();
        self
    }

    /// Set embedding config
    pub fn config(mut self, config: EmbeddingConfig) -> Self {
        self.config = config;
        self
    }

    /// Set verbose mode
    pub fn verbose(mut self, verbose: bool) -> Self {
        self.verbose = verbose;
        self
    }

    /// Set API key
    pub fn api_key(mut self, key: impl Into<String>) -> Self {
        self.config.api_key = Some(key.into());
        self
    }

    /// Set API base URL
    pub fn api_base(mut self, url: impl Into<String>) -> Self {
        self.config.api_base = Some(url.into());
        self
    }

    /// Build the EmbeddingAgent
    pub fn build(self) -> Result<EmbeddingAgent> {
        Ok(EmbeddingAgent {
            name: self.name,
            model: self.model,
            config: self.config,
            verbose: self.verbose,
        })
    }
}

/// Agent for generating text embeddings.
///
/// Provides embedding capabilities for text using AI embedding models,
/// with support for batch processing and similarity calculations.
///
/// # Supported Providers
///
/// - OpenAI: `text-embedding-3-small`, `text-embedding-3-large`, `text-embedding-ada-002`
/// - Azure: `azure/text-embedding-3-small`
/// - Cohere: `cohere/embed-english-v3.0`
/// - Voyage: `voyage/voyage-3`
/// - Mistral: `mistral/mistral-embed`
#[derive(Debug, Clone)]
pub struct EmbeddingAgent {
    /// Agent name
    pub name: String,
    /// Model name
    pub model: String,
    /// Embedding configuration
    pub config: EmbeddingConfig,
    /// Verbose output
    pub verbose: bool,
}

impl EmbeddingAgent {
    /// Create a new builder
    pub fn new() -> EmbeddingAgentBuilder {
        EmbeddingAgentBuilder::new()
    }

    /// Create a simple embedding agent with default settings
    pub fn simple() -> Result<Self> {
        Self::new().build()
    }

    /// Generate embedding for a single text.
    ///
    /// # Arguments
    ///
    /// * `text` - Text to embed
    ///
    /// # Returns
    ///
    /// Vector of floats representing the embedding
    pub async fn embed(&self, text: &str) -> Result<Vec<f32>> {
        let result = self.embed_batch(&[text]).await?;
        result
            .embeddings
            .into_iter()
            .next()
            .ok_or_else(|| Error::Embedding("No embedding returned".to_string()))
    }

    /// Generate embeddings for multiple texts.
    ///
    /// # Arguments
    ///
    /// * `texts` - Slice of texts to embed
    ///
    /// # Returns
    ///
    /// EmbeddingResult containing all embeddings
    pub async fn embed_batch(&self, texts: &[&str]) -> Result<EmbeddingResult> {
        if texts.is_empty() {
            return Ok(EmbeddingResult {
                embeddings: vec![],
                model: self.model.clone(),
                usage: EmbeddingUsage::default(),
            });
        }

        // Get API key from config or environment
        let api_key = self
            .config
            .api_key
            .clone()
            .or_else(|| std::env::var("OPENAI_API_KEY").ok())
            .ok_or_else(|| Error::Config("No API key provided for embeddings".to_string()))?;

        // Build API URL
        let api_base = self
            .config
            .api_base
            .clone()
            .unwrap_or_else(|| "https://api.openai.com/v1".to_string());
        let url = format!("{}/embeddings", api_base);

        // Build request body
        let mut body = serde_json::json!({
            "model": self.model,
            "input": texts,
        });

        if let Some(dims) = self.config.dimensions {
            body["dimensions"] = serde_json::json!(dims);
        }

        if self.config.encoding_format != "float" {
            body["encoding_format"] = serde_json::json!(self.config.encoding_format);
        }

        // Make HTTP request
        let client = reqwest::Client::new();
        let response = client
            .post(&url)
            .header("Authorization", format!("Bearer {}", api_key))
            .header("Content-Type", "application/json")
            .timeout(std::time::Duration::from_secs(self.config.timeout))
            .json(&body)
            .send()
            .await
            .map_err(|e| Error::Embedding(format!("HTTP request failed: {}", e)))?;

        if !response.status().is_success() {
            let status = response.status();
            let text = response
                .text()
                .await
                .unwrap_or_else(|_| "Unknown error".to_string());
            return Err(Error::Embedding(format!(
                "API request failed ({}): {}",
                status, text
            )));
        }

        // Parse response
        let response_json: serde_json::Value = response
            .json()
            .await
            .map_err(|e| Error::Embedding(format!("Failed to parse response: {}", e)))?;

        // Extract embeddings
        let data = response_json["data"]
            .as_array()
            .ok_or_else(|| Error::Embedding("Invalid response format".to_string()))?;

        let embeddings: Vec<Vec<f32>> = data
            .iter()
            .map(|item| {
                item["embedding"]
                    .as_array()
                    .map(|arr| {
                        arr.iter()
                            .filter_map(|v| v.as_f64().map(|f| f as f32))
                            .collect()
                    })
                    .unwrap_or_default()
            })
            .collect();

        // Extract usage
        let usage = EmbeddingUsage {
            prompt_tokens: response_json["usage"]["prompt_tokens"]
                .as_u64()
                .unwrap_or(0) as u32,
            total_tokens: response_json["usage"]["total_tokens"]
                .as_u64()
                .unwrap_or(0) as u32,
        };

        Ok(EmbeddingResult {
            embeddings,
            model: self.model.clone(),
            usage,
        })
    }

    /// Calculate cosine similarity between two texts.
    ///
    /// # Arguments
    ///
    /// * `text1` - First text
    /// * `text2` - Second text
    ///
    /// # Returns
    ///
    /// Cosine similarity score (0.0 to 1.0)
    pub async fn similarity(&self, text1: &str, text2: &str) -> Result<f32> {
        let result = self.embed_batch(&[text1, text2]).await?;
        if result.embeddings.len() < 2 {
            return Err(Error::Embedding(
                "Not enough embeddings returned".to_string(),
            ));
        }
        Ok(cosine_similarity(&result.embeddings[0], &result.embeddings[1]))
    }

    /// Find the most similar texts to a query.
    ///
    /// # Arguments
    ///
    /// * `query` - Query text
    /// * `candidates` - List of candidate texts to compare
    /// * `top_k` - Number of top results to return
    ///
    /// # Returns
    ///
    /// List of SimilarityResult sorted by score (descending)
    pub async fn find_most_similar(
        &self,
        query: &str,
        candidates: &[&str],
        top_k: usize,
    ) -> Result<Vec<SimilarityResult>> {
        if candidates.is_empty() {
            return Ok(vec![]);
        }

        // Embed query and all candidates together
        let mut all_texts: Vec<&str> = vec![query];
        all_texts.extend(candidates);

        let result = self.embed_batch(&all_texts).await?;
        if result.embeddings.is_empty() {
            return Ok(vec![]);
        }

        let query_embedding = &result.embeddings[0];
        let candidate_embeddings = &result.embeddings[1..];

        // Calculate similarities
        let mut scores: Vec<SimilarityResult> = candidate_embeddings
            .iter()
            .enumerate()
            .map(|(i, emb)| SimilarityResult {
                text: candidates[i].to_string(),
                score: cosine_similarity(query_embedding, emb),
                index: i,
            })
            .collect();

        // Sort by score descending
        scores.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap_or(std::cmp::Ordering::Equal));

        // Return top_k
        scores.truncate(top_k);
        Ok(scores)
    }
}

impl Default for EmbeddingAgent {
    fn default() -> Self {
        Self::new().build().expect("Failed to build default EmbeddingAgent")
    }
}

/// Calculate cosine similarity between two vectors.
pub fn cosine_similarity(vec1: &[f32], vec2: &[f32]) -> f32 {
    if vec1.len() != vec2.len() || vec1.is_empty() {
        return 0.0;
    }

    let dot_product: f32 = vec1.iter().zip(vec2.iter()).map(|(a, b)| a * b).sum();
    let norm1: f32 = vec1.iter().map(|x| x * x).sum::<f32>().sqrt();
    let norm2: f32 = vec2.iter().map(|x| x * x).sum::<f32>().sqrt();

    if norm1 == 0.0 || norm2 == 0.0 {
        return 0.0;
    }

    dot_product / (norm1 * norm2)
}

/// Get embedding dimensions for a model.
pub fn get_dimensions(model: &str) -> Option<usize> {
    match model {
        "text-embedding-3-small" => Some(1536),
        "text-embedding-3-large" => Some(3072),
        "text-embedding-ada-002" => Some(1536),
        "cohere/embed-english-v3.0" => Some(1024),
        "cohere/embed-multilingual-v3.0" => Some(1024),
        "voyage/voyage-3" => Some(1024),
        "voyage/voyage-3-lite" => Some(512),
        "mistral/mistral-embed" => Some(1024),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_embedding_config_default() {
        let config = EmbeddingConfig::default();
        assert_eq!(config.encoding_format, "float");
        assert_eq!(config.timeout, 60);
        assert!(config.dimensions.is_none());
    }

    #[test]
    fn test_embedding_config_builder() {
        let config = EmbeddingConfig::new()
            .dimensions(1536)
            .timeout(30)
            .api_key("test-key");

        assert_eq!(config.dimensions, Some(1536));
        assert_eq!(config.timeout, 30);
        assert_eq!(config.api_key, Some("test-key".to_string()));
    }

    #[test]
    fn test_embedding_agent_builder() {
        let agent = EmbeddingAgent::new()
            .name("TestAgent")
            .model("text-embedding-3-small")
            .verbose(false)
            .build()
            .unwrap();

        assert_eq!(agent.name, "TestAgent");
        assert_eq!(agent.model, "text-embedding-3-small");
        assert!(!agent.verbose);
    }

    #[test]
    fn test_cosine_similarity() {
        let vec1 = vec![1.0, 0.0, 0.0];
        let vec2 = vec![1.0, 0.0, 0.0];
        assert!((cosine_similarity(&vec1, &vec2) - 1.0).abs() < 0.001);

        let vec3 = vec![0.0, 1.0, 0.0];
        assert!((cosine_similarity(&vec1, &vec3)).abs() < 0.001);

        let vec4 = vec![0.707, 0.707, 0.0];
        let sim = cosine_similarity(&vec1, &vec4);
        assert!(sim > 0.7 && sim < 0.71);
    }

    #[test]
    fn test_cosine_similarity_empty() {
        let empty: Vec<f32> = vec![];
        assert_eq!(cosine_similarity(&empty, &empty), 0.0);
    }

    #[test]
    fn test_cosine_similarity_different_lengths() {
        let vec1 = vec![1.0, 0.0];
        let vec2 = vec![1.0, 0.0, 0.0];
        assert_eq!(cosine_similarity(&vec1, &vec2), 0.0);
    }

    #[test]
    fn test_get_dimensions() {
        assert_eq!(get_dimensions("text-embedding-3-small"), Some(1536));
        assert_eq!(get_dimensions("text-embedding-3-large"), Some(3072));
        assert_eq!(get_dimensions("unknown-model"), None);
    }

    #[test]
    fn test_embedding_result() {
        let result = EmbeddingResult {
            embeddings: vec![vec![1.0, 2.0, 3.0], vec![4.0, 5.0, 6.0]],
            model: "test".to_string(),
            usage: EmbeddingUsage::default(),
        };

        assert_eq!(result.len(), 2);
        assert!(!result.is_empty());
        assert_eq!(result.dimension(), 3);
        assert_eq!(result.first(), Some(&vec![1.0, 2.0, 3.0]));
    }

    #[test]
    fn test_similarity_result() {
        let result = SimilarityResult {
            text: "test".to_string(),
            score: 0.95,
            index: 0,
        };

        assert_eq!(result.text, "test");
        assert_eq!(result.score, 0.95);
        assert_eq!(result.index, 0);
    }
}
