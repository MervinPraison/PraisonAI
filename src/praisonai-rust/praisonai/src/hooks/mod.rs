//! Hooks Module for PraisonAI Rust SDK.
//!
//! Provides a powerful hook system for intercepting and modifying agent behavior
//! at various lifecycle points. Unlike callbacks (which are for UI events),
//! hooks can intercept, modify, or block tool execution.
//!
//! # Features
//!
//! - Event-based hook system (BeforeTool, AfterTool, BeforeAgent, etc.)
//! - Function hooks for in-process customization
//! - Matcher patterns for selective hook execution
//! - Decision outcomes (allow, deny, block)
//!
//! # Usage
//!
//! ```rust,ignore
//! use praisonai::hooks::{HookRegistry, HookEvent, HookResult};
//!
//! let mut registry = HookRegistry::new();
//!
//! registry.add_hook(HookEvent::BeforeTool, |input| {
//!     if input.tool_name == Some("dangerous_tool".to_string()) {
//!         return HookResult::deny("Tool blocked by policy");
//!     }
//!     HookResult::allow()
//! });
//!
//! let agent = Agent::new()
//!     .hooks(registry)
//!     .build()?;
//! ```

use crate::error::Result;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;

/// Event names for the hook system
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum HookEvent {
    /// Before tool execution
    BeforeTool,
    /// After tool execution
    AfterTool,
    /// Before agent processes a message
    BeforeAgent,
    /// After agent processes a message
    AfterAgent,
    /// Before LLM call
    BeforeLlm,
    /// After LLM call
    AfterLlm,
    /// Session start
    SessionStart,
    /// Session end
    SessionEnd,
    /// On error
    OnError,
    /// On retry
    OnRetry,
    /// On initialization
    OnInit,
    /// On shutdown
    OnShutdown,
}

impl std::fmt::Display for HookEvent {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            HookEvent::BeforeTool => write!(f, "before_tool"),
            HookEvent::AfterTool => write!(f, "after_tool"),
            HookEvent::BeforeAgent => write!(f, "before_agent"),
            HookEvent::AfterAgent => write!(f, "after_agent"),
            HookEvent::BeforeLlm => write!(f, "before_llm"),
            HookEvent::AfterLlm => write!(f, "after_llm"),
            HookEvent::SessionStart => write!(f, "session_start"),
            HookEvent::SessionEnd => write!(f, "session_end"),
            HookEvent::OnError => write!(f, "on_error"),
            HookEvent::OnRetry => write!(f, "on_retry"),
            HookEvent::OnInit => write!(f, "on_init"),
            HookEvent::OnShutdown => write!(f, "on_shutdown"),
        }
    }
}

/// Decision types for hook outputs
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
#[derive(Default)]
pub enum HookDecision {
    /// Allow the operation to proceed
    #[default]
    Allow,
    /// Deny the operation
    Deny,
    /// Block the operation (stronger than deny)
    Block,
    /// Ask for user confirmation
    Ask,
}

/// Input data for hooks
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HookInput {
    /// Session ID
    pub session_id: String,
    /// Event name
    pub event_name: String,
    /// Timestamp (ISO 8601)
    pub timestamp: String,
    /// Agent name (optional)
    pub agent_name: Option<String>,
    /// Tool name (for tool events)
    pub tool_name: Option<String>,
    /// Tool arguments (for tool events)
    pub tool_args: Option<serde_json::Value>,
    /// Message content (for agent/LLM events)
    pub message: Option<String>,
    /// Error message (for error events)
    pub error: Option<String>,
    /// Additional data
    #[serde(default)]
    pub extra: HashMap<String, serde_json::Value>,
}

impl HookInput {
    /// Create a new hook input
    pub fn new(event: HookEvent, session_id: impl Into<String>) -> Self {
        Self {
            session_id: session_id.into(),
            event_name: event.to_string(),
            timestamp: chrono::Utc::now().to_rfc3339(),
            agent_name: None,
            tool_name: None,
            tool_args: None,
            message: None,
            error: None,
            extra: HashMap::new(),
        }
    }

    /// Set agent name
    pub fn with_agent(mut self, name: impl Into<String>) -> Self {
        self.agent_name = Some(name.into());
        self
    }

    /// Set tool info
    pub fn with_tool(mut self, name: impl Into<String>, args: serde_json::Value) -> Self {
        self.tool_name = Some(name.into());
        self.tool_args = Some(args);
        self
    }

    /// Set message
    pub fn with_message(mut self, message: impl Into<String>) -> Self {
        self.message = Some(message.into());
        self
    }

    /// Set error
    pub fn with_error(mut self, error: impl Into<String>) -> Self {
        self.error = Some(error.into());
        self
    }

    /// Add extra data
    pub fn with_extra(mut self, key: impl Into<String>, value: serde_json::Value) -> Self {
        self.extra.insert(key.into(), value);
        self
    }
}

/// Result from a hook execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HookResult {
    /// Decision (allow, deny, block, ask)
    pub decision: HookDecision,
    /// Reason for the decision
    pub reason: Option<String>,
    /// Modified input data (optional)
    pub modified_input: Option<HashMap<String, serde_json::Value>>,
    /// Additional context
    pub additional_context: Option<String>,
    /// Whether to suppress output
    pub suppress_output: bool,
}

impl HookResult {
    /// Create an allow result
    pub fn allow() -> Self {
        Self {
            decision: HookDecision::Allow,
            reason: None,
            modified_input: None,
            additional_context: None,
            suppress_output: false,
        }
    }

    /// Create an allow result with reason
    pub fn allow_with_reason(reason: impl Into<String>) -> Self {
        Self {
            decision: HookDecision::Allow,
            reason: Some(reason.into()),
            modified_input: None,
            additional_context: None,
            suppress_output: false,
        }
    }

    /// Create a deny result
    pub fn deny(reason: impl Into<String>) -> Self {
        Self {
            decision: HookDecision::Deny,
            reason: Some(reason.into()),
            modified_input: None,
            additional_context: None,
            suppress_output: false,
        }
    }

    /// Create a block result
    pub fn block(reason: impl Into<String>) -> Self {
        Self {
            decision: HookDecision::Block,
            reason: Some(reason.into()),
            modified_input: None,
            additional_context: None,
            suppress_output: false,
        }
    }

    /// Create an ask result
    pub fn ask(reason: impl Into<String>) -> Self {
        Self {
            decision: HookDecision::Ask,
            reason: Some(reason.into()),
            modified_input: None,
            additional_context: None,
            suppress_output: false,
        }
    }

    /// Check if the result allows execution
    pub fn is_allowed(&self) -> bool {
        matches!(self.decision, HookDecision::Allow)
    }

    /// Check if the result denies execution
    pub fn is_denied(&self) -> bool {
        matches!(self.decision, HookDecision::Deny | HookDecision::Block)
    }

    /// Add modified input
    pub fn with_modified_input(mut self, input: HashMap<String, serde_json::Value>) -> Self {
        self.modified_input = Some(input);
        self
    }

    /// Add additional context
    pub fn with_context(mut self, context: impl Into<String>) -> Self {
        self.additional_context = Some(context.into());
        self
    }

    /// Suppress output
    pub fn suppress(mut self) -> Self {
        self.suppress_output = true;
        self
    }
}

impl Default for HookResult {
    fn default() -> Self {
        Self::allow()
    }
}

/// Hook function type
pub type HookFn = Arc<dyn Fn(&HookInput) -> HookResult + Send + Sync>;

/// Hook definition
pub struct HookDefinition {
    /// Unique ID
    pub id: String,
    /// Event to hook
    pub event: HookEvent,
    /// Optional matcher pattern (regex for tool names, etc.)
    pub matcher: Option<String>,
    /// Hook function
    pub func: HookFn,
    /// Whether hook is enabled
    pub enabled: bool,
    /// Hook name (for debugging)
    pub name: Option<String>,
}

impl HookDefinition {
    /// Create a new hook definition
    pub fn new(
        event: HookEvent,
        func: impl Fn(&HookInput) -> HookResult + Send + Sync + 'static,
    ) -> Self {
        Self {
            id: uuid::Uuid::new_v4().to_string()[..8].to_string(),
            event,
            matcher: None,
            func: Arc::new(func),
            enabled: true,
            name: None,
        }
    }

    /// Set matcher pattern
    pub fn with_matcher(mut self, pattern: impl Into<String>) -> Self {
        self.matcher = Some(pattern.into());
        self
    }

    /// Set name
    pub fn with_name(mut self, name: impl Into<String>) -> Self {
        self.name = Some(name.into());
        self
    }

    /// Check if this hook matches the target
    pub fn matches(&self, target: &str) -> bool {
        match &self.matcher {
            None => true,
            Some(pattern) => {
                // Simple glob matching
                if pattern.contains('*') {
                    let parts: Vec<&str> = pattern.split('*').collect();
                    if parts.len() == 2 {
                        let (prefix, suffix) = (parts[0], parts[1]);
                        target.starts_with(prefix) && target.ends_with(suffix)
                    } else {
                        target.contains(pattern.trim_matches('*'))
                    }
                } else {
                    target == pattern
                }
            }
        }
    }

    /// Execute the hook
    pub fn execute(&self, input: &HookInput) -> HookResult {
        if !self.enabled {
            return HookResult::allow();
        }
        (self.func)(input)
    }
}

/// Hook registry for managing hooks
pub struct HookRegistry {
    hooks: HashMap<HookEvent, Vec<HookDefinition>>,
}

impl HookRegistry {
    /// Create a new hook registry
    pub fn new() -> Self {
        Self {
            hooks: HashMap::new(),
        }
    }

    /// Add a hook
    pub fn add_hook(
        &mut self,
        event: HookEvent,
        func: impl Fn(&HookInput) -> HookResult + Send + Sync + 'static,
    ) -> &mut Self {
        let hook = HookDefinition::new(event, func);
        self.hooks.entry(event).or_default().push(hook);
        self
    }

    /// Add a hook with matcher
    pub fn add_hook_with_matcher(
        &mut self,
        event: HookEvent,
        matcher: impl Into<String>,
        func: impl Fn(&HookInput) -> HookResult + Send + Sync + 'static,
    ) -> &mut Self {
        let hook = HookDefinition::new(event, func).with_matcher(matcher);
        self.hooks.entry(event).or_default().push(hook);
        self
    }

    /// Add a hook definition
    pub fn add_definition(&mut self, hook: HookDefinition) -> &mut Self {
        self.hooks.entry(hook.event).or_default().push(hook);
        self
    }

    /// Remove a hook by ID
    pub fn remove_hook(&mut self, id: &str) -> bool {
        for hooks in self.hooks.values_mut() {
            if let Some(pos) = hooks.iter().position(|h| h.id == id) {
                hooks.remove(pos);
                return true;
            }
        }
        false
    }

    /// Check if any hooks exist for an event
    pub fn has_hooks(&self, event: HookEvent) -> bool {
        self.hooks.get(&event).is_some_and(|h| !h.is_empty())
    }

    /// Get hook count for an event
    pub fn hook_count(&self, event: HookEvent) -> usize {
        self.hooks.get(&event).map_or(0, |h| h.len())
    }

    /// Execute all hooks for an event
    pub fn execute(&self, event: HookEvent, input: &HookInput) -> HookResult {
        let hooks = match self.hooks.get(&event) {
            Some(h) => h,
            None => return HookResult::allow(),
        };

        // Get target for matching (tool name, etc.)
        let target = input.tool_name.as_deref().unwrap_or("");

        for hook in hooks {
            if !hook.matches(target) {
                continue;
            }

            let result = hook.execute(input);

            // If any hook denies, stop and return
            if result.is_denied() {
                return result;
            }
        }

        HookResult::allow()
    }

    /// Execute hooks asynchronously (for future async hooks)
    pub async fn execute_async(&self, event: HookEvent, input: &HookInput) -> HookResult {
        // For now, just call sync version
        self.execute(event, input)
    }
}

impl Default for HookRegistry {
    fn default() -> Self {
        Self::new()
    }
}

/// Hook runner for executing hooks in a workflow
pub struct HookRunner {
    registry: Arc<HookRegistry>,
}

impl HookRunner {
    /// Create a new hook runner
    pub fn new(registry: HookRegistry) -> Self {
        Self {
            registry: Arc::new(registry),
        }
    }

    /// Run before-tool hooks
    pub fn before_tool(
        &self,
        session_id: &str,
        tool_name: &str,
        args: serde_json::Value,
    ) -> Result<HookResult> {
        let input = HookInput::new(HookEvent::BeforeTool, session_id).with_tool(tool_name, args);
        Ok(self.registry.execute(HookEvent::BeforeTool, &input))
    }

    /// Run after-tool hooks
    pub fn after_tool(
        &self,
        session_id: &str,
        tool_name: &str,
        result: serde_json::Value,
    ) -> Result<HookResult> {
        let input = HookInput::new(HookEvent::AfterTool, session_id).with_tool(tool_name, result);
        Ok(self.registry.execute(HookEvent::AfterTool, &input))
    }

    /// Run before-agent hooks
    pub fn before_agent(
        &self,
        session_id: &str,
        agent_name: &str,
        message: &str,
    ) -> Result<HookResult> {
        let input = HookInput::new(HookEvent::BeforeAgent, session_id)
            .with_agent(agent_name)
            .with_message(message);
        Ok(self.registry.execute(HookEvent::BeforeAgent, &input))
    }

    /// Run after-agent hooks
    pub fn after_agent(
        &self,
        session_id: &str,
        agent_name: &str,
        response: &str,
    ) -> Result<HookResult> {
        let input = HookInput::new(HookEvent::AfterAgent, session_id)
            .with_agent(agent_name)
            .with_message(response);
        Ok(self.registry.execute(HookEvent::AfterAgent, &input))
    }

    /// Run on-error hooks
    pub fn on_error(&self, session_id: &str, error: &str) -> Result<HookResult> {
        let input = HookInput::new(HookEvent::OnError, session_id).with_error(error);
        Ok(self.registry.execute(HookEvent::OnError, &input))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_hook_result_creation() {
        let allow = HookResult::allow();
        assert!(allow.is_allowed());
        assert!(!allow.is_denied());

        let deny = HookResult::deny("Not allowed");
        assert!(!deny.is_allowed());
        assert!(deny.is_denied());
        assert_eq!(deny.reason, Some("Not allowed".to_string()));
    }

    #[test]
    fn test_hook_registry() {
        let mut registry = HookRegistry::new();

        registry.add_hook(HookEvent::BeforeTool, |_| HookResult::allow());

        assert!(registry.has_hooks(HookEvent::BeforeTool));
        assert!(!registry.has_hooks(HookEvent::AfterTool));
        assert_eq!(registry.hook_count(HookEvent::BeforeTool), 1);
    }

    #[test]
    fn test_hook_execution() {
        let mut registry = HookRegistry::new();

        registry.add_hook(HookEvent::BeforeTool, |input| {
            if input.tool_name.as_deref() == Some("dangerous") {
                HookResult::deny("Dangerous tool blocked")
            } else {
                HookResult::allow()
            }
        });

        // Safe tool should be allowed
        let input = HookInput::new(HookEvent::BeforeTool, "session-1")
            .with_tool("safe_tool", serde_json::json!({}));
        let result = registry.execute(HookEvent::BeforeTool, &input);
        assert!(result.is_allowed());

        // Dangerous tool should be denied
        let input = HookInput::new(HookEvent::BeforeTool, "session-1")
            .with_tool("dangerous", serde_json::json!({}));
        let result = registry.execute(HookEvent::BeforeTool, &input);
        assert!(result.is_denied());
    }

    #[test]
    fn test_hook_matcher() {
        let mut registry = HookRegistry::new();

        // Only match tools starting with "write_"
        registry.add_hook_with_matcher(HookEvent::BeforeTool, "write_*", |_| {
            HookResult::deny("Write operations blocked")
        });

        // Read tool should be allowed
        let input = HookInput::new(HookEvent::BeforeTool, "session-1")
            .with_tool("read_file", serde_json::json!({}));
        let result = registry.execute(HookEvent::BeforeTool, &input);
        assert!(result.is_allowed());

        // Write tool should be denied
        let input = HookInput::new(HookEvent::BeforeTool, "session-1")
            .with_tool("write_file", serde_json::json!({}));
        let result = registry.execute(HookEvent::BeforeTool, &input);
        assert!(result.is_denied());
    }

    #[test]
    fn test_hook_input_builder() {
        let input = HookInput::new(HookEvent::BeforeTool, "session-123")
            .with_agent("my-agent")
            .with_tool("search", serde_json::json!({"query": "rust"}))
            .with_extra("custom", serde_json::json!("value"));

        assert_eq!(input.session_id, "session-123");
        assert_eq!(input.agent_name, Some("my-agent".to_string()));
        assert_eq!(input.tool_name, Some("search".to_string()));
        assert!(input.extra.contains_key("custom"));
    }
}
