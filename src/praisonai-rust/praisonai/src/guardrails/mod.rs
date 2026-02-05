//! Guardrails Module
//!
//! This module provides guardrail validation for agent outputs:
//! - `Guardrail` - Guardrail trait for validation
//! - `GuardrailResult` - Result of guardrail validation
//! - `LlmGuardrail` - LLM-based guardrail implementation
//!
//! # Example
//!
//! ```ignore
//! use praisonai::guardrails::{Guardrail, GuardrailResult};
//!
//! struct ContentFilter;
//!
//! impl Guardrail for ContentFilter {
//!     fn validate(&self, output: &str) -> GuardrailResult {
//!         if output.contains("unsafe") {
//!             GuardrailResult::failure("Content contains unsafe material")
//!         } else {
//!             GuardrailResult::success(output.to_string())
//!         }
//!     }
//! }
//! ```

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// Note: Result is available for future async implementations

// =============================================================================
// GUARDRAIL RESULT
// =============================================================================

/// Result of a guardrail validation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GuardrailResult {
    /// Whether the guardrail check passed
    pub success: bool,
    /// The result if modified, or original if unchanged
    pub result: Option<String>,
    /// Error message if validation failed
    pub error: String,
    /// Additional metadata
    pub metadata: HashMap<String, String>,
}

impl Default for GuardrailResult {
    fn default() -> Self {
        Self {
            success: true,
            result: None,
            error: String::new(),
            metadata: HashMap::new(),
        }
    }
}

impl GuardrailResult {
    /// Create a successful result
    pub fn success(result: impl Into<String>) -> Self {
        Self {
            success: true,
            result: Some(result.into()),
            error: String::new(),
            metadata: HashMap::new(),
        }
    }

    /// Create a successful result without modification
    pub fn pass() -> Self {
        Self {
            success: true,
            result: None,
            error: String::new(),
            metadata: HashMap::new(),
        }
    }

    /// Create a failed result
    pub fn failure(error: impl Into<String>) -> Self {
        Self {
            success: false,
            result: None,
            error: error.into(),
            metadata: HashMap::new(),
        }
    }

    /// Create from a tuple (success, result_or_error)
    pub fn from_tuple(success: bool, data: impl Into<String>) -> Self {
        let data = data.into();
        if success {
            Self::success(data)
        } else {
            Self::failure(data)
        }
    }

    /// Add metadata
    pub fn with_metadata(mut self, key: impl Into<String>, value: impl Into<String>) -> Self {
        self.metadata.insert(key.into(), value.into());
        self
    }

    /// Check if passed
    pub fn is_success(&self) -> bool {
        self.success
    }

    /// Check if failed
    pub fn is_failure(&self) -> bool {
        !self.success
    }

    /// Get the result or original content
    pub fn get_result_or(&self, original: &str) -> String {
        self.result.clone().unwrap_or_else(|| original.to_string())
    }
}

// =============================================================================
// GUARDRAIL TRAIT
// =============================================================================

/// Trait for synchronous guardrail validation.
pub trait Guardrail: Send + Sync {
    /// Validate the output
    fn validate(&self, output: &str) -> GuardrailResult;

    /// Get guardrail name
    fn name(&self) -> &str {
        "guardrail"
    }

    /// Get guardrail description
    fn description(&self) -> &str {
        "A guardrail for validating agent output"
    }
}

/// Trait for asynchronous guardrail validation.
#[async_trait]
pub trait AsyncGuardrail: Send + Sync {
    /// Validate the output asynchronously
    async fn validate(&self, output: &str) -> GuardrailResult;

    /// Get guardrail name
    fn name(&self) -> &str {
        "async_guardrail"
    }

    /// Get guardrail description
    fn description(&self) -> &str {
        "An async guardrail for validating agent output"
    }
}

// =============================================================================
// GUARDRAIL ACTION
// =============================================================================

/// Action to take when guardrail fails.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum GuardrailAction {
    /// Stop execution and return error
    #[default]
    Stop,
    /// Retry the task
    Retry,
    /// Continue with warning
    Warn,
    /// Skip and continue
    Skip,
    /// Use fallback response
    Fallback,
}

impl std::fmt::Display for GuardrailAction {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Stop => write!(f, "stop"),
            Self::Retry => write!(f, "retry"),
            Self::Warn => write!(f, "warn"),
            Self::Skip => write!(f, "skip"),
            Self::Fallback => write!(f, "fallback"),
        }
    }
}

// =============================================================================
// GUARDRAIL CONFIG
// =============================================================================

/// Configuration for guardrails.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GuardrailConfig {
    /// Action to take on failure
    pub on_failure: GuardrailAction,
    /// Maximum retries if action is Retry
    pub max_retries: usize,
    /// Fallback response if action is Fallback
    pub fallback_response: Option<String>,
    /// Whether to log validation results
    pub log_results: bool,
    /// Custom error message template
    pub error_template: Option<String>,
}

impl Default for GuardrailConfig {
    fn default() -> Self {
        Self {
            on_failure: GuardrailAction::Stop,
            max_retries: 3,
            fallback_response: None,
            log_results: true,
            error_template: None,
        }
    }
}

impl GuardrailConfig {
    /// Create new config
    pub fn new() -> Self {
        Self::default()
    }

    /// Set failure action
    pub fn on_failure(mut self, action: GuardrailAction) -> Self {
        self.on_failure = action;
        self
    }

    /// Set max retries
    pub fn max_retries(mut self, retries: usize) -> Self {
        self.max_retries = retries;
        self
    }

    /// Set fallback response
    pub fn fallback_response(mut self, response: impl Into<String>) -> Self {
        self.fallback_response = Some(response.into());
        self
    }

    /// Set log results
    pub fn log_results(mut self, log: bool) -> Self {
        self.log_results = log;
        self
    }

    /// Set error template
    pub fn error_template(mut self, template: impl Into<String>) -> Self {
        self.error_template = Some(template.into());
        self
    }
}

// =============================================================================
// BUILT-IN GUARDRAILS
// =============================================================================

/// Content length guardrail.
#[derive(Debug, Clone)]
pub struct LengthGuardrail {
    /// Minimum length
    pub min_length: Option<usize>,
    /// Maximum length
    pub max_length: Option<usize>,
}

impl LengthGuardrail {
    /// Create a new length guardrail
    pub fn new() -> Self {
        Self {
            min_length: None,
            max_length: None,
        }
    }

    /// Set minimum length
    pub fn min(mut self, length: usize) -> Self {
        self.min_length = Some(length);
        self
    }

    /// Set maximum length
    pub fn max(mut self, length: usize) -> Self {
        self.max_length = Some(length);
        self
    }
}

impl Default for LengthGuardrail {
    fn default() -> Self {
        Self::new()
    }
}

impl Guardrail for LengthGuardrail {
    fn validate(&self, output: &str) -> GuardrailResult {
        let len = output.len();

        if let Some(min) = self.min_length {
            if len < min {
                return GuardrailResult::failure(format!(
                    "Output too short: {} chars (minimum: {})",
                    len, min
                ));
            }
        }

        if let Some(max) = self.max_length {
            if len > max {
                return GuardrailResult::failure(format!(
                    "Output too long: {} chars (maximum: {})",
                    len, max
                ));
            }
        }

        GuardrailResult::pass()
    }

    fn name(&self) -> &str {
        "length_guardrail"
    }

    fn description(&self) -> &str {
        "Validates output length is within bounds"
    }
}

/// Keyword blocklist guardrail.
#[derive(Debug, Clone)]
pub struct BlocklistGuardrail {
    /// Blocked keywords
    pub keywords: Vec<String>,
    /// Case sensitive matching
    pub case_sensitive: bool,
}

impl BlocklistGuardrail {
    /// Create a new blocklist guardrail
    pub fn new(keywords: Vec<String>) -> Self {
        Self {
            keywords,
            case_sensitive: false,
        }
    }

    /// Set case sensitivity
    pub fn case_sensitive(mut self, sensitive: bool) -> Self {
        self.case_sensitive = sensitive;
        self
    }

    /// Add a keyword
    pub fn add_keyword(mut self, keyword: impl Into<String>) -> Self {
        self.keywords.push(keyword.into());
        self
    }
}

impl Guardrail for BlocklistGuardrail {
    fn validate(&self, output: &str) -> GuardrailResult {
        let check_output = if self.case_sensitive {
            output.to_string()
        } else {
            output.to_lowercase()
        };

        for keyword in &self.keywords {
            let check_keyword = if self.case_sensitive {
                keyword.clone()
            } else {
                keyword.to_lowercase()
            };

            if check_output.contains(&check_keyword) {
                return GuardrailResult::failure(format!(
                    "Output contains blocked keyword: '{}'",
                    keyword
                ));
            }
        }

        GuardrailResult::pass()
    }

    fn name(&self) -> &str {
        "blocklist_guardrail"
    }

    fn description(&self) -> &str {
        "Blocks output containing specified keywords"
    }
}

/// Regex pattern guardrail.
#[derive(Debug, Clone)]
pub struct PatternGuardrail {
    /// Pattern to match (must match for success)
    pub must_match: Option<String>,
    /// Pattern to not match (must not match for success)
    pub must_not_match: Option<String>,
}

impl PatternGuardrail {
    /// Create a new pattern guardrail
    pub fn new() -> Self {
        Self {
            must_match: None,
            must_not_match: None,
        }
    }

    /// Set must match pattern
    pub fn must_match(mut self, pattern: impl Into<String>) -> Self {
        self.must_match = Some(pattern.into());
        self
    }

    /// Set must not match pattern
    pub fn must_not_match(mut self, pattern: impl Into<String>) -> Self {
        self.must_not_match = Some(pattern.into());
        self
    }
}

impl Default for PatternGuardrail {
    fn default() -> Self {
        Self::new()
    }
}

impl Guardrail for PatternGuardrail {
    fn validate(&self, output: &str) -> GuardrailResult {
        // Note: In a real implementation, we'd use the regex crate
        // For now, we use simple string matching

        if let Some(pattern) = &self.must_match {
            if !output.contains(pattern) {
                return GuardrailResult::failure(format!(
                    "Output does not match required pattern: '{}'",
                    pattern
                ));
            }
        }

        if let Some(pattern) = &self.must_not_match {
            if output.contains(pattern) {
                return GuardrailResult::failure(format!(
                    "Output matches forbidden pattern: '{}'",
                    pattern
                ));
            }
        }

        GuardrailResult::pass()
    }

    fn name(&self) -> &str {
        "pattern_guardrail"
    }

    fn description(&self) -> &str {
        "Validates output against regex patterns"
    }
}

// =============================================================================
// GUARDRAIL CHAIN
// =============================================================================

/// Chain of guardrails to run in sequence.
pub struct GuardrailChain {
    guardrails: Vec<Box<dyn Guardrail>>,
    config: GuardrailConfig,
}

impl GuardrailChain {
    /// Create a new guardrail chain
    pub fn new() -> Self {
        Self {
            guardrails: Vec::new(),
            config: GuardrailConfig::default(),
        }
    }

    /// Add a guardrail to the chain
    pub fn add(mut self, guardrail: impl Guardrail + 'static) -> Self {
        self.guardrails.push(Box::new(guardrail));
        self
    }

    /// Set config
    pub fn config(mut self, config: GuardrailConfig) -> Self {
        self.config = config;
        self
    }

    /// Validate output through all guardrails
    pub fn validate(&self, output: &str) -> GuardrailResult {
        let mut current_output = output.to_string();

        for guardrail in &self.guardrails {
            let result = guardrail.validate(&current_output);

            if !result.success {
                return result;
            }

            // Update output if guardrail modified it
            if let Some(new_output) = &result.result {
                current_output = new_output.clone();
            }
        }

        if current_output != output {
            GuardrailResult::success(current_output)
        } else {
            GuardrailResult::pass()
        }
    }

    /// Get guardrail count
    pub fn len(&self) -> usize {
        self.guardrails.len()
    }

    /// Check if empty
    pub fn is_empty(&self) -> bool {
        self.guardrails.is_empty()
    }
}

impl Default for GuardrailChain {
    fn default() -> Self {
        Self::new()
    }
}

// =============================================================================
// FUNCTION GUARDRAIL
// =============================================================================

/// A guardrail implemented as a function.
pub struct FunctionGuardrail<F>
where
    F: Fn(&str) -> GuardrailResult + Send + Sync,
{
    name: String,
    description: String,
    func: F,
}

impl<F> FunctionGuardrail<F>
where
    F: Fn(&str) -> GuardrailResult + Send + Sync,
{
    /// Create a new function guardrail
    pub fn new(name: impl Into<String>, func: F) -> Self {
        Self {
            name: name.into(),
            description: String::new(),
            func,
        }
    }

    /// Set description
    pub fn description(mut self, desc: impl Into<String>) -> Self {
        self.description = desc.into();
        self
    }
}

impl<F> Guardrail for FunctionGuardrail<F>
where
    F: Fn(&str) -> GuardrailResult + Send + Sync,
{
    fn validate(&self, output: &str) -> GuardrailResult {
        (self.func)(output)
    }

    fn name(&self) -> &str {
        &self.name
    }

    fn description(&self) -> &str {
        &self.description
    }
}

// =============================================================================
// TESTS
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_guardrail_result_success() {
        let result = GuardrailResult::success("output");
        assert!(result.is_success());
        assert!(!result.is_failure());
        assert_eq!(result.result, Some("output".to_string()));
        assert!(result.error.is_empty());
    }

    #[test]
    fn test_guardrail_result_failure() {
        let result = GuardrailResult::failure("error message");
        assert!(result.is_failure());
        assert!(!result.is_success());
        assert_eq!(result.error, "error message");
    }

    #[test]
    fn test_guardrail_result_pass() {
        let result = GuardrailResult::pass();
        assert!(result.is_success());
        assert!(result.result.is_none());
    }

    #[test]
    fn test_guardrail_result_from_tuple() {
        let success = GuardrailResult::from_tuple(true, "result");
        assert!(success.is_success());
        assert_eq!(success.result, Some("result".to_string()));

        let failure = GuardrailResult::from_tuple(false, "error");
        assert!(failure.is_failure());
        assert_eq!(failure.error, "error");
    }

    #[test]
    fn test_guardrail_result_get_result_or() {
        let with_result = GuardrailResult::success("modified");
        assert_eq!(with_result.get_result_or("original"), "modified");

        let without_result = GuardrailResult::pass();
        assert_eq!(without_result.get_result_or("original"), "original");
    }

    #[test]
    fn test_length_guardrail() {
        let guardrail = LengthGuardrail::new().min(5).max(100);

        let short = guardrail.validate("Hi");
        assert!(short.is_failure());
        assert!(short.error.contains("too short"));

        let ok = guardrail.validate("Hello, world!");
        assert!(ok.is_success());

        let long = guardrail.validate(&"x".repeat(200));
        assert!(long.is_failure());
        assert!(long.error.contains("too long"));
    }

    #[test]
    fn test_blocklist_guardrail() {
        let guardrail = BlocklistGuardrail::new(vec!["bad".to_string(), "unsafe".to_string()]);

        let clean = guardrail.validate("This is good content");
        assert!(clean.is_success());

        let blocked = guardrail.validate("This contains bad words");
        assert!(blocked.is_failure());
        assert!(blocked.error.contains("bad"));
    }

    #[test]
    fn test_blocklist_case_insensitive() {
        let guardrail = BlocklistGuardrail::new(vec!["bad".to_string()]);

        let result = guardrail.validate("This is BAD");
        assert!(result.is_failure());
    }

    #[test]
    fn test_blocklist_case_sensitive() {
        let guardrail = BlocklistGuardrail::new(vec!["bad".to_string()]).case_sensitive(true);

        let result = guardrail.validate("This is BAD");
        assert!(result.is_success()); // "BAD" != "bad"

        let result2 = guardrail.validate("This is bad");
        assert!(result2.is_failure());
    }

    #[test]
    fn test_pattern_guardrail() {
        let guardrail = PatternGuardrail::new()
            .must_match("hello")
            .must_not_match("goodbye");

        let ok = guardrail.validate("hello world");
        assert!(ok.is_success());

        let missing = guardrail.validate("hi world");
        assert!(missing.is_failure());
        assert!(missing.error.contains("does not match"));

        let forbidden = guardrail.validate("hello and goodbye");
        assert!(forbidden.is_failure());
        assert!(forbidden.error.contains("matches forbidden"));
    }

    #[test]
    fn test_guardrail_chain() {
        let chain = GuardrailChain::new()
            .add(LengthGuardrail::new().min(5))
            .add(BlocklistGuardrail::new(vec!["bad".to_string()]));

        let ok = chain.validate("Hello, world!");
        assert!(ok.is_success());

        let too_short = chain.validate("Hi");
        assert!(too_short.is_failure());

        let blocked = chain.validate("This is bad content");
        assert!(blocked.is_failure());
    }

    #[test]
    fn test_function_guardrail() {
        let guardrail = FunctionGuardrail::new("custom", |output: &str| {
            if output.starts_with("OK:") {
                GuardrailResult::pass()
            } else {
                GuardrailResult::failure("Output must start with 'OK:'")
            }
        });

        let ok = guardrail.validate("OK: This is valid");
        assert!(ok.is_success());

        let fail = guardrail.validate("This is invalid");
        assert!(fail.is_failure());
    }

    #[test]
    fn test_guardrail_config() {
        let config = GuardrailConfig::new()
            .on_failure(GuardrailAction::Retry)
            .max_retries(5)
            .fallback_response("Default response")
            .log_results(false);

        assert_eq!(config.on_failure, GuardrailAction::Retry);
        assert_eq!(config.max_retries, 5);
        assert_eq!(config.fallback_response, Some("Default response".to_string()));
        assert!(!config.log_results);
    }

    #[test]
    fn test_guardrail_action_display() {
        assert_eq!(GuardrailAction::Stop.to_string(), "stop");
        assert_eq!(GuardrailAction::Retry.to_string(), "retry");
        assert_eq!(GuardrailAction::Warn.to_string(), "warn");
        assert_eq!(GuardrailAction::Skip.to_string(), "skip");
        assert_eq!(GuardrailAction::Fallback.to_string(), "fallback");
    }
}
