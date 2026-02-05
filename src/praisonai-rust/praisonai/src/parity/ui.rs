//! UI Protocols - A2A and AGUI implementations
//!
//! Provides Agent-to-Agent (A2A) and AG-UI protocol interfaces
//! for exposing PraisonAI agents via standard protocols.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// =============================================================================
// A2A Protocol Types
// =============================================================================

/// A2A Task State enum
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum A2ATaskState {
    /// Task is pending
    Pending,
    /// Task is running
    Running,
    /// Task completed successfully
    Completed,
    /// Task failed
    Failed,
    /// Task was cancelled
    Cancelled,
}

impl Default for A2ATaskState {
    fn default() -> Self {
        Self::Pending
    }
}

/// A2A Agent Skill definition
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct A2AAgentSkill {
    /// Skill name
    pub name: String,
    /// Skill description
    pub description: String,
    /// Input schema (JSON Schema)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub input_schema: Option<serde_json::Value>,
    /// Output schema (JSON Schema)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub output_schema: Option<serde_json::Value>,
}

/// A2A Agent Capabilities
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct A2AAgentCapabilities {
    /// Whether the agent supports streaming
    #[serde(default)]
    pub streaming: bool,
    /// Whether the agent supports push notifications
    #[serde(default)]
    pub push_notifications: bool,
    /// Whether the agent supports state transfer
    #[serde(default)]
    pub state_transfer: bool,
}

/// A2A Agent Card - Discovery information for an agent
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct A2AAgentCard {
    /// Agent name
    pub name: String,
    /// Agent description
    pub description: String,
    /// Agent URL
    pub url: String,
    /// Agent version
    pub version: String,
    /// Agent capabilities
    #[serde(default)]
    pub capabilities: A2AAgentCapabilities,
    /// Agent skills
    #[serde(default)]
    pub skills: Vec<A2AAgentSkill>,
    /// Additional metadata
    #[serde(default)]
    pub metadata: HashMap<String, serde_json::Value>,
}

impl A2AAgentCard {
    /// Create a new A2A Agent Card
    pub fn new(name: impl Into<String>, description: impl Into<String>, url: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            description: description.into(),
            url: url.into(),
            version: "1.0.0".to_string(),
            capabilities: A2AAgentCapabilities::default(),
            skills: Vec::new(),
            metadata: HashMap::new(),
        }
    }

    /// Set version
    pub fn version(mut self, version: impl Into<String>) -> Self {
        self.version = version.into();
        self
    }

    /// Enable streaming
    pub fn with_streaming(mut self) -> Self {
        self.capabilities.streaming = true;
        self
    }

    /// Add a skill
    pub fn skill(mut self, skill: A2AAgentSkill) -> Self {
        self.skills.push(skill);
        self
    }
}

/// A2A Task definition
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct A2ATask {
    /// Task ID
    pub id: String,
    /// Task state
    pub state: A2ATaskState,
    /// Input message
    pub input: String,
    /// Output message (if completed)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub output: Option<String>,
    /// Error message (if failed)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    /// Task metadata
    #[serde(default)]
    pub metadata: HashMap<String, serde_json::Value>,
}

/// A2A Interface for PraisonAI Agents
///
/// Exposes a PraisonAI Agent via the A2A (Agent2Agent) protocol,
/// enabling agent-to-agent communication with other A2A-compatible systems.
#[derive(Debug, Clone)]
pub struct A2A {
    /// Agent name
    pub name: String,
    /// Agent description
    pub description: String,
    /// A2A endpoint URL
    pub url: String,
    /// Version string
    pub version: String,
    /// URL prefix for router
    pub prefix: String,
    /// OpenAPI tags
    pub tags: Vec<String>,
    /// Agent card cache
    agent_card: Option<A2AAgentCard>,
}

impl A2A {
    /// Create a new A2A interface
    pub fn new(name: impl Into<String>, url: impl Into<String>) -> Self {
        let name = name.into();
        Self {
            description: format!("{} via A2A", &name),
            name,
            url: url.into(),
            version: "1.0.0".to_string(),
            prefix: String::new(),
            tags: vec!["A2A".to_string()],
            agent_card: None,
        }
    }

    /// Set description
    pub fn description(mut self, description: impl Into<String>) -> Self {
        self.description = description.into();
        self
    }

    /// Set version
    pub fn version(mut self, version: impl Into<String>) -> Self {
        self.version = version.into();
        self
    }

    /// Set URL prefix
    pub fn prefix(mut self, prefix: impl Into<String>) -> Self {
        self.prefix = prefix.into();
        self
    }

    /// Get the Agent Card for this A2A instance
    pub fn get_agent_card(&self) -> A2AAgentCard {
        A2AAgentCard::new(&self.name, &self.description, &self.url)
            .version(&self.version)
            .with_streaming()
    }

    /// Get status
    pub fn get_status(&self) -> HashMap<String, String> {
        let mut status = HashMap::new();
        status.insert("status".to_string(), "ok".to_string());
        status.insert("name".to_string(), self.name.clone());
        status.insert("version".to_string(), self.version.clone());
        status
    }
}

// =============================================================================
// AGUI Protocol Types
// =============================================================================

/// AGUI Message Role
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum AGUIRole {
    User,
    Assistant,
    System,
    Tool,
}

/// AGUI Message
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AGUIMessage {
    /// Message role
    pub role: AGUIRole,
    /// Message content
    pub content: String,
    /// Optional name
    #[serde(skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
}

/// AGUI Run Input
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AGUIRunInput {
    /// Run ID
    #[serde(skip_serializing_if = "Option::is_none")]
    pub run_id: Option<String>,
    /// Thread ID
    #[serde(skip_serializing_if = "Option::is_none")]
    pub thread_id: Option<String>,
    /// Messages
    #[serde(default)]
    pub messages: Vec<AGUIMessage>,
    /// State
    #[serde(skip_serializing_if = "Option::is_none")]
    pub state: Option<serde_json::Value>,
    /// Forwarded properties
    #[serde(skip_serializing_if = "Option::is_none")]
    pub forwarded_props: Option<serde_json::Value>,
}

/// AGUI Event Type
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AGUIEventType {
    /// Run started
    RunStarted,
    /// Run finished
    RunFinished,
    /// Run error
    RunError,
    /// Text delta
    TextDelta,
    /// Tool call started
    ToolCallStarted,
    /// Tool call finished
    ToolCallFinished,
}

/// AGUI Base Event
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AGUIEvent {
    /// Event type
    pub event_type: AGUIEventType,
    /// Event data
    #[serde(skip_serializing_if = "Option::is_none")]
    pub data: Option<serde_json::Value>,
    /// Run ID
    #[serde(skip_serializing_if = "Option::is_none")]
    pub run_id: Option<String>,
}

impl AGUIEvent {
    /// Create a run started event
    pub fn run_started(run_id: impl Into<String>) -> Self {
        Self {
            event_type: AGUIEventType::RunStarted,
            data: None,
            run_id: Some(run_id.into()),
        }
    }

    /// Create a run finished event
    pub fn run_finished(run_id: impl Into<String>) -> Self {
        Self {
            event_type: AGUIEventType::RunFinished,
            data: None,
            run_id: Some(run_id.into()),
        }
    }

    /// Create a run error event
    pub fn run_error(run_id: impl Into<String>, error: impl Into<String>) -> Self {
        Self {
            event_type: AGUIEventType::RunError,
            data: Some(serde_json::json!({ "error": error.into() })),
            run_id: Some(run_id.into()),
        }
    }

    /// Create a text delta event
    pub fn text_delta(run_id: impl Into<String>, delta: impl Into<String>) -> Self {
        Self {
            event_type: AGUIEventType::TextDelta,
            data: Some(serde_json::json!({ "delta": delta.into() })),
            run_id: Some(run_id.into()),
        }
    }
}

/// AG-UI Interface for PraisonAI Agents
///
/// Exposes a PraisonAI Agent via the AG-UI protocol,
/// enabling integration with CopilotKit and other AG-UI compatible frontends.
#[derive(Debug, Clone)]
pub struct AGUI {
    /// Agent name
    pub name: String,
    /// Agent description
    pub description: String,
    /// URL prefix for router
    pub prefix: String,
    /// OpenAPI tags
    pub tags: Vec<String>,
}

impl AGUI {
    /// Create a new AGUI interface
    pub fn new(name: impl Into<String>) -> Self {
        let name = name.into();
        Self {
            description: format!("{} via AG-UI", &name),
            name,
            prefix: String::new(),
            tags: vec!["AGUI".to_string()],
        }
    }

    /// Set description
    pub fn description(mut self, description: impl Into<String>) -> Self {
        self.description = description.into();
        self
    }

    /// Set URL prefix
    pub fn prefix(mut self, prefix: impl Into<String>) -> Self {
        self.prefix = prefix.into();
        self
    }

    /// Get status
    pub fn get_status(&self) -> HashMap<String, String> {
        let mut status = HashMap::new();
        status.insert("status".to_string(), "available".to_string());
        status.insert("name".to_string(), self.name.clone());
        status
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_a2a_creation() {
        let a2a = A2A::new("TestAgent", "http://localhost:8000/a2a")
            .description("Test agent description")
            .version("2.0.0");

        assert_eq!(a2a.name, "TestAgent");
        assert_eq!(a2a.url, "http://localhost:8000/a2a");
        assert_eq!(a2a.version, "2.0.0");
    }

    #[test]
    fn test_a2a_agent_card() {
        let a2a = A2A::new("TestAgent", "http://localhost:8000/a2a");
        let card = a2a.get_agent_card();

        assert_eq!(card.name, "TestAgent");
        assert!(card.capabilities.streaming);
    }

    #[test]
    fn test_agui_creation() {
        let agui = AGUI::new("TestAgent")
            .description("Test description")
            .prefix("/api/v1");

        assert_eq!(agui.name, "TestAgent");
        assert_eq!(agui.prefix, "/api/v1");
    }

    #[test]
    fn test_agui_events() {
        let event = AGUIEvent::run_started("run-123");
        assert_eq!(event.event_type, AGUIEventType::RunStarted);
        assert_eq!(event.run_id, Some("run-123".to_string()));

        let error_event = AGUIEvent::run_error("run-123", "Something went wrong");
        assert_eq!(error_event.event_type, AGUIEventType::RunError);
    }

    #[test]
    fn test_a2a_task_state() {
        assert_eq!(A2ATaskState::default(), A2ATaskState::Pending);
    }
}
