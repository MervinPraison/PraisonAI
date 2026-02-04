//! Error types for PraisonAI Core
//!
//! This module defines the error types used throughout the crate.

use thiserror::Error;

/// Result type alias using our Error type
pub type Result<T> = std::result::Result<T, Error>;

/// Main error type for PraisonAI Core
#[derive(Error, Debug)]
pub enum Error {
    /// Agent-related errors
    #[error("Agent error: {0}")]
    Agent(String),
    
    /// Tool execution errors
    #[error("Tool error: {0}")]
    Tool(String),
    
    /// LLM provider errors
    #[error("LLM error: {0}")]
    Llm(String),
    
    /// Memory errors
    #[error("Memory error: {0}")]
    Memory(String),
    
    /// Workflow errors
    #[error("Workflow error: {0}")]
    Workflow(String),
    
    /// Configuration errors
    #[error("Config error: {0}")]
    Config(String),
    
    /// Serialization/deserialization errors
    #[error("Serialization error: {0}")]
    Serialization(#[from] serde_json::Error),
    
    /// YAML parsing errors
    #[error("YAML error: {0}")]
    Yaml(#[from] serde_yaml::Error),
    
    /// HTTP request errors
    #[error("HTTP error: {0}")]
    Http(#[from] reqwest::Error),
    
    /// IO errors
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
    
    /// Generic error with context
    #[error("{context}: {source}")]
    WithContext {
        context: String,
        #[source]
        source: Box<Error>,
    },
}

impl Error {
    /// Create an agent error
    pub fn agent(msg: impl Into<String>) -> Self {
        Self::Agent(msg.into())
    }
    
    /// Create a tool error
    pub fn tool(msg: impl Into<String>) -> Self {
        Self::Tool(msg.into())
    }
    
    /// Create an LLM error
    pub fn llm(msg: impl Into<String>) -> Self {
        Self::Llm(msg.into())
    }
    
    /// Create a memory error
    pub fn memory(msg: impl Into<String>) -> Self {
        Self::Memory(msg.into())
    }
    
    /// Create a workflow error
    pub fn workflow(msg: impl Into<String>) -> Self {
        Self::Workflow(msg.into())
    }
    
    /// Create a config error
    pub fn config(msg: impl Into<String>) -> Self {
        Self::Config(msg.into())
    }
    
    /// Add context to an error
    pub fn with_context(self, context: impl Into<String>) -> Self {
        Self::WithContext {
            context: context.into(),
            source: Box::new(self),
        }
    }
}

/// Extension trait for adding context to Results
pub trait ResultExt<T> {
    /// Add context to an error
    fn context(self, context: impl Into<String>) -> Result<T>;
}

impl<T> ResultExt<T> for Result<T> {
    fn context(self, context: impl Into<String>) -> Result<T> {
        self.map_err(|e| e.with_context(context))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_error_display() {
        let err = Error::agent("test error");
        assert_eq!(err.to_string(), "Agent error: test error");
    }
    
    #[test]
    fn test_error_with_context() {
        let err = Error::tool("failed to execute").with_context("search_web");
        assert!(err.to_string().contains("search_web"));
    }
}
