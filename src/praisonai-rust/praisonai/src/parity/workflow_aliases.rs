//! Workflow Pattern Aliases
//!
//! Provides function aliases for workflow patterns matching Python SDK:
//! - loop, parallel, repeat, route, when
//! - Workflow, Pipeline (aliases for AgentFlow)
//! - handoff, handoff_filters, prompt_with_handoff_instructions

use std::sync::Arc;

// =============================================================================
// Type Aliases
// =============================================================================

/// Alias for AgentFlow (matches Python SDK naming)
pub type Workflow = crate::workflows::AgentFlow;

/// Alias for AgentFlow (matches Python SDK naming)
pub type Pipeline = crate::workflows::AgentFlow;

/// Alias for AgentManager/Agents (matches Python SDK naming)
pub type Agents = crate::workflows::AgentTeam;

/// Alias for AgentManager (matches Python SDK naming)
pub type AgentManager = crate::workflows::AgentTeam;

// =============================================================================
// Workflow Pattern Functions
// =============================================================================

/// Create a loop workflow step
///
/// Creates a loop step with an agent and items to iterate over.
///
/// # Arguments
/// * `agent` - The agent to execute for each item
/// * `items` - Items to iterate over
///
/// # Example
/// ```ignore
/// use praisonai::parity::workflow_aliases::loop_step;
///
/// let step = loop_step(agent, vec!["item1".to_string(), "item2".to_string()]);
/// ```
pub fn loop_step(
    agent: Arc<crate::agent::Agent>,
    items: Vec<String>,
) -> crate::workflows::FlowStep {
    crate::workflows::FlowStep::Loop(crate::workflows::Loop { agent, items })
}

/// Create a parallel workflow step
///
/// Executes multiple agents concurrently.
///
/// # Arguments
/// * `agents` - List of agents to execute in parallel
///
/// # Example
/// ```ignore
/// use praisonai::parity::workflow_aliases::parallel;
///
/// let step = parallel(vec![agent1, agent2, agent3]);
/// ```
pub fn parallel(agents: Vec<Arc<crate::agent::Agent>>) -> crate::workflows::FlowStep {
    crate::workflows::FlowStep::Parallel(crate::workflows::Parallel { agents })
}

/// Create a repeat workflow step
///
/// Executes the agent a fixed number of times.
///
/// # Arguments
/// * `agent` - The agent to execute
/// * `times` - Number of times to repeat
///
/// # Example
/// ```ignore
/// use praisonai::parity::workflow_aliases::repeat;
///
/// let step = repeat(agent, 3);
/// ```
pub fn repeat(agent: Arc<crate::agent::Agent>, times: usize) -> crate::workflows::FlowStep {
    crate::workflows::FlowStep::Repeat(crate::workflows::Repeat { agent, times })
}

/// Create a route workflow step
///
/// Conditionally routes to different agents based on a condition.
///
/// # Arguments
/// * `condition` - Function that returns true/false to determine routing
/// * `if_true` - Agent to execute if condition is true
/// * `if_false` - Optional agent to execute if condition is false
///
/// # Example
/// ```ignore
/// use praisonai::parity::workflow_aliases::route;
///
/// let step = route(
///     |input| input.contains("urgent"),
///     urgent_agent,
///     Some(normal_agent),
/// );
/// ```
pub fn route<F>(
    condition: F,
    if_true: Arc<crate::agent::Agent>,
    if_false: Option<Arc<crate::agent::Agent>>,
) -> crate::workflows::FlowStep
where
    F: Fn(&str) -> bool + Send + Sync + 'static,
{
    crate::workflows::FlowStep::Route(crate::workflows::Route {
        condition: Box::new(condition),
        if_true,
        if_false,
    })
}

/// Alias for route (matches Python SDK naming)
///
/// Creates a conditional routing step.
pub fn when<F>(
    condition: F,
    if_true: Arc<crate::agent::Agent>,
    if_false: Option<Arc<crate::agent::Agent>>,
) -> crate::workflows::FlowStep
where
    F: Fn(&str) -> bool + Send + Sync + 'static,
{
    route(condition, if_true, if_false)
}

// =============================================================================
// Handoff Functions
// =============================================================================

/// Handoff configuration for agent-to-agent transfers
#[derive(Debug, Clone, Default)]
pub struct HandoffConfig {
    /// Target agent name
    pub target: String,
    /// Handoff message/context
    pub message: Option<String>,
    /// Whether to include conversation history
    pub include_history: bool,
    /// Custom metadata
    pub metadata: std::collections::HashMap<String, serde_json::Value>,
}

impl HandoffConfig {
    /// Create a new handoff configuration
    pub fn new(target: impl Into<String>) -> Self {
        Self {
            target: target.into(),
            message: None,
            include_history: true,
            metadata: std::collections::HashMap::new(),
        }
    }

    /// Set handoff message
    pub fn message(mut self, message: impl Into<String>) -> Self {
        self.message = Some(message.into());
        self
    }

    /// Set whether to include history
    pub fn include_history(mut self, include: bool) -> Self {
        self.include_history = include;
        self
    }

    /// Add metadata
    pub fn metadata(mut self, key: impl Into<String>, value: serde_json::Value) -> Self {
        self.metadata.insert(key.into(), value);
        self
    }
}

/// Create a handoff to another agent
///
/// # Arguments
/// * `target` - Name of the target agent
/// * `message` - Optional handoff message
///
/// # Example
/// ```ignore
/// use praisonai::parity::workflow_aliases::handoff;
///
/// let config = handoff("specialist_agent", Some("Please handle this complex query"));
/// ```
pub fn handoff(target: impl Into<String>, message: Option<&str>) -> HandoffConfig {
    let mut config = HandoffConfig::new(target);
    if let Some(msg) = message {
        config = config.message(msg);
    }
    config
}

/// Handoff filter types
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HandoffFilter {
    /// Allow all handoffs
    AllowAll,
    /// Deny all handoffs
    DenyAll,
    /// Allow specific agents only
    AllowList,
    /// Deny specific agents
    DenyList,
}

/// Handoff filter configuration
#[derive(Debug, Clone, Default)]
pub struct HandoffFilters {
    /// Filter type
    pub filter_type: Option<HandoffFilter>,
    /// List of agent names for allow/deny lists
    pub agents: Vec<String>,
}

impl HandoffFilters {
    /// Create a new handoff filter
    pub fn new() -> Self {
        Self::default()
    }

    /// Allow all handoffs
    pub fn allow_all() -> Self {
        Self {
            filter_type: Some(HandoffFilter::AllowAll),
            agents: Vec::new(),
        }
    }

    /// Deny all handoffs
    pub fn deny_all() -> Self {
        Self {
            filter_type: Some(HandoffFilter::DenyAll),
            agents: Vec::new(),
        }
    }

    /// Allow only specific agents
    pub fn allow_only(agents: Vec<String>) -> Self {
        Self {
            filter_type: Some(HandoffFilter::AllowList),
            agents,
        }
    }

    /// Deny specific agents
    pub fn deny(agents: Vec<String>) -> Self {
        Self {
            filter_type: Some(HandoffFilter::DenyList),
            agents,
        }
    }

    /// Check if handoff to target is allowed
    pub fn is_allowed(&self, target: &str) -> bool {
        match self.filter_type {
            Some(HandoffFilter::AllowAll) => true,
            Some(HandoffFilter::DenyAll) => false,
            Some(HandoffFilter::AllowList) => self.agents.iter().any(|a| a == target),
            Some(HandoffFilter::DenyList) => !self.agents.iter().any(|a| a == target),
            None => true, // Default: allow all
        }
    }
}

/// Create handoff filters
pub fn handoff_filters() -> HandoffFilters {
    HandoffFilters::new()
}

/// Generate a prompt with handoff instructions
///
/// Creates a system prompt that includes instructions for handing off
/// to other agents when appropriate.
///
/// # Arguments
/// * `base_prompt` - The base system prompt
/// * `available_agents` - List of agents that can be handed off to
///
/// # Example
/// ```ignore
/// use praisonai::parity::workflow_aliases::prompt_with_handoff_instructions;
///
/// let prompt = prompt_with_handoff_instructions(
///     "You are a helpful assistant.",
///     &["specialist", "researcher"],
/// );
/// ```
pub fn prompt_with_handoff_instructions(base_prompt: &str, available_agents: &[&str]) -> String {
    if available_agents.is_empty() {
        return base_prompt.to_string();
    }

    let agents_list = available_agents.join(", ");
    
    format!(
        r#"{base_prompt}

## Handoff Instructions

You can hand off the conversation to specialized agents when appropriate.
Available agents: {agents_list}

To hand off, respond with:
HANDOFF: <agent_name>
REASON: <brief explanation>
CONTEXT: <relevant context for the receiving agent>

Only hand off when the query is better suited for another agent's expertise."#
    )
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_handoff_config() {
        let config = HandoffConfig::new("target_agent")
            .message("Please handle this")
            .include_history(false)
            .metadata("priority", serde_json::json!("high"));

        assert_eq!(config.target, "target_agent");
        assert_eq!(config.message, Some("Please handle this".to_string()));
        assert!(!config.include_history);
        assert!(config.metadata.contains_key("priority"));
    }

    #[test]
    fn test_handoff_function() {
        let config = handoff("agent1", Some("Test message"));
        assert_eq!(config.target, "agent1");
        assert_eq!(config.message, Some("Test message".to_string()));
    }

    #[test]
    fn test_handoff_filters_allow_all() {
        let filters = HandoffFilters::allow_all();
        assert!(filters.is_allowed("any_agent"));
        assert!(filters.is_allowed("another_agent"));
    }

    #[test]
    fn test_handoff_filters_deny_all() {
        let filters = HandoffFilters::deny_all();
        assert!(!filters.is_allowed("any_agent"));
        assert!(!filters.is_allowed("another_agent"));
    }

    #[test]
    fn test_handoff_filters_allow_list() {
        let filters = HandoffFilters::allow_only(vec!["agent1".to_string(), "agent2".to_string()]);
        assert!(filters.is_allowed("agent1"));
        assert!(filters.is_allowed("agent2"));
        assert!(!filters.is_allowed("agent3"));
    }

    #[test]
    fn test_handoff_filters_deny_list() {
        let filters = HandoffFilters::deny(vec!["blocked".to_string()]);
        assert!(filters.is_allowed("agent1"));
        assert!(!filters.is_allowed("blocked"));
    }

    #[test]
    fn test_prompt_with_handoff_instructions() {
        let prompt = prompt_with_handoff_instructions(
            "You are a helpful assistant.",
            &["specialist", "researcher"],
        );

        assert!(prompt.contains("You are a helpful assistant."));
        assert!(prompt.contains("specialist, researcher"));
        assert!(prompt.contains("HANDOFF:"));
    }

    #[test]
    fn test_prompt_with_handoff_no_agents() {
        let prompt = prompt_with_handoff_instructions("Base prompt", &[]);
        assert_eq!(prompt, "Base prompt");
    }
}
