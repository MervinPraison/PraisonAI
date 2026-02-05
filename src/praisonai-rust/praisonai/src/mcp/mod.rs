//! MCP (Model Context Protocol) Integration Module
//!
//! This module provides MCP integration for agents:
//! - `MCP` - Main MCP client
//! - `MCPConfig` - Configuration for MCP connections
//! - `MCPCall` - MCP tool call
//! - `MCPServer` - MCP server for exposing tools
//!
//! # Example
//!
//! ```ignore
//! use praisonai::mcp::{MCP, MCPConfig};
//!
//! let mcp = MCP::new()
//!     .server("npx", &["-y", "@anthropic/mcp-server-memory"])
//!     .build()?;
//!
//! let tools = mcp.list_tools().await?;
//! ```

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use crate::error::{Error, Result};

// =============================================================================
// MCP TRANSPORT
// =============================================================================

/// Transport type for MCP connections.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TransportType {
    /// Standard input/output (subprocess)
    #[default]
    Stdio,
    /// Server-Sent Events (legacy HTTP+SSE)
    Sse,
    /// Streamable HTTP (current standard)
    HttpStream,
    /// WebSocket
    WebSocket,
}

/// Transport configuration for MCP.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TransportConfig {
    /// Transport type
    pub transport_type: TransportType,
    /// Command for stdio transport
    pub command: Option<String>,
    /// Arguments for stdio transport
    pub args: Vec<String>,
    /// URL for HTTP/WebSocket transport
    pub url: Option<String>,
    /// Headers for HTTP transport
    pub headers: HashMap<String, String>,
    /// Environment variables
    pub env: HashMap<String, String>,
    /// Connection timeout in seconds
    pub timeout: u32,
}

impl Default for TransportConfig {
    fn default() -> Self {
        Self {
            transport_type: TransportType::Stdio,
            command: None,
            args: Vec::new(),
            url: None,
            headers: HashMap::new(),
            env: HashMap::new(),
            timeout: 30,
        }
    }
}

impl TransportConfig {
    /// Create a new stdio transport config
    pub fn stdio(command: impl Into<String>, args: &[&str]) -> Self {
        Self {
            transport_type: TransportType::Stdio,
            command: Some(command.into()),
            args: args.iter().map(|s| s.to_string()).collect(),
            ..Default::default()
        }
    }

    /// Create a new HTTP transport config
    pub fn http(url: impl Into<String>) -> Self {
        Self {
            transport_type: TransportType::HttpStream,
            url: Some(url.into()),
            ..Default::default()
        }
    }

    /// Create a new WebSocket transport config
    pub fn websocket(url: impl Into<String>) -> Self {
        Self {
            transport_type: TransportType::WebSocket,
            url: Some(url.into()),
            ..Default::default()
        }
    }

    /// Add an environment variable
    pub fn env(mut self, key: impl Into<String>, value: impl Into<String>) -> Self {
        self.env.insert(key.into(), value.into());
        self
    }

    /// Add a header
    pub fn header(mut self, key: impl Into<String>, value: impl Into<String>) -> Self {
        self.headers.insert(key.into(), value.into());
        self
    }

    /// Set timeout
    pub fn timeout(mut self, timeout: u32) -> Self {
        self.timeout = timeout;
        self
    }
}

// =============================================================================
// MCP CONFIG
// =============================================================================

/// Security configuration for MCP.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SecurityConfig {
    /// Allow file system access
    pub allow_fs: bool,
    /// Allow network access
    pub allow_network: bool,
    /// Allow environment variable access
    pub allow_env: bool,
    /// Allowed hosts for network access
    pub allowed_hosts: Vec<String>,
    /// Allowed paths for file system access
    pub allowed_paths: Vec<String>,
}

impl Default for SecurityConfig {
    fn default() -> Self {
        Self {
            allow_fs: false,
            allow_network: false,
            allow_env: false,
            allowed_hosts: Vec::new(),
            allowed_paths: Vec::new(),
        }
    }
}

impl SecurityConfig {
    /// Create a permissive security config
    pub fn permissive() -> Self {
        Self {
            allow_fs: true,
            allow_network: true,
            allow_env: true,
            allowed_hosts: vec!["*".to_string()],
            allowed_paths: vec!["*".to_string()],
        }
    }

    /// Create a restrictive security config
    pub fn restrictive() -> Self {
        Self::default()
    }

    /// Allow file system access
    pub fn allow_fs(mut self, allow: bool) -> Self {
        self.allow_fs = allow;
        self
    }

    /// Allow network access
    pub fn allow_network(mut self, allow: bool) -> Self {
        self.allow_network = allow;
        self
    }

    /// Add allowed host
    pub fn allowed_host(mut self, host: impl Into<String>) -> Self {
        self.allowed_hosts.push(host.into());
        self
    }

    /// Add allowed path
    pub fn allowed_path(mut self, path: impl Into<String>) -> Self {
        self.allowed_paths.push(path.into());
        self
    }
}

/// Configuration for MCP client.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MCPConfig {
    /// Server name
    pub name: String,
    /// Transport configuration
    pub transport: TransportConfig,
    /// Security configuration
    pub security: SecurityConfig,
    /// Auto-reconnect on disconnect
    pub auto_reconnect: bool,
    /// Maximum reconnect attempts
    pub max_reconnect_attempts: u32,
    /// Enable debug logging
    pub debug: bool,
}

impl Default for MCPConfig {
    fn default() -> Self {
        Self {
            name: "mcp-server".to_string(),
            transport: TransportConfig::default(),
            security: SecurityConfig::default(),
            auto_reconnect: true,
            max_reconnect_attempts: 3,
            debug: false,
        }
    }
}

impl MCPConfig {
    /// Create a new MCPConfig
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            ..Default::default()
        }
    }

    /// Set transport
    pub fn transport(mut self, transport: TransportConfig) -> Self {
        self.transport = transport;
        self
    }

    /// Set security
    pub fn security(mut self, security: SecurityConfig) -> Self {
        self.security = security;
        self
    }

    /// Enable debug mode
    pub fn debug(mut self, debug: bool) -> Self {
        self.debug = debug;
        self
    }
}

// =============================================================================
// MCP TOOL
// =============================================================================

/// An MCP tool definition.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MCPTool {
    /// Tool name
    pub name: String,
    /// Tool description
    pub description: String,
    /// Input schema (JSON Schema)
    pub input_schema: serde_json::Value,
}

impl MCPTool {
    /// Create a new MCP tool
    pub fn new(name: impl Into<String>, description: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            description: description.into(),
            input_schema: serde_json::json!({"type": "object", "properties": {}}),
        }
    }

    /// Set input schema
    pub fn input_schema(mut self, schema: serde_json::Value) -> Self {
        self.input_schema = schema;
        self
    }
}

// =============================================================================
// MCP CALL
// =============================================================================

/// An MCP tool call request.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MCPCall {
    /// Tool name
    pub name: String,
    /// Tool arguments
    pub arguments: serde_json::Value,
    /// Call ID
    pub id: String,
}

impl MCPCall {
    /// Create a new MCP call
    pub fn new(name: impl Into<String>, arguments: serde_json::Value) -> Self {
        Self {
            name: name.into(),
            arguments,
            id: uuid::Uuid::new_v4().to_string(),
        }
    }
}

/// Result of an MCP tool call.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MCPCallResult {
    /// Call ID
    pub id: String,
    /// Result content
    pub content: Vec<MCPContent>,
    /// Whether the call was successful
    pub is_error: bool,
}

/// MCP content types.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum MCPContent {
    /// Text content
    Text { text: String },
    /// Image content
    Image { data: String, mime_type: String },
    /// Resource content
    Resource { uri: String, text: Option<String> },
}

impl MCPContent {
    /// Create text content
    pub fn text(text: impl Into<String>) -> Self {
        Self::Text { text: text.into() }
    }

    /// Create image content
    pub fn image(data: impl Into<String>, mime_type: impl Into<String>) -> Self {
        Self::Image {
            data: data.into(),
            mime_type: mime_type.into(),
        }
    }
}

// =============================================================================
// MCP RESOURCE
// =============================================================================

/// An MCP resource.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MCPResource {
    /// Resource URI
    pub uri: String,
    /// Resource name
    pub name: String,
    /// Resource description
    pub description: Option<String>,
    /// MIME type
    pub mime_type: Option<String>,
}

impl MCPResource {
    /// Create a new resource
    pub fn new(uri: impl Into<String>, name: impl Into<String>) -> Self {
        Self {
            uri: uri.into(),
            name: name.into(),
            description: None,
            mime_type: None,
        }
    }
}

// =============================================================================
// MCP PROMPT
// =============================================================================

/// An MCP prompt template.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MCPPrompt {
    /// Prompt name
    pub name: String,
    /// Prompt description
    pub description: Option<String>,
    /// Prompt arguments
    pub arguments: Vec<MCPPromptArgument>,
}

/// An MCP prompt argument.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MCPPromptArgument {
    /// Argument name
    pub name: String,
    /// Argument description
    pub description: Option<String>,
    /// Whether the argument is required
    pub required: bool,
}

// =============================================================================
// MCP CLIENT
// =============================================================================

/// Connection status for MCP.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum ConnectionStatus {
    /// Not connected
    #[default]
    Disconnected,
    /// Connecting
    Connecting,
    /// Connected
    Connected,
    /// Error state
    Error,
}

/// Main MCP client.
#[derive(Debug)]
pub struct MCP {
    /// Configuration
    pub config: MCPConfig,
    /// Connection status
    pub status: ConnectionStatus,
    /// Available tools
    tools: Vec<MCPTool>,
    /// Available resources
    resources: Vec<MCPResource>,
    /// Available prompts
    prompts: Vec<MCPPrompt>,
}

impl Default for MCP {
    fn default() -> Self {
        Self {
            config: MCPConfig::default(),
            status: ConnectionStatus::Disconnected,
            tools: Vec::new(),
            resources: Vec::new(),
            prompts: Vec::new(),
        }
    }
}

impl MCP {
    /// Create a new MCP builder
    pub fn new() -> MCPBuilder {
        MCPBuilder::default()
    }

    /// Get connection status
    pub fn status(&self) -> ConnectionStatus {
        self.status
    }

    /// Check if connected
    pub fn is_connected(&self) -> bool {
        self.status == ConnectionStatus::Connected
    }

    /// Connect to the MCP server (placeholder)
    pub async fn connect(&mut self) -> Result<()> {
        self.status = ConnectionStatus::Connecting;
        // Actual implementation would start the subprocess or connect to URL
        self.status = ConnectionStatus::Connected;
        Ok(())
    }

    /// Disconnect from the MCP server
    pub async fn disconnect(&mut self) -> Result<()> {
        self.status = ConnectionStatus::Disconnected;
        Ok(())
    }

    /// List available tools (placeholder)
    pub async fn list_tools(&self) -> Result<Vec<MCPTool>> {
        Ok(self.tools.clone())
    }

    /// List available resources (placeholder)
    pub async fn list_resources(&self) -> Result<Vec<MCPResource>> {
        Ok(self.resources.clone())
    }

    /// List available prompts (placeholder)
    pub async fn list_prompts(&self) -> Result<Vec<MCPPrompt>> {
        Ok(self.prompts.clone())
    }

    /// Call a tool (placeholder)
    pub async fn call_tool(&self, call: MCPCall) -> Result<MCPCallResult> {
        if !self.is_connected() {
            return Err(Error::workflow("MCP not connected"));
        }

        // Placeholder - actual implementation would send request to server
        Ok(MCPCallResult {
            id: call.id,
            content: vec![MCPContent::text(format!(
                "Result of calling {} with {:?}",
                call.name, call.arguments
            ))],
            is_error: false,
        })
    }

    /// Read a resource (placeholder)
    pub async fn read_resource(&self, uri: &str) -> Result<MCPContent> {
        if !self.is_connected() {
            return Err(Error::workflow("MCP not connected"));
        }

        Ok(MCPContent::Resource {
            uri: uri.to_string(),
            text: Some(format!("Content of resource: {}", uri)),
        })
    }

    /// Get a prompt (placeholder)
    pub async fn get_prompt(&self, name: &str, args: HashMap<String, String>) -> Result<String> {
        if !self.is_connected() {
            return Err(Error::workflow("MCP not connected"));
        }

        Ok(format!("Prompt '{}' with args: {:?}", name, args))
    }
}

/// Builder for MCP
#[derive(Debug, Default)]
pub struct MCPBuilder {
    config: MCPConfig,
    tools: Vec<MCPTool>,
}

impl MCPBuilder {
    /// Set server name
    pub fn name(mut self, name: impl Into<String>) -> Self {
        self.config.name = name.into();
        self
    }

    /// Set stdio server
    pub fn server(mut self, command: impl Into<String>, args: &[&str]) -> Self {
        self.config.transport = TransportConfig::stdio(command, args);
        self
    }

    /// Set HTTP server
    pub fn http(mut self, url: impl Into<String>) -> Self {
        self.config.transport = TransportConfig::http(url);
        self
    }

    /// Set WebSocket server
    pub fn websocket(mut self, url: impl Into<String>) -> Self {
        self.config.transport = TransportConfig::websocket(url);
        self
    }

    /// Set config
    pub fn config(mut self, config: MCPConfig) -> Self {
        self.config = config;
        self
    }

    /// Set security
    pub fn security(mut self, security: SecurityConfig) -> Self {
        self.config.security = security;
        self
    }

    /// Add a tool (for testing)
    pub fn tool(mut self, tool: MCPTool) -> Self {
        self.tools.push(tool);
        self
    }

    /// Build the MCP client
    pub fn build(self) -> Result<MCP> {
        Ok(MCP {
            config: self.config,
            status: ConnectionStatus::Disconnected,
            tools: self.tools,
            resources: Vec::new(),
            prompts: Vec::new(),
        })
    }
}

// =============================================================================
// MCP SERVER
// =============================================================================

/// MCP server for exposing tools.
#[derive(Debug)]
pub struct MCPServer {
    /// Server name
    pub name: String,
    /// Registered tools
    tools: Vec<MCPTool>,
    /// Registered resources
    resources: Vec<MCPResource>,
    /// Running status
    running: bool,
}

impl Default for MCPServer {
    fn default() -> Self {
        Self {
            name: "praisonai-mcp-server".to_string(),
            tools: Vec::new(),
            resources: Vec::new(),
            running: false,
        }
    }
}

impl MCPServer {
    /// Create a new MCP server
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            ..Default::default()
        }
    }

    /// Register a tool
    pub fn register_tool(&mut self, tool: MCPTool) {
        self.tools.push(tool);
    }

    /// Register a resource
    pub fn register_resource(&mut self, resource: MCPResource) {
        self.resources.push(resource);
    }

    /// Get registered tools
    pub fn tools(&self) -> &[MCPTool] {
        &self.tools
    }

    /// Get registered resources
    pub fn resources(&self) -> &[MCPResource] {
        &self.resources
    }

    /// Check if running
    pub fn is_running(&self) -> bool {
        self.running
    }

    /// Start the server (placeholder)
    pub async fn start(&mut self) -> Result<()> {
        self.running = true;
        Ok(())
    }

    /// Stop the server
    pub async fn stop(&mut self) -> Result<()> {
        self.running = false;
        Ok(())
    }
}

// =============================================================================
// TESTS
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_transport_config_stdio() {
        let config = TransportConfig::stdio("npx", &["-y", "@anthropic/mcp-server"]);
        assert_eq!(config.transport_type, TransportType::Stdio);
        assert_eq!(config.command, Some("npx".to_string()));
        assert_eq!(config.args.len(), 2);
    }

    #[test]
    fn test_transport_config_http() {
        let config = TransportConfig::http("http://localhost:8080")
            .header("Authorization", "Bearer token")
            .timeout(60);

        assert_eq!(config.transport_type, TransportType::HttpStream);
        assert_eq!(config.url, Some("http://localhost:8080".to_string()));
        assert_eq!(config.timeout, 60);
    }

    #[test]
    fn test_security_config() {
        let config = SecurityConfig::permissive();
        assert!(config.allow_fs);
        assert!(config.allow_network);

        let restrictive = SecurityConfig::restrictive();
        assert!(!restrictive.allow_fs);
        assert!(!restrictive.allow_network);
    }

    #[test]
    fn test_mcp_config() {
        let config = MCPConfig::new("test-server")
            .transport(TransportConfig::stdio("node", &["server.js"]))
            .debug(true);

        assert_eq!(config.name, "test-server");
        assert!(config.debug);
    }

    #[test]
    fn test_mcp_tool() {
        let tool = MCPTool::new("search", "Search the web")
            .input_schema(serde_json::json!({
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                }
            }));

        assert_eq!(tool.name, "search");
        assert!(tool.input_schema["properties"]["query"].is_object());
    }

    #[test]
    fn test_mcp_call() {
        let call = MCPCall::new("search", serde_json::json!({"query": "test"}));
        assert_eq!(call.name, "search");
        assert!(!call.id.is_empty());
    }

    #[test]
    fn test_mcp_content() {
        let text = MCPContent::text("Hello");
        match text {
            MCPContent::Text { text } => assert_eq!(text, "Hello"),
            _ => panic!("Expected text content"),
        }
    }

    #[test]
    fn test_mcp_builder() {
        let mcp = MCP::new()
            .name("test")
            .server("npx", &["-y", "@test/server"])
            .build()
            .unwrap();

        assert_eq!(mcp.config.name, "test");
        assert_eq!(mcp.status(), ConnectionStatus::Disconnected);
    }

    #[test]
    fn test_mcp_server() {
        let mut server = MCPServer::new("test-server");
        server.register_tool(MCPTool::new("tool1", "Description"));
        server.register_resource(MCPResource::new("file://test", "test"));

        assert_eq!(server.tools().len(), 1);
        assert_eq!(server.resources().len(), 1);
        assert!(!server.is_running());
    }

    #[tokio::test]
    async fn test_mcp_connect() {
        let mut mcp = MCP::new()
            .name("test")
            .build()
            .unwrap();

        assert!(!mcp.is_connected());
        mcp.connect().await.unwrap();
        assert!(mcp.is_connected());
        mcp.disconnect().await.unwrap();
        assert!(!mcp.is_connected());
    }

    #[tokio::test]
    async fn test_mcp_call_tool() {
        let mut mcp = MCP::new()
            .tool(MCPTool::new("test_tool", "Test"))
            .build()
            .unwrap();

        mcp.connect().await.unwrap();

        let call = MCPCall::new("test_tool", serde_json::json!({}));
        let result = mcp.call_tool(call).await.unwrap();

        assert!(!result.is_error);
        assert!(!result.content.is_empty());
    }

    #[tokio::test]
    async fn test_mcp_server_lifecycle() {
        let mut server = MCPServer::new("test");
        assert!(!server.is_running());

        server.start().await.unwrap();
        assert!(server.is_running());

        server.stop().await.unwrap();
        assert!(!server.is_running());
    }
}
