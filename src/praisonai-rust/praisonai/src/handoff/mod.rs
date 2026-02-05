//! Handoff functionality for agent-to-agent delegation.
//!
//! This module provides handoff capabilities that allow agents to delegate tasks
//! to other agents, similar to the Python SDK implementation.
//!
//! # Features
//!
//! - **Handoff**: LLM-driven or programmatic agent-to-agent transfer
//! - **HandoffConfig**: Configuration for context policy, timeouts, safety
//! - **HandoffResult**: Result of a handoff operation
//! - **ContextPolicy**: Policy for context sharing during handoff
//!
//! # Example
//!
//! ```ignore
//! use praisonai::{Handoff, HandoffConfig, ContextPolicy};
//!
//! let config = HandoffConfig::new()
//!     .context_policy(ContextPolicy::Summary)
//!     .timeout_seconds(60.0)
//!     .detect_cycles(true);
//!
//! let handoff = Handoff::new(target_agent)
//!     .config(config)
//!     .tool_name("transfer_to_billing");
//! ```

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use crate::error::{Error, Result};

// =============================================================================
// CONTEXT POLICY
// =============================================================================

/// Policy for context sharing during handoff.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ContextPolicy {
    /// Share full conversation history
    Full,
    /// Share summarized context (default - safe)
    #[default]
    Summary,
    /// No context sharing
    None,
    /// Share last N messages
    LastN,
}

// =============================================================================
// HANDOFF CONFIG
// =============================================================================

/// Configuration for handoff behavior.
///
/// This consolidates all handoff-related settings including context policy,
/// timeouts, concurrency control, and safety features.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HandoffConfig {
    /// How to share context during handoff (default: summary for safety)
    #[serde(default)]
    pub context_policy: ContextPolicy,

    /// Maximum tokens to include in context
    #[serde(default = "default_max_context_tokens")]
    pub max_context_tokens: usize,

    /// Maximum messages to include (for LastN policy)
    #[serde(default = "default_max_context_messages")]
    pub max_context_messages: usize,

    /// Whether to preserve system messages in context
    #[serde(default = "default_true")]
    pub preserve_system: bool,

    /// Timeout for handoff execution in seconds
    #[serde(default = "default_timeout")]
    pub timeout_seconds: f64,

    /// Maximum concurrent handoffs (0 = unlimited)
    #[serde(default = "default_max_concurrent")]
    pub max_concurrent: usize,

    /// Enable cycle detection to prevent infinite loops
    #[serde(default = "default_true")]
    pub detect_cycles: bool,

    /// Maximum handoff chain depth
    #[serde(default = "default_max_depth")]
    pub max_depth: usize,

    /// Enable async execution
    #[serde(default)]
    pub async_mode: bool,
}

fn default_max_context_tokens() -> usize {
    4000
}

fn default_max_context_messages() -> usize {
    10
}

fn default_true() -> bool {
    true
}

fn default_timeout() -> f64 {
    300.0
}

fn default_max_concurrent() -> usize {
    3
}

fn default_max_depth() -> usize {
    10
}

impl Default for HandoffConfig {
    fn default() -> Self {
        Self {
            context_policy: ContextPolicy::Summary,
            max_context_tokens: 4000,
            max_context_messages: 10,
            preserve_system: true,
            timeout_seconds: 300.0,
            max_concurrent: 3,
            detect_cycles: true,
            max_depth: 10,
            async_mode: false,
        }
    }
}

impl HandoffConfig {
    /// Create a new handoff config with defaults
    pub fn new() -> Self {
        Self::default()
    }

    /// Set context policy
    pub fn context_policy(mut self, policy: ContextPolicy) -> Self {
        self.context_policy = policy;
        self
    }

    /// Set max context tokens
    pub fn max_context_tokens(mut self, tokens: usize) -> Self {
        self.max_context_tokens = tokens;
        self
    }

    /// Set max context messages
    pub fn max_context_messages(mut self, messages: usize) -> Self {
        self.max_context_messages = messages;
        self
    }

    /// Set preserve system messages
    pub fn preserve_system(mut self, preserve: bool) -> Self {
        self.preserve_system = preserve;
        self
    }

    /// Set timeout in seconds
    pub fn timeout_seconds(mut self, timeout: f64) -> Self {
        self.timeout_seconds = timeout;
        self
    }

    /// Set max concurrent handoffs
    pub fn max_concurrent(mut self, max: usize) -> Self {
        self.max_concurrent = max;
        self
    }

    /// Enable/disable cycle detection
    pub fn detect_cycles(mut self, detect: bool) -> Self {
        self.detect_cycles = detect;
        self
    }

    /// Set max handoff depth
    pub fn max_depth(mut self, depth: usize) -> Self {
        self.max_depth = depth;
        self
    }

    /// Enable async mode
    pub fn async_mode(mut self) -> Self {
        self.async_mode = true;
        self
    }

    /// Convert to dictionary/map
    pub fn to_map(&self) -> HashMap<String, serde_json::Value> {
        let mut map = HashMap::new();
        map.insert(
            "context_policy".to_string(),
            serde_json::to_value(&self.context_policy).unwrap_or_default(),
        );
        map.insert(
            "max_context_tokens".to_string(),
            serde_json::Value::Number(self.max_context_tokens.into()),
        );
        map.insert(
            "max_context_messages".to_string(),
            serde_json::Value::Number(self.max_context_messages.into()),
        );
        map.insert(
            "preserve_system".to_string(),
            serde_json::Value::Bool(self.preserve_system),
        );
        map.insert(
            "timeout_seconds".to_string(),
            serde_json::json!(self.timeout_seconds),
        );
        map.insert(
            "max_concurrent".to_string(),
            serde_json::Value::Number(self.max_concurrent.into()),
        );
        map.insert(
            "detect_cycles".to_string(),
            serde_json::Value::Bool(self.detect_cycles),
        );
        map.insert(
            "max_depth".to_string(),
            serde_json::Value::Number(self.max_depth.into()),
        );
        map.insert(
            "async_mode".to_string(),
            serde_json::Value::Bool(self.async_mode),
        );
        map
    }
}

// =============================================================================
// HANDOFF INPUT DATA
// =============================================================================

/// Data passed to a handoff target agent.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct HandoffInputData {
    /// Messages to pass to target agent
    pub messages: Vec<serde_json::Value>,
    /// Additional context data
    pub context: HashMap<String, serde_json::Value>,
    /// Name of the source agent
    pub source_agent: Option<String>,
    /// Current handoff depth
    pub handoff_depth: usize,
    /// Chain of agents in the handoff
    pub handoff_chain: Vec<String>,
}

impl HandoffInputData {
    /// Create new handoff input data
    pub fn new() -> Self {
        Self::default()
    }

    /// Set messages
    pub fn messages(mut self, messages: Vec<serde_json::Value>) -> Self {
        self.messages = messages;
        self
    }

    /// Add context
    pub fn context(mut self, key: impl Into<String>, value: serde_json::Value) -> Self {
        self.context.insert(key.into(), value);
        self
    }

    /// Set source agent
    pub fn source_agent(mut self, agent: impl Into<String>) -> Self {
        self.source_agent = Some(agent.into());
        self
    }
}

// =============================================================================
// HANDOFF RESULT
// =============================================================================

/// Result of a handoff operation.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HandoffResult {
    /// Whether the handoff succeeded
    pub success: bool,
    /// Response from target agent
    pub response: Option<String>,
    /// Name of the target agent
    pub target_agent: Option<String>,
    /// Name of the source agent
    pub source_agent: Option<String>,
    /// Duration of the handoff in seconds
    pub duration_seconds: f64,
    /// Error message if failed
    pub error: Option<String>,
    /// Handoff depth at completion
    pub handoff_depth: usize,
}

impl HandoffResult {
    /// Create a successful result
    pub fn success(response: impl Into<String>) -> Self {
        Self {
            success: true,
            response: Some(response.into()),
            target_agent: None,
            source_agent: None,
            duration_seconds: 0.0,
            error: None,
            handoff_depth: 0,
        }
    }

    /// Create a failed result
    pub fn failure(error: impl Into<String>) -> Self {
        Self {
            success: false,
            response: None,
            target_agent: None,
            source_agent: None,
            duration_seconds: 0.0,
            error: Some(error.into()),
            handoff_depth: 0,
        }
    }

    /// Set target agent
    pub fn with_target(mut self, agent: impl Into<String>) -> Self {
        self.target_agent = Some(agent.into());
        self
    }

    /// Set source agent
    pub fn with_source(mut self, agent: impl Into<String>) -> Self {
        self.source_agent = Some(agent.into());
        self
    }

    /// Set duration
    pub fn with_duration(mut self, seconds: f64) -> Self {
        self.duration_seconds = seconds;
        self
    }

    /// Set handoff depth
    pub fn with_depth(mut self, depth: usize) -> Self {
        self.handoff_depth = depth;
        self
    }
}

impl Default for HandoffResult {
    fn default() -> Self {
        Self {
            success: false,
            response: None,
            target_agent: None,
            source_agent: None,
            duration_seconds: 0.0,
            error: None,
            handoff_depth: 0,
        }
    }
}

// =============================================================================
// HANDOFF ERRORS
// =============================================================================

/// Error when a cycle is detected in handoff chain.
#[derive(Debug, Clone)]
pub struct HandoffCycleError {
    /// The chain of agents that formed the cycle
    pub chain: Vec<String>,
}

impl std::fmt::Display for HandoffCycleError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "Handoff cycle detected: {}", self.chain.join(" -> "))
    }
}

impl std::error::Error for HandoffCycleError {}

/// Error when max handoff depth is exceeded.
#[derive(Debug, Clone)]
pub struct HandoffDepthError {
    /// Current depth
    pub depth: usize,
    /// Maximum allowed depth
    pub max_depth: usize,
}

impl std::fmt::Display for HandoffDepthError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "Max handoff depth exceeded: {} > {}",
            self.depth, self.max_depth
        )
    }
}

impl std::error::Error for HandoffDepthError {}

/// Error when handoff times out.
#[derive(Debug, Clone)]
pub struct HandoffTimeoutError {
    /// Timeout duration
    pub timeout: f64,
    /// Agent that timed out
    pub agent_name: String,
}

impl std::fmt::Display for HandoffTimeoutError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "Handoff to {} timed out after {}s",
            self.agent_name, self.timeout
        )
    }
}

impl std::error::Error for HandoffTimeoutError {}

// =============================================================================
// HANDOFF CHAIN TRACKING
// =============================================================================

/// Thread-safe handoff chain tracker.
#[derive(Debug, Default)]
pub struct HandoffChain {
    chain: std::sync::RwLock<Vec<String>>,
}

impl HandoffChain {
    /// Create a new handoff chain
    pub fn new() -> Self {
        Self::default()
    }

    /// Get current chain
    pub fn get(&self) -> Vec<String> {
        self.chain.read().unwrap().clone()
    }

    /// Get current depth
    pub fn depth(&self) -> usize {
        self.chain.read().unwrap().len()
    }

    /// Push agent to chain
    pub fn push(&self, agent_name: impl Into<String>) {
        self.chain.write().unwrap().push(agent_name.into());
    }

    /// Pop agent from chain
    pub fn pop(&self) -> Option<String> {
        self.chain.write().unwrap().pop()
    }

    /// Check if agent is in chain (cycle detection)
    pub fn contains(&self, agent_name: &str) -> bool {
        self.chain.read().unwrap().iter().any(|a| a == agent_name)
    }

    /// Clear the chain
    pub fn clear(&self) {
        self.chain.write().unwrap().clear();
    }
}

// =============================================================================
// HANDOFF
// =============================================================================

/// Represents a handoff configuration for delegating tasks to another agent.
///
/// Handoffs are represented as tools to the LLM, allowing agents to transfer
/// control to specialized agents for specific tasks.
#[derive(Debug, Clone)]
pub struct Handoff {
    /// Target agent name
    pub target_agent_name: String,
    /// Custom tool name override
    pub tool_name_override: Option<String>,
    /// Custom tool description override
    pub tool_description_override: Option<String>,
    /// Handoff configuration
    pub config: HandoffConfig,
}

impl Handoff {
    /// Create a new handoff to a target agent
    pub fn new(target_agent_name: impl Into<String>) -> Self {
        Self {
            target_agent_name: target_agent_name.into(),
            tool_name_override: None,
            tool_description_override: None,
            config: HandoffConfig::default(),
        }
    }

    /// Set custom tool name
    pub fn tool_name(mut self, name: impl Into<String>) -> Self {
        self.tool_name_override = Some(name.into());
        self
    }

    /// Set custom tool description
    pub fn tool_description(mut self, description: impl Into<String>) -> Self {
        self.tool_description_override = Some(description.into());
        self
    }

    /// Set handoff configuration
    pub fn config(mut self, config: HandoffConfig) -> Self {
        self.config = config;
        self
    }

    /// Get the tool name for this handoff
    pub fn get_tool_name(&self) -> String {
        if let Some(ref name) = self.tool_name_override {
            name.clone()
        } else {
            self.default_tool_name()
        }
    }

    /// Get the tool description for this handoff
    pub fn get_tool_description(&self) -> String {
        if let Some(ref desc) = self.tool_description_override {
            desc.clone()
        } else {
            self.default_tool_description()
        }
    }

    /// Generate default tool name based on agent name
    fn default_tool_name(&self) -> String {
        let agent_name = self
            .target_agent_name
            .to_lowercase()
            .replace(' ', "_")
            .replace('-', "_");
        format!("transfer_to_{}", agent_name)
    }

    /// Generate default tool description
    fn default_tool_description(&self) -> String {
        format!("Transfer task to {}", self.target_agent_name)
    }

    /// Check safety constraints before handoff
    pub fn check_safety(
        &self,
        _source_agent_name: &str,
        chain: &HandoffChain,
    ) -> Result<()> {
        // Check for cycles
        if self.config.detect_cycles && chain.contains(&self.target_agent_name) {
            let mut cycle_chain = chain.get();
            cycle_chain.push(self.target_agent_name.clone());
            return Err(Error::handoff(format!(
                "Cycle detected: {}",
                cycle_chain.join(" -> ")
            )));
        }

        // Check depth
        let current_depth = chain.depth();
        if current_depth >= self.config.max_depth {
            return Err(Error::handoff(format!(
                "Max depth exceeded: {} > {}",
                current_depth + 1,
                self.config.max_depth
            )));
        }

        Ok(())
    }

    /// Prepare context data for handoff based on context policy
    pub fn prepare_context(
        &self,
        messages: Vec<serde_json::Value>,
        source_agent: &str,
        chain: &HandoffChain,
        extra_context: HashMap<String, serde_json::Value>,
    ) -> HandoffInputData {
        let filtered_messages = match self.config.context_policy {
            ContextPolicy::None => vec![],
            ContextPolicy::LastN => {
                let n = self.config.max_context_messages;
                if self.config.preserve_system {
                    let system_msgs: Vec<_> = messages
                        .iter()
                        .filter(|m| {
                            m.get("role")
                                .and_then(|r| r.as_str())
                                .map(|r| r == "system")
                                .unwrap_or(false)
                        })
                        .cloned()
                        .collect();
                    let other_msgs: Vec<_> = messages
                        .iter()
                        .filter(|m| {
                            m.get("role")
                                .and_then(|r| r.as_str())
                                .map(|r| r != "system")
                                .unwrap_or(true)
                        })
                        .cloned()
                        .collect();
                    let mut result = system_msgs;
                    result.extend(other_msgs.into_iter().rev().take(n).rev());
                    result
                } else {
                    messages.into_iter().rev().take(n).rev().collect()
                }
            }
            ContextPolicy::Summary => {
                // For summary, keep system + last few messages
                if self.config.preserve_system {
                    let system_msgs: Vec<_> = messages
                        .iter()
                        .filter(|m| {
                            m.get("role")
                                .and_then(|r| r.as_str())
                                .map(|r| r == "system")
                                .unwrap_or(false)
                        })
                        .cloned()
                        .collect();
                    let other_msgs: Vec<_> = messages
                        .iter()
                        .filter(|m| {
                            m.get("role")
                                .and_then(|r| r.as_str())
                                .map(|r| r != "system")
                                .unwrap_or(true)
                        })
                        .cloned()
                        .collect();
                    let mut result = system_msgs;
                    result.extend(other_msgs.into_iter().rev().take(3).rev());
                    result
                } else {
                    messages.into_iter().rev().take(3).rev().collect()
                }
            }
            ContextPolicy::Full => messages,
        };

        let mut context = extra_context;
        context.insert(
            "source_agent".to_string(),
            serde_json::Value::String(source_agent.to_string()),
        );

        HandoffInputData {
            messages: filtered_messages,
            context,
            source_agent: Some(source_agent.to_string()),
            handoff_depth: chain.depth(),
            handoff_chain: chain.get(),
        }
    }
}

// =============================================================================
// HANDOFF FILTERS
// =============================================================================

/// Common handoff input filters.
pub struct HandoffFilters;

impl HandoffFilters {
    /// Remove all tool calls from the message history
    pub fn remove_all_tools(mut data: HandoffInputData) -> HandoffInputData {
        data.messages.retain(|msg| {
            let has_tool_calls = msg.get("tool_calls").is_some();
            let is_tool_role = msg
                .get("role")
                .and_then(|r| r.as_str())
                .map(|r| r == "tool")
                .unwrap_or(false);
            !has_tool_calls && !is_tool_role
        });
        data
    }

    /// Keep only the last n messages
    pub fn keep_last_n(n: usize) -> impl Fn(HandoffInputData) -> HandoffInputData {
        move |mut data: HandoffInputData| {
            let len = data.messages.len();
            if len > n {
                data.messages = data.messages.into_iter().skip(len - n).collect();
            }
            data
        }
    }

    /// Remove all system messages
    pub fn remove_system_messages(mut data: HandoffInputData) -> HandoffInputData {
        data.messages.retain(|msg| {
            msg.get("role")
                .and_then(|r| r.as_str())
                .map(|r| r != "system")
                .unwrap_or(true)
        });
        data
    }
}

// =============================================================================
// TESTS
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_handoff_config_defaults() {
        let config = HandoffConfig::new();
        assert_eq!(config.context_policy, ContextPolicy::Summary);
        assert_eq!(config.max_context_tokens, 4000);
        assert_eq!(config.max_depth, 10);
        assert!(config.detect_cycles);
    }

    #[test]
    fn test_handoff_config_builder() {
        let config = HandoffConfig::new()
            .context_policy(ContextPolicy::Full)
            .timeout_seconds(60.0)
            .max_depth(5)
            .detect_cycles(false);

        assert_eq!(config.context_policy, ContextPolicy::Full);
        assert_eq!(config.timeout_seconds, 60.0);
        assert_eq!(config.max_depth, 5);
        assert!(!config.detect_cycles);
    }

    #[test]
    fn test_handoff_result_success() {
        let result = HandoffResult::success("Task completed")
            .with_target("billing_agent")
            .with_source("triage_agent")
            .with_duration(1.5);

        assert!(result.success);
        assert_eq!(result.response, Some("Task completed".to_string()));
        assert_eq!(result.target_agent, Some("billing_agent".to_string()));
        assert_eq!(result.source_agent, Some("triage_agent".to_string()));
        assert_eq!(result.duration_seconds, 1.5);
    }

    #[test]
    fn test_handoff_result_failure() {
        let result = HandoffResult::failure("Connection timeout")
            .with_target("billing_agent");

        assert!(!result.success);
        assert_eq!(result.error, Some("Connection timeout".to_string()));
        assert!(result.response.is_none());
    }

    #[test]
    fn test_handoff_tool_name() {
        let handoff = Handoff::new("Billing Agent");
        assert_eq!(handoff.get_tool_name(), "transfer_to_billing_agent");

        let handoff_custom = Handoff::new("Billing Agent").tool_name("custom_transfer");
        assert_eq!(handoff_custom.get_tool_name(), "custom_transfer");
    }

    #[test]
    fn test_handoff_chain() {
        let chain = HandoffChain::new();
        assert_eq!(chain.depth(), 0);

        chain.push("agent_a");
        chain.push("agent_b");
        assert_eq!(chain.depth(), 2);
        assert!(chain.contains("agent_a"));
        assert!(chain.contains("agent_b"));
        assert!(!chain.contains("agent_c"));

        let popped = chain.pop();
        assert_eq!(popped, Some("agent_b".to_string()));
        assert_eq!(chain.depth(), 1);
    }

    #[test]
    fn test_handoff_cycle_detection() {
        let handoff = Handoff::new("agent_a").config(HandoffConfig::new().detect_cycles(true));

        let chain = HandoffChain::new();
        chain.push("agent_a");

        let result = handoff.check_safety("agent_b", &chain);
        assert!(result.is_err());
    }

    #[test]
    fn test_handoff_depth_check() {
        let handoff = Handoff::new("agent_c").config(HandoffConfig::new().max_depth(2));

        let chain = HandoffChain::new();
        chain.push("agent_a");
        chain.push("agent_b");

        let result = handoff.check_safety("agent_b", &chain);
        assert!(result.is_err());
    }

    #[test]
    fn test_context_policy_none() {
        let handoff = Handoff::new("target").config(
            HandoffConfig::new().context_policy(ContextPolicy::None),
        );

        let messages = vec![
            serde_json::json!({"role": "system", "content": "You are helpful"}),
            serde_json::json!({"role": "user", "content": "Hello"}),
        ];

        let chain = HandoffChain::new();
        let data = handoff.prepare_context(messages, "source", &chain, HashMap::new());

        assert!(data.messages.is_empty());
    }

    #[test]
    fn test_context_policy_last_n() {
        let handoff = Handoff::new("target").config(
            HandoffConfig::new()
                .context_policy(ContextPolicy::LastN)
                .max_context_messages(2)
                .preserve_system(false),
        );

        let messages = vec![
            serde_json::json!({"role": "user", "content": "msg1"}),
            serde_json::json!({"role": "assistant", "content": "msg2"}),
            serde_json::json!({"role": "user", "content": "msg3"}),
            serde_json::json!({"role": "assistant", "content": "msg4"}),
        ];

        let chain = HandoffChain::new();
        let data = handoff.prepare_context(messages, "source", &chain, HashMap::new());

        assert_eq!(data.messages.len(), 2);
    }

    #[test]
    fn test_handoff_filters_remove_tools() {
        let data = HandoffInputData {
            messages: vec![
                serde_json::json!({"role": "user", "content": "Hello"}),
                serde_json::json!({"role": "assistant", "tool_calls": []}),
                serde_json::json!({"role": "tool", "content": "result"}),
                serde_json::json!({"role": "assistant", "content": "Done"}),
            ],
            ..Default::default()
        };

        let filtered = HandoffFilters::remove_all_tools(data);
        assert_eq!(filtered.messages.len(), 2);
    }

    #[test]
    fn test_handoff_input_data_builder() {
        let data = HandoffInputData::new()
            .source_agent("source_agent")
            .context("key", serde_json::json!("value"));

        assert_eq!(data.source_agent, Some("source_agent".to_string()));
        assert!(data.context.contains_key("key"));
    }
}
