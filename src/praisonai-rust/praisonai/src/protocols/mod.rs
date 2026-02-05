//! Protocol System Module
//!
//! This module provides protocol definitions for agent implementations:
//! - `AgentProtocol` - Minimal protocol for agent implementations
//! - `RunnableAgentProtocol` - Extended protocol with run/start methods
//! - `AgentOSProtocol` - Agent OS integration protocol
//!
//! # Example
//!
//! ```ignore
//! use praisonai::protocols::AgentProtocol;
//!
//! struct MockAgent {
//!     name: String,
//! }
//!
//! impl AgentProtocol for MockAgent {
//!     fn name(&self) -> &str { &self.name }
//!     fn chat(&self, prompt: &str) -> String { "Response".to_string() }
//! }
//! ```

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use crate::error::Result;

// =============================================================================
// AGENT PROTOCOL
// =============================================================================

/// Minimal Protocol for agent implementations.
///
/// This defines the essential interface that any agent must provide.
/// It enables proper mocking and testing without real LLM dependencies.
#[async_trait]
pub trait AgentProtocol: Send + Sync {
    /// Get the agent's name
    fn name(&self) -> &str;

    /// Synchronous chat with the agent
    fn chat(&self, prompt: &str) -> Result<String>;

    /// Asynchronous chat with the agent
    async fn achat(&self, prompt: &str) -> Result<String>;
}

/// Extended Protocol for agents that support run/start methods.
#[async_trait]
pub trait RunnableAgentProtocol: AgentProtocol {
    /// Run the agent with a prompt (alias for chat in most cases)
    fn run(&self, prompt: &str) -> Result<String> {
        self.chat(prompt)
    }

    /// Start the agent with a prompt
    fn start(&self, prompt: &str) -> Result<String> {
        self.chat(prompt)
    }

    /// Async run the agent with a prompt
    async fn arun(&self, prompt: &str) -> Result<String> {
        self.achat(prompt).await
    }

    /// Async start the agent with a prompt
    async fn astart(&self, prompt: &str) -> Result<String> {
        self.achat(prompt).await
    }
}

// =============================================================================
// TOOL PROTOCOL
// =============================================================================

/// Protocol for tool implementations.
#[async_trait]
pub trait ToolProtocol: Send + Sync {
    /// Get the tool's name
    fn name(&self) -> &str;

    /// Get the tool's description
    fn description(&self) -> &str;

    /// Get the tool's parameter schema
    fn parameters_schema(&self) -> serde_json::Value;

    /// Execute the tool with arguments
    async fn execute(&self, args: serde_json::Value) -> Result<serde_json::Value>;
}

// =============================================================================
// MEMORY PROTOCOL
// =============================================================================

/// Protocol for memory implementations.
#[async_trait]
pub trait MemoryProtocol: Send + Sync {
    /// Store a message in memory
    async fn store(&mut self, role: &str, content: &str) -> Result<()>;

    /// Get conversation history
    async fn history(&self) -> Result<Vec<MemoryMessage>>;

    /// Clear memory
    async fn clear(&mut self) -> Result<()>;

    /// Search memory
    async fn search(&self, query: &str, limit: usize) -> Result<Vec<MemoryMessage>>;
}

/// A message stored in memory.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryMessage {
    /// Message role
    pub role: String,
    /// Message content
    pub content: String,
    /// Timestamp
    pub timestamp: u64,
    /// Metadata
    pub metadata: HashMap<String, String>,
}

impl MemoryMessage {
    /// Create a new memory message
    pub fn new(role: impl Into<String>, content: impl Into<String>) -> Self {
        Self {
            role: role.into(),
            content: content.into(),
            timestamp: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs(),
            metadata: HashMap::new(),
        }
    }
}

// =============================================================================
// LLM PROTOCOL
// =============================================================================

/// Protocol for LLM provider implementations.
#[async_trait]
pub trait LlmProtocol: Send + Sync {
    /// Get the model name
    fn model(&self) -> &str;

    /// Chat with the LLM
    async fn chat(&self, messages: &[LlmMessage]) -> Result<LlmResponse>;

    /// Chat with tools
    async fn chat_with_tools(
        &self,
        messages: &[LlmMessage],
        tools: &[ToolSchema],
    ) -> Result<LlmResponse>;
}

/// An LLM message.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LlmMessage {
    /// Message role
    pub role: String,
    /// Message content
    pub content: String,
}

impl LlmMessage {
    /// Create a system message
    pub fn system(content: impl Into<String>) -> Self {
        Self {
            role: "system".to_string(),
            content: content.into(),
        }
    }

    /// Create a user message
    pub fn user(content: impl Into<String>) -> Self {
        Self {
            role: "user".to_string(),
            content: content.into(),
        }
    }

    /// Create an assistant message
    pub fn assistant(content: impl Into<String>) -> Self {
        Self {
            role: "assistant".to_string(),
            content: content.into(),
        }
    }
}

/// An LLM response.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LlmResponse {
    /// Response content
    pub content: String,
    /// Tool calls if any
    pub tool_calls: Vec<ToolCall>,
    /// Token usage
    pub usage: Option<TokenUsage>,
}

/// A tool call from the LLM.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCall {
    /// Tool call ID
    pub id: String,
    /// Tool name
    pub name: String,
    /// Tool arguments
    pub arguments: serde_json::Value,
}

/// Token usage statistics.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TokenUsage {
    /// Prompt tokens
    pub prompt_tokens: u32,
    /// Completion tokens
    pub completion_tokens: u32,
    /// Total tokens
    pub total_tokens: u32,
}

/// Tool schema for LLM.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolSchema {
    /// Tool name
    pub name: String,
    /// Tool description
    pub description: String,
    /// Parameter schema
    pub parameters: serde_json::Value,
}

// =============================================================================
// AGENT OS PROTOCOL
// =============================================================================

/// Agent OS configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentOSConfig {
    /// Agent OS URL
    pub url: String,
    /// API key
    pub api_key: Option<String>,
    /// Agent ID
    pub agent_id: Option<String>,
    /// Enable telemetry
    pub telemetry: bool,
    /// Connection timeout
    pub timeout: u32,
}

impl Default for AgentOSConfig {
    fn default() -> Self {
        Self {
            url: "https://agentos.praison.ai".to_string(),
            api_key: None,
            agent_id: None,
            telemetry: true,
            timeout: 30,
        }
    }
}

impl AgentOSConfig {
    /// Create a new config
    pub fn new(url: impl Into<String>) -> Self {
        Self {
            url: url.into(),
            ..Default::default()
        }
    }

    /// Set API key
    pub fn api_key(mut self, key: impl Into<String>) -> Self {
        self.api_key = Some(key.into());
        self
    }

    /// Set agent ID
    pub fn agent_id(mut self, id: impl Into<String>) -> Self {
        self.agent_id = Some(id.into());
        self
    }

    /// Disable telemetry
    pub fn no_telemetry(mut self) -> Self {
        self.telemetry = false;
        self
    }
}

/// Protocol for Agent OS integration.
#[async_trait]
pub trait AgentOSProtocol: Send + Sync {
    /// Get configuration
    fn config(&self) -> &AgentOSConfig;

    /// Register agent with Agent OS
    async fn register(&self) -> Result<String>;

    /// Send heartbeat
    async fn heartbeat(&self) -> Result<()>;

    /// Report metrics
    async fn report_metrics(&self, metrics: AgentMetrics) -> Result<()>;

    /// Get remote configuration
    async fn get_config(&self) -> Result<serde_json::Value>;
}

/// Agent metrics for reporting.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentMetrics {
    /// Number of requests processed
    pub requests: u64,
    /// Number of errors
    pub errors: u64,
    /// Average response time in ms
    pub avg_response_time_ms: f64,
    /// Token usage
    pub tokens_used: u64,
    /// Custom metrics
    pub custom: HashMap<String, f64>,
}

impl Default for AgentMetrics {
    fn default() -> Self {
        Self {
            requests: 0,
            errors: 0,
            avg_response_time_ms: 0.0,
            tokens_used: 0,
            custom: HashMap::new(),
        }
    }
}

impl AgentMetrics {
    /// Create new metrics
    pub fn new() -> Self {
        Self::default()
    }

    /// Add a custom metric
    pub fn custom(mut self, key: impl Into<String>, value: f64) -> Self {
        self.custom.insert(key.into(), value);
        self
    }
}

// =============================================================================
// BOT PROTOCOL
// =============================================================================

/// Bot protocol for chat integrations.
#[async_trait]
pub trait BotProtocol: Send + Sync {
    /// Get bot name
    fn name(&self) -> &str;

    /// Handle incoming message
    async fn on_message(&self, message: BotMessage) -> Result<BotResponse>;

    /// Handle command
    async fn on_command(&self, command: &str, args: &[&str]) -> Result<BotResponse>;

    /// Start the bot
    async fn start(&mut self) -> Result<()>;

    /// Stop the bot
    async fn stop(&mut self) -> Result<()>;
}

/// A bot message.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BotMessage {
    /// Message ID
    pub id: String,
    /// Sender ID
    pub sender_id: String,
    /// Sender name
    pub sender_name: Option<String>,
    /// Message content
    pub content: String,
    /// Channel/room ID
    pub channel_id: Option<String>,
    /// Timestamp
    pub timestamp: u64,
    /// Metadata
    pub metadata: HashMap<String, String>,
}

impl BotMessage {
    /// Create a new bot message
    pub fn new(sender_id: impl Into<String>, content: impl Into<String>) -> Self {
        Self {
            id: uuid::Uuid::new_v4().to_string(),
            sender_id: sender_id.into(),
            sender_name: None,
            content: content.into(),
            channel_id: None,
            timestamp: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs(),
            metadata: HashMap::new(),
        }
    }
}

/// A bot response.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BotResponse {
    /// Response content
    pub content: String,
    /// Reply to message ID
    pub reply_to: Option<String>,
    /// Attachments
    pub attachments: Vec<BotAttachment>,
    /// Actions/buttons
    pub actions: Vec<BotAction>,
}

impl BotResponse {
    /// Create a simple text response
    pub fn text(content: impl Into<String>) -> Self {
        Self {
            content: content.into(),
            reply_to: None,
            attachments: Vec::new(),
            actions: Vec::new(),
        }
    }

    /// Set reply to
    pub fn reply_to(mut self, message_id: impl Into<String>) -> Self {
        self.reply_to = Some(message_id.into());
        self
    }

    /// Add an attachment
    pub fn attachment(mut self, attachment: BotAttachment) -> Self {
        self.attachments.push(attachment);
        self
    }

    /// Add an action
    pub fn action(mut self, action: BotAction) -> Self {
        self.actions.push(action);
        self
    }
}

/// A bot attachment.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BotAttachment {
    /// Attachment type
    pub attachment_type: String,
    /// URL or data
    pub url: String,
    /// Title
    pub title: Option<String>,
}

/// A bot action/button.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BotAction {
    /// Action ID
    pub id: String,
    /// Action label
    pub label: String,
    /// Action type
    pub action_type: String,
    /// Action value
    pub value: Option<String>,
}

// =============================================================================
// TESTS
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    struct MockAgent {
        name: String,
    }

    #[async_trait]
    impl AgentProtocol for MockAgent {
        fn name(&self) -> &str {
            &self.name
        }

        fn chat(&self, prompt: &str) -> Result<String> {
            Ok(format!("Response to: {}", prompt))
        }

        async fn achat(&self, prompt: &str) -> Result<String> {
            Ok(format!("Async response to: {}", prompt))
        }
    }

    #[test]
    fn test_mock_agent_protocol() {
        let agent = MockAgent {
            name: "TestAgent".to_string(),
        };

        assert_eq!(agent.name(), "TestAgent");
        let response = agent.chat("Hello").unwrap();
        assert!(response.contains("Hello"));
    }

    #[tokio::test]
    async fn test_mock_agent_async() {
        let agent = MockAgent {
            name: "TestAgent".to_string(),
        };

        let response = agent.achat("Hello").await.unwrap();
        assert!(response.contains("Async"));
    }

    #[test]
    fn test_memory_message() {
        let msg = MemoryMessage::new("user", "Hello");
        assert_eq!(msg.role, "user");
        assert_eq!(msg.content, "Hello");
        assert!(msg.timestamp > 0);
    }

    #[test]
    fn test_llm_message() {
        let system = LlmMessage::system("You are helpful");
        let user = LlmMessage::user("Hello");
        let assistant = LlmMessage::assistant("Hi there");

        assert_eq!(system.role, "system");
        assert_eq!(user.role, "user");
        assert_eq!(assistant.role, "assistant");
    }

    #[test]
    fn test_agent_os_config() {
        let config = AgentOSConfig::new("https://custom.url")
            .api_key("test-key")
            .agent_id("agent-123")
            .no_telemetry();

        assert_eq!(config.url, "https://custom.url");
        assert_eq!(config.api_key, Some("test-key".to_string()));
        assert_eq!(config.agent_id, Some("agent-123".to_string()));
        assert!(!config.telemetry);
    }

    #[test]
    fn test_agent_metrics() {
        let metrics = AgentMetrics::new()
            .custom("latency_p99", 150.0)
            .custom("cache_hit_rate", 0.85);

        assert_eq!(metrics.custom.len(), 2);
        assert_eq!(metrics.custom.get("latency_p99"), Some(&150.0));
    }

    #[test]
    fn test_bot_message() {
        let msg = BotMessage::new("user123", "Hello bot");
        assert_eq!(msg.sender_id, "user123");
        assert_eq!(msg.content, "Hello bot");
        assert!(!msg.id.is_empty());
    }

    #[test]
    fn test_bot_response() {
        let response = BotResponse::text("Hello!")
            .reply_to("msg-123")
            .action(BotAction {
                id: "btn1".to_string(),
                label: "Click me".to_string(),
                action_type: "button".to_string(),
                value: None,
            });

        assert_eq!(response.content, "Hello!");
        assert_eq!(response.reply_to, Some("msg-123".to_string()));
        assert_eq!(response.actions.len(), 1);
    }

    #[test]
    fn test_tool_schema() {
        let schema = ToolSchema {
            name: "search".to_string(),
            description: "Search the web".to_string(),
            parameters: serde_json::json!({
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                }
            }),
        };

        assert_eq!(schema.name, "search");
    }

    #[test]
    fn test_llm_response() {
        let response = LlmResponse {
            content: "Hello!".to_string(),
            tool_calls: vec![ToolCall {
                id: "call-1".to_string(),
                name: "search".to_string(),
                arguments: serde_json::json!({"query": "test"}),
            }],
            usage: Some(TokenUsage {
                prompt_tokens: 10,
                completion_tokens: 5,
                total_tokens: 15,
            }),
        };

        assert_eq!(response.tool_calls.len(), 1);
        assert_eq!(response.usage.unwrap().total_tokens, 15);
    }
}
