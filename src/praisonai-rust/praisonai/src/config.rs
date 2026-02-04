//! Configuration types for PraisonAI
//!
//! This module provides configuration structs for various features.
//! Follows the Python SDK pattern of XConfig naming convention.

use serde::{Deserialize, Serialize};

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

fn default_true() -> bool { true }
fn default_memory_provider() -> String { "memory".to_string() }
fn default_max_messages() -> usize { 100 }

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

fn default_output_mode() -> String { "verbose".to_string() }

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

fn default_max_iterations() -> usize { 10 }
fn default_timeout() -> u64 { 300 }

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
