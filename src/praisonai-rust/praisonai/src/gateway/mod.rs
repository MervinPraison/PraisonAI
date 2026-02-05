//! Gateway Module for PraisonAI Rust SDK
//!
//! Defines protocols and types for gateway/control plane implementations.
//! These enable multi-agent coordination, session management, and real-time communication.
//!
//! # Example
//!
//! ```rust,ignore
//! use praisonai::gateway::{GatewayEvent, EventType, GatewayMessage};
//!
//! let event = GatewayEvent::new(EventType::Message)
//!     .data(serde_json::json!({"text": "Hello"}))
//!     .source("agent-1");
//!
//! let message = GatewayMessage::new("Hello!", "user-1", "session-1");
//! ```

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};
use uuid::Uuid;

use crate::agent::Agent;
use crate::error::Result;

/// Standard gateway event types.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EventType {
    // Connection events
    Connect,
    Disconnect,
    Reconnect,
    
    // Session events
    SessionStart,
    SessionEnd,
    SessionUpdate,
    
    // Agent events
    AgentRegister,
    AgentUnregister,
    AgentStatus,
    
    // Message events
    Message,
    MessageAck,
    Typing,
    
    // System events
    Health,
    Error,
    Broadcast,
}

impl Default for EventType {
    fn default() -> Self {
        Self::Message
    }
}

impl std::fmt::Display for EventType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let s = match self {
            Self::Connect => "connect",
            Self::Disconnect => "disconnect",
            Self::Reconnect => "reconnect",
            Self::SessionStart => "session_start",
            Self::SessionEnd => "session_end",
            Self::SessionUpdate => "session_update",
            Self::AgentRegister => "agent_register",
            Self::AgentUnregister => "agent_unregister",
            Self::AgentStatus => "agent_status",
            Self::Message => "message",
            Self::MessageAck => "message_ack",
            Self::Typing => "typing",
            Self::Health => "health",
            Self::Error => "error",
            Self::Broadcast => "broadcast",
        };
        write!(f, "{}", s)
    }
}

/// Get current timestamp in seconds since UNIX epoch.
fn current_timestamp() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

/// A gateway event with metadata.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GatewayEvent {
    /// The event type
    #[serde(rename = "type")]
    pub event_type: EventType,
    /// Event payload
    pub data: serde_json::Value,
    /// Unique event identifier
    pub event_id: String,
    /// Event creation time (Unix timestamp)
    pub timestamp: f64,
    /// Source identifier (agent_id, client_id, etc.)
    pub source: Option<String>,
    /// Target identifier (optional, for directed events)
    pub target: Option<String>,
}

impl GatewayEvent {
    /// Create a new gateway event.
    pub fn new(event_type: EventType) -> Self {
        Self {
            event_type,
            data: serde_json::json!({}),
            event_id: Uuid::new_v4().to_string(),
            timestamp: current_timestamp(),
            source: None,
            target: None,
        }
    }

    /// Set event data.
    pub fn data(mut self, data: serde_json::Value) -> Self {
        self.data = data;
        self
    }

    /// Set source identifier.
    pub fn source(mut self, source: impl Into<String>) -> Self {
        self.source = Some(source.into());
        self
    }

    /// Set target identifier.
    pub fn target(mut self, target: impl Into<String>) -> Self {
        self.target = Some(target.into());
        self
    }

    /// Convert to dictionary for serialization.
    pub fn to_dict(&self) -> HashMap<String, serde_json::Value> {
        let mut map = HashMap::new();
        map.insert("type".to_string(), serde_json::json!(self.event_type.to_string()));
        map.insert("data".to_string(), self.data.clone());
        map.insert("event_id".to_string(), serde_json::json!(self.event_id));
        map.insert("timestamp".to_string(), serde_json::json!(self.timestamp));
        map.insert("source".to_string(), serde_json::json!(self.source));
        map.insert("target".to_string(), serde_json::json!(self.target));
        map
    }

    /// Create from dictionary.
    pub fn from_dict(data: &HashMap<String, serde_json::Value>) -> Self {
        let event_type = data
            .get("type")
            .and_then(|v| v.as_str())
            .and_then(|s| serde_json::from_str(&format!("\"{}\"", s)).ok())
            .unwrap_or_default();

        Self {
            event_type,
            data: data.get("data").cloned().unwrap_or(serde_json::json!({})),
            event_id: data
                .get("event_id")
                .and_then(|v| v.as_str())
                .map(String::from)
                .unwrap_or_else(|| Uuid::new_v4().to_string()),
            timestamp: data
                .get("timestamp")
                .and_then(|v| v.as_f64())
                .unwrap_or_else(current_timestamp),
            source: data.get("source").and_then(|v| v.as_str()).map(String::from),
            target: data.get("target").and_then(|v| v.as_str()).map(String::from),
        }
    }
}

impl Default for GatewayEvent {
    fn default() -> Self {
        Self::new(EventType::Message)
    }
}

/// A message sent through the gateway.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GatewayMessage {
    /// Message content (text or structured data)
    pub content: serde_json::Value,
    /// Sender identifier
    pub sender_id: String,
    /// Session this message belongs to
    pub session_id: String,
    /// Unique message identifier
    pub message_id: String,
    /// Message creation time (Unix timestamp)
    pub timestamp: f64,
    /// Additional message metadata
    pub metadata: HashMap<String, serde_json::Value>,
    /// ID of message being replied to (optional)
    pub reply_to: Option<String>,
}

impl GatewayMessage {
    /// Create a new gateway message.
    pub fn new(
        content: impl Into<serde_json::Value>,
        sender_id: impl Into<String>,
        session_id: impl Into<String>,
    ) -> Self {
        Self {
            content: content.into(),
            sender_id: sender_id.into(),
            session_id: session_id.into(),
            message_id: Uuid::new_v4().to_string(),
            timestamp: current_timestamp(),
            metadata: HashMap::new(),
            reply_to: None,
        }
    }

    /// Create a text message.
    pub fn text(
        text: impl Into<String>,
        sender_id: impl Into<String>,
        session_id: impl Into<String>,
    ) -> Self {
        Self::new(serde_json::json!(text.into()), sender_id, session_id)
    }

    /// Set reply_to message ID.
    pub fn reply_to(mut self, message_id: impl Into<String>) -> Self {
        self.reply_to = Some(message_id.into());
        self
    }

    /// Add metadata.
    pub fn metadata(mut self, key: impl Into<String>, value: serde_json::Value) -> Self {
        self.metadata.insert(key.into(), value);
        self
    }

    /// Get text content if available.
    pub fn text_content(&self) -> Option<&str> {
        self.content.as_str()
    }

    /// Convert to dictionary for serialization.
    pub fn to_dict(&self) -> HashMap<String, serde_json::Value> {
        let mut map = HashMap::new();
        map.insert("content".to_string(), self.content.clone());
        map.insert("sender_id".to_string(), serde_json::json!(self.sender_id));
        map.insert("session_id".to_string(), serde_json::json!(self.session_id));
        map.insert("message_id".to_string(), serde_json::json!(self.message_id));
        map.insert("timestamp".to_string(), serde_json::json!(self.timestamp));
        map.insert("metadata".to_string(), serde_json::json!(self.metadata));
        map.insert("reply_to".to_string(), serde_json::json!(self.reply_to));
        map
    }

    /// Create from dictionary.
    pub fn from_dict(data: &HashMap<String, serde_json::Value>) -> Self {
        Self {
            content: data.get("content").cloned().unwrap_or(serde_json::json!("")),
            sender_id: data
                .get("sender_id")
                .and_then(|v| v.as_str())
                .map(String::from)
                .unwrap_or_else(|| "unknown".to_string()),
            session_id: data
                .get("session_id")
                .and_then(|v| v.as_str())
                .map(String::from)
                .unwrap_or_else(|| "default".to_string()),
            message_id: data
                .get("message_id")
                .and_then(|v| v.as_str())
                .map(String::from)
                .unwrap_or_else(|| Uuid::new_v4().to_string()),
            timestamp: data
                .get("timestamp")
                .and_then(|v| v.as_f64())
                .unwrap_or_else(current_timestamp),
            metadata: data
                .get("metadata")
                .and_then(|v| serde_json::from_value(v.clone()).ok())
                .unwrap_or_default(),
            reply_to: data.get("reply_to").and_then(|v| v.as_str()).map(String::from),
        }
    }
}

/// Configuration for a gateway.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GatewayConfig {
    /// Host to bind to
    pub host: String,
    /// Port to listen on
    pub port: u16,
    /// Maximum connections
    pub max_connections: usize,
    /// Session timeout in seconds
    pub session_timeout: u64,
    /// Enable authentication
    pub auth_enabled: bool,
    /// Authentication token (if auth_enabled)
    pub auth_token: Option<String>,
    /// Enable TLS
    pub tls_enabled: bool,
    /// TLS certificate path
    pub tls_cert_path: Option<String>,
    /// TLS key path
    pub tls_key_path: Option<String>,
}

impl Default for GatewayConfig {
    fn default() -> Self {
        Self {
            host: "127.0.0.1".to_string(),
            port: 8765,
            max_connections: 1000,
            session_timeout: 3600,
            auth_enabled: false,
            auth_token: None,
            tls_enabled: false,
            tls_cert_path: None,
            tls_key_path: None,
        }
    }
}

impl GatewayConfig {
    /// Create a new config with defaults.
    pub fn new() -> Self {
        Self::default()
    }

    /// Set host.
    pub fn host(mut self, host: impl Into<String>) -> Self {
        self.host = host.into();
        self
    }

    /// Set port.
    pub fn port(mut self, port: u16) -> Self {
        self.port = port;
        self
    }

    /// Set max connections.
    pub fn max_connections(mut self, max: usize) -> Self {
        self.max_connections = max;
        self
    }

    /// Set session timeout.
    pub fn session_timeout(mut self, timeout: u64) -> Self {
        self.session_timeout = timeout;
        self
    }

    /// Enable authentication with token.
    pub fn auth(mut self, token: impl Into<String>) -> Self {
        self.auth_enabled = true;
        self.auth_token = Some(token.into());
        self
    }

    /// Enable TLS.
    pub fn tls(mut self, cert_path: impl Into<String>, key_path: impl Into<String>) -> Self {
        self.tls_enabled = true;
        self.tls_cert_path = Some(cert_path.into());
        self.tls_key_path = Some(key_path.into());
        self
    }
}

/// Protocol for gateway session management.
///
/// Sessions track conversations between clients and agents,
/// maintaining state and message history.
#[async_trait]
pub trait GatewaySessionProtocol: Send + Sync {
    /// Unique session identifier.
    fn session_id(&self) -> &str;

    /// ID of the agent handling this session.
    fn agent_id(&self) -> Option<&str>;

    /// ID of the client in this session.
    fn client_id(&self) -> Option<&str>;

    /// Whether the session is currently active.
    fn is_active(&self) -> bool;

    /// Session creation timestamp.
    fn created_at(&self) -> f64;

    /// Last activity timestamp.
    fn last_activity(&self) -> f64;

    /// Get session state.
    fn get_state(&self) -> HashMap<String, serde_json::Value>;

    /// Set a session state value.
    fn set_state(&mut self, key: &str, value: serde_json::Value);

    /// Add a message to the session history.
    fn add_message(&mut self, message: GatewayMessage);

    /// Get session message history.
    fn get_messages(&self, limit: Option<usize>) -> Vec<GatewayMessage>;

    /// Close the session.
    fn close(&mut self);
}

/// Protocol for gateway client connections.
///
/// Clients are external connections (WebSocket, HTTP, etc.)
/// that communicate with agents through the gateway.
#[async_trait]
pub trait GatewayClientProtocol: Send + Sync {
    /// Unique client identifier.
    fn client_id(&self) -> &str;

    /// Whether the client is currently connected.
    fn is_connected(&self) -> bool;

    /// Connection timestamp.
    fn connected_at(&self) -> f64;

    /// Send an event to the client.
    async fn send(&self, event: GatewayEvent) -> Result<()>;

    /// Receive an event from the client.
    async fn receive(&self) -> Result<GatewayEvent>;

    /// Close the client connection.
    async fn close(&self) -> Result<()>;
}

/// Protocol for gateway/control plane implementations.
///
/// The gateway coordinates communication between clients and agents,
/// manages sessions, and provides health/presence tracking.
#[async_trait]
pub trait GatewayProtocol: Send + Sync {
    /// Whether the gateway is currently running.
    fn is_running(&self) -> bool;

    /// Port the gateway is listening on.
    fn port(&self) -> u16;

    /// Host the gateway is bound to.
    fn host(&self) -> &str;

    /// Start the gateway server.
    async fn start(&mut self) -> Result<()>;

    /// Stop the gateway server.
    async fn stop(&mut self) -> Result<()>;

    /// Register an agent with the gateway.
    fn register_agent(&mut self, agent: Arc<Agent>, agent_id: Option<String>) -> String;

    /// Unregister an agent from the gateway.
    fn unregister_agent(&mut self, agent_id: &str) -> bool;

    /// Get a registered agent by ID.
    fn get_agent(&self, agent_id: &str) -> Option<Arc<Agent>>;

    /// List all registered agent IDs.
    fn list_agents(&self) -> Vec<String>;

    /// Create a new session.
    fn create_session(
        &mut self,
        agent_id: &str,
        client_id: Option<String>,
        session_id: Option<String>,
    ) -> Result<Box<dyn GatewaySessionProtocol>>;

    /// Get a session by ID.
    fn get_session(&self, session_id: &str) -> Option<&dyn GatewaySessionProtocol>;

    /// Close a session.
    fn close_session(&mut self, session_id: &str) -> bool;

    /// List session IDs, optionally filtered by agent.
    fn list_sessions(&self, agent_id: Option<&str>) -> Vec<String>;

    /// Emit an event to registered handlers.
    async fn emit(&self, event: GatewayEvent) -> Result<()>;

    /// Broadcast an event to all connected clients.
    async fn broadcast(&self, event: GatewayEvent, exclude: Option<Vec<String>>) -> Result<()>;

    /// Get gateway health status.
    fn health(&self) -> GatewayHealth;
}

/// Gateway health status.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GatewayHealth {
    /// Health status
    pub status: String,
    /// Seconds since start
    pub uptime: f64,
    /// Number of registered agents
    pub agents: usize,
    /// Number of active sessions
    pub sessions: usize,
    /// Number of connected clients
    pub clients: usize,
}

impl Default for GatewayHealth {
    fn default() -> Self {
        Self {
            status: "healthy".to_string(),
            uptime: 0.0,
            agents: 0,
            sessions: 0,
            clients: 0,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_event_type_display() {
        assert_eq!(EventType::Connect.to_string(), "connect");
        assert_eq!(EventType::Message.to_string(), "message");
        assert_eq!(EventType::SessionStart.to_string(), "session_start");
    }

    #[test]
    fn test_gateway_event_new() {
        let event = GatewayEvent::new(EventType::Message);
        assert_eq!(event.event_type, EventType::Message);
        assert!(!event.event_id.is_empty());
        assert!(event.timestamp > 0.0);
    }

    #[test]
    fn test_gateway_event_builder() {
        let event = GatewayEvent::new(EventType::Message)
            .data(serde_json::json!({"text": "Hello"}))
            .source("agent-1")
            .target("client-1");

        assert_eq!(event.data["text"], "Hello");
        assert_eq!(event.source, Some("agent-1".to_string()));
        assert_eq!(event.target, Some("client-1".to_string()));
    }

    #[test]
    fn test_gateway_event_to_dict() {
        let event = GatewayEvent::new(EventType::Message)
            .source("test");

        let dict = event.to_dict();
        assert_eq!(dict.get("type").unwrap(), "message");
        assert_eq!(dict.get("source").unwrap(), "test");
    }

    #[test]
    fn test_gateway_message_new() {
        let msg = GatewayMessage::new(
            serde_json::json!("Hello"),
            "user-1",
            "session-1",
        );

        assert_eq!(msg.content, serde_json::json!("Hello"));
        assert_eq!(msg.sender_id, "user-1");
        assert_eq!(msg.session_id, "session-1");
        assert!(!msg.message_id.is_empty());
    }

    #[test]
    fn test_gateway_message_text() {
        let msg = GatewayMessage::text("Hello world", "user-1", "session-1");
        assert_eq!(msg.text_content(), Some("Hello world"));
    }

    #[test]
    fn test_gateway_message_builder() {
        let msg = GatewayMessage::text("Hello", "user-1", "session-1")
            .reply_to("msg-123")
            .metadata("priority", serde_json::json!("high"));

        assert_eq!(msg.reply_to, Some("msg-123".to_string()));
        assert_eq!(msg.metadata.get("priority").unwrap(), "high");
    }

    #[test]
    fn test_gateway_message_to_dict() {
        let msg = GatewayMessage::text("Hello", "user-1", "session-1");
        let dict = msg.to_dict();

        assert_eq!(dict.get("sender_id").unwrap(), "user-1");
        assert_eq!(dict.get("session_id").unwrap(), "session-1");
    }

    #[test]
    fn test_gateway_config_default() {
        let config = GatewayConfig::default();
        assert_eq!(config.host, "127.0.0.1");
        assert_eq!(config.port, 8765);
        assert!(!config.auth_enabled);
        assert!(!config.tls_enabled);
    }

    #[test]
    fn test_gateway_config_builder() {
        let config = GatewayConfig::new()
            .host("0.0.0.0")
            .port(9000)
            .max_connections(500)
            .auth("secret-token");

        assert_eq!(config.host, "0.0.0.0");
        assert_eq!(config.port, 9000);
        assert_eq!(config.max_connections, 500);
        assert!(config.auth_enabled);
        assert_eq!(config.auth_token, Some("secret-token".to_string()));
    }

    #[test]
    fn test_gateway_config_tls() {
        let config = GatewayConfig::new()
            .tls("/path/to/cert.pem", "/path/to/key.pem");

        assert!(config.tls_enabled);
        assert_eq!(config.tls_cert_path, Some("/path/to/cert.pem".to_string()));
        assert_eq!(config.tls_key_path, Some("/path/to/key.pem".to_string()));
    }

    #[test]
    fn test_gateway_health_default() {
        let health = GatewayHealth::default();
        assert_eq!(health.status, "healthy");
        assert_eq!(health.agents, 0);
        assert_eq!(health.sessions, 0);
    }
}
