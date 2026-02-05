//! Plugin Protocols and Functions
//!
//! Provides plugin system types and functions matching the Python SDK:
//! - PluginProtocol, ToolPluginProtocol, HookPluginProtocol
//! - AgentPluginProtocol, LLMPluginProtocol
//! - Plugin discovery and loading functions

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::{Path, PathBuf};

// =============================================================================
// Plugin Metadata
// =============================================================================

/// Plugin metadata extracted from plugin header
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct PluginMetadata {
    /// Plugin name
    pub name: String,
    /// Plugin version
    pub version: String,
    /// Plugin description
    pub description: String,
    /// Plugin author
    pub author: Option<String>,
    /// Plugin dependencies
    #[serde(default)]
    pub dependencies: Vec<String>,
    /// Plugin type (tool, hook, agent, llm)
    pub plugin_type: PluginType,
}

/// Plugin type enumeration
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum PluginType {
    /// Tool-providing plugin
    #[default]
    Tool,
    /// Lifecycle hook plugin
    Hook,
    /// Agent lifecycle plugin
    Agent,
    /// LLM call hook plugin
    Llm,
    /// Generic plugin
    Generic,
}

/// Plugin parse error
#[derive(Debug, Clone, thiserror::Error)]
pub enum PluginParseError {
    /// Missing required field
    #[error("Missing required field: {0}")]
    MissingField(String),
    /// Invalid format
    #[error("Invalid plugin format: {0}")]
    InvalidFormat(String),
    /// IO error
    #[error("IO error: {0}")]
    IoError(String),
}

// =============================================================================
// Plugin Protocols (Traits)
// =============================================================================

/// Base plugin protocol trait
pub trait PluginProtocol: Send + Sync {
    /// Get plugin metadata
    fn metadata(&self) -> &PluginMetadata;
    
    /// Initialize the plugin
    fn initialize(&mut self) -> Result<(), String> {
        Ok(())
    }
    
    /// Cleanup the plugin
    fn cleanup(&mut self) -> Result<(), String> {
        Ok(())
    }
    
    /// Check if plugin is enabled
    fn is_enabled(&self) -> bool {
        true
    }
}

/// Tool-providing plugin protocol
pub trait ToolPluginProtocol: PluginProtocol {
    /// Get tool definitions provided by this plugin
    fn get_tools(&self) -> Vec<ToolDefinition>;
    
    /// Execute a tool by name
    fn execute_tool(&self, name: &str, args: serde_json::Value) -> Result<serde_json::Value, String>;
}

/// Lifecycle hook plugin protocol
pub trait HookPluginProtocol: PluginProtocol {
    /// Called before agent execution
    fn before_agent(&self, _agent_name: &str, _input: &str) -> Result<Option<String>, String> {
        Ok(None)
    }
    
    /// Called after agent execution
    fn after_agent(&self, _agent_name: &str, _output: &str) -> Result<Option<String>, String> {
        Ok(None)
    }
    
    /// Called before tool execution
    fn before_tool(&self, _tool_name: &str, _args: &serde_json::Value) -> Result<Option<serde_json::Value>, String> {
        Ok(None)
    }
    
    /// Called after tool execution
    fn after_tool(&self, _tool_name: &str, _result: &serde_json::Value) -> Result<Option<serde_json::Value>, String> {
        Ok(None)
    }
    
    /// Called on error
    fn on_error(&self, _error: &str) -> Result<(), String> {
        Ok(())
    }
}

/// Agent lifecycle plugin protocol
pub trait AgentPluginProtocol: PluginProtocol {
    /// Called when agent is created
    fn on_agent_created(&self, _agent_name: &str) -> Result<(), String> {
        Ok(())
    }
    
    /// Called when agent starts
    fn on_agent_start(&self, _agent_name: &str, _input: &str) -> Result<(), String> {
        Ok(())
    }
    
    /// Called when agent completes
    fn on_agent_complete(&self, _agent_name: &str, _output: &str) -> Result<(), String> {
        Ok(())
    }
    
    /// Called when agent errors
    fn on_agent_error(&self, _agent_name: &str, _error: &str) -> Result<(), String> {
        Ok(())
    }
}

/// LLM call hook plugin protocol
pub trait LLMPluginProtocol: PluginProtocol {
    /// Called before LLM call
    fn before_llm_call(&self, _messages: &[LLMMessage]) -> Result<Option<Vec<LLMMessage>>, String> {
        Ok(None)
    }
    
    /// Called after LLM call
    fn after_llm_call(&self, _response: &str) -> Result<Option<String>, String> {
        Ok(None)
    }
    
    /// Called on LLM error
    fn on_llm_error(&self, _error: &str) -> Result<(), String> {
        Ok(())
    }
}

// =============================================================================
// Supporting Types
// =============================================================================

/// Tool definition for plugins
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolDefinition {
    /// Tool name
    pub name: String,
    /// Tool description
    pub description: String,
    /// Parameters schema (JSON Schema)
    pub parameters: serde_json::Value,
}

/// LLM Message for plugin hooks
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LLMMessage {
    /// Message role
    pub role: String,
    /// Message content
    pub content: String,
}

// =============================================================================
// Plugin Discovery and Loading Functions
// =============================================================================

/// Parse plugin header from string content
///
/// Extracts metadata from a plugin file's header comments.
pub fn parse_plugin_header(content: &str) -> Result<PluginMetadata, PluginParseError> {
    let mut metadata = PluginMetadata::default();
    let mut found_header = false;
    
    for line in content.lines() {
        let line = line.trim();
        
        // Look for header markers
        if line.starts_with("//!") || line.starts_with("///") || line.starts_with("#") {
            found_header = true;
            let content = line.trim_start_matches("//!").trim_start_matches("///").trim_start_matches("#").trim();
            
            // Parse key-value pairs
            if let Some((key, value)) = content.split_once(':') {
                let key = key.trim().to_lowercase();
                let value = value.trim();
                
                match key.as_str() {
                    "name" | "plugin" => metadata.name = value.to_string(),
                    "version" => metadata.version = value.to_string(),
                    "description" | "desc" => metadata.description = value.to_string(),
                    "author" => metadata.author = Some(value.to_string()),
                    "type" | "plugin_type" => {
                        metadata.plugin_type = match value.to_lowercase().as_str() {
                            "tool" => PluginType::Tool,
                            "hook" => PluginType::Hook,
                            "agent" => PluginType::Agent,
                            "llm" => PluginType::Llm,
                            _ => PluginType::Generic,
                        };
                    }
                    "dependencies" | "deps" => {
                        metadata.dependencies = value.split(',').map(|s| s.trim().to_string()).collect();
                    }
                    _ => {}
                }
            }
        } else if found_header && !line.is_empty() && !line.starts_with("//") && !line.starts_with("#") {
            // End of header
            break;
        }
    }
    
    if metadata.name.is_empty() {
        return Err(PluginParseError::MissingField("name".to_string()));
    }
    
    if metadata.version.is_empty() {
        metadata.version = "0.1.0".to_string();
    }
    
    Ok(metadata)
}

/// Parse plugin header from file
pub fn parse_plugin_header_from_file(path: &Path) -> Result<PluginMetadata, PluginParseError> {
    let content = std::fs::read_to_string(path)
        .map_err(|e| PluginParseError::IoError(e.to_string()))?;
    parse_plugin_header(&content)
}

/// Get default plugin directories
pub fn get_default_plugin_dirs() -> Vec<PathBuf> {
    let mut dirs = Vec::new();
    
    // Current directory plugins
    dirs.push(PathBuf::from("./.praisonai/plugins/"));
    
    // Home directory plugins
    if let Some(home) = dirs::home_dir() {
        dirs.push(home.join(".praisonai/plugins/"));
    }
    
    dirs
}

/// Discover plugins in a directory
pub fn discover_plugins(dir: &Path) -> Vec<PathBuf> {
    let mut plugins = Vec::new();
    
    if !dir.exists() || !dir.is_dir() {
        return plugins;
    }
    
    if let Ok(entries) = std::fs::read_dir(dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_file() {
                // Check for Rust plugin files
                if let Some(ext) = path.extension() {
                    if ext == "rs" || ext == "so" || ext == "dylib" || ext == "dll" {
                        plugins.push(path);
                    }
                }
            }
        }
    }
    
    plugins
}

/// Discover and load plugins from default directories
pub fn discover_and_load_plugins() -> Vec<PluginMetadata> {
    let mut plugins = Vec::new();
    
    for dir in get_default_plugin_dirs() {
        for plugin_path in discover_plugins(&dir) {
            if let Ok(metadata) = parse_plugin_header_from_file(&plugin_path) {
                plugins.push(metadata);
            }
        }
    }
    
    plugins
}

/// Ensure plugin directory exists
pub fn ensure_plugin_dir(dir: &Path) -> Result<(), std::io::Error> {
    if !dir.exists() {
        std::fs::create_dir_all(dir)?;
    }
    Ok(())
}

/// Get plugin template content
pub fn get_plugin_template(plugin_type: PluginType, name: &str) -> String {
    match plugin_type {
        PluginType::Tool => format!(
            r#"//! Name: {name}
//! Version: 0.1.0
//! Description: A tool plugin
//! Type: tool

use praisonai::parity::plugins::{{PluginProtocol, ToolPluginProtocol, PluginMetadata, ToolDefinition}};

pub struct {name}Plugin {{
    metadata: PluginMetadata,
}}

impl {name}Plugin {{
    pub fn new() -> Self {{
        Self {{
            metadata: PluginMetadata {{
                name: "{name}".to_string(),
                version: "0.1.0".to_string(),
                description: "A tool plugin".to_string(),
                ..Default::default()
            }},
        }}
    }}
}}

impl PluginProtocol for {name}Plugin {{
    fn metadata(&self) -> &PluginMetadata {{
        &self.metadata
    }}
}}

impl ToolPluginProtocol for {name}Plugin {{
    fn get_tools(&self) -> Vec<ToolDefinition> {{
        vec![]
    }}
    
    fn execute_tool(&self, name: &str, args: serde_json::Value) -> Result<serde_json::Value, String> {{
        Err(format!("Unknown tool: {{}}", name))
    }}
}}
"#
        ),
        PluginType::Hook => format!(
            r#"//! Name: {name}
//! Version: 0.1.0
//! Description: A hook plugin
//! Type: hook

use praisonai::parity::plugins::{{PluginProtocol, HookPluginProtocol, PluginMetadata}};

pub struct {name}Plugin {{
    metadata: PluginMetadata,
}}

impl {name}Plugin {{
    pub fn new() -> Self {{
        Self {{
            metadata: PluginMetadata {{
                name: "{name}".to_string(),
                version: "0.1.0".to_string(),
                description: "A hook plugin".to_string(),
                ..Default::default()
            }},
        }}
    }}
}}

impl PluginProtocol for {name}Plugin {{
    fn metadata(&self) -> &PluginMetadata {{
        &self.metadata
    }}
}}

impl HookPluginProtocol for {name}Plugin {{
    // Override hook methods as needed
}}
"#
        ),
        _ => format!(
            r#"//! Name: {name}
//! Version: 0.1.0
//! Description: A generic plugin
//! Type: generic

use praisonai::parity::plugins::{{PluginProtocol, PluginMetadata}};

pub struct {name}Plugin {{
    metadata: PluginMetadata,
}}

impl {name}Plugin {{
    pub fn new() -> Self {{
        Self {{
            metadata: PluginMetadata {{
                name: "{name}".to_string(),
                version: "0.1.0".to_string(),
                description: "A generic plugin".to_string(),
                ..Default::default()
            }},
        }}
    }}
}}

impl PluginProtocol for {name}Plugin {{
    fn metadata(&self) -> &PluginMetadata {{
        &self.metadata
    }}
}}
"#
        ),
    }
}

// =============================================================================
// Plugin Registry
// =============================================================================

/// Plugin registry for managing loaded plugins
#[derive(Default)]
pub struct PluginRegistry {
    plugins: HashMap<String, PluginMetadata>,
    enabled: HashMap<String, bool>,
}

impl PluginRegistry {
    /// Create a new plugin registry
    pub fn new() -> Self {
        Self::default()
    }
    
    /// Register a plugin
    pub fn register(&mut self, metadata: PluginMetadata) {
        let name = metadata.name.clone();
        self.plugins.insert(name.clone(), metadata);
        self.enabled.insert(name, true);
    }
    
    /// Get plugin metadata by name
    pub fn get(&self, name: &str) -> Option<&PluginMetadata> {
        self.plugins.get(name)
    }
    
    /// Check if plugin is registered
    pub fn has(&self, name: &str) -> bool {
        self.plugins.contains_key(name)
    }
    
    /// Check if plugin is enabled
    pub fn is_enabled(&self, name: &str) -> bool {
        self.enabled.get(name).copied().unwrap_or(false)
    }
    
    /// Enable a plugin
    pub fn enable(&mut self, name: &str) {
        if self.plugins.contains_key(name) {
            self.enabled.insert(name.to_string(), true);
        }
    }
    
    /// Disable a plugin
    pub fn disable(&mut self, name: &str) {
        if self.plugins.contains_key(name) {
            self.enabled.insert(name.to_string(), false);
        }
    }
    
    /// List all registered plugins
    pub fn list(&self) -> Vec<&str> {
        self.plugins.keys().map(|s| s.as_str()).collect()
    }
    
    /// List enabled plugins
    pub fn list_enabled(&self) -> Vec<&str> {
        self.plugins
            .keys()
            .filter(|name| self.is_enabled(name))
            .map(|s| s.as_str())
            .collect()
    }
    
    /// Get plugin count
    pub fn len(&self) -> usize {
        self.plugins.len()
    }
    
    /// Check if registry is empty
    pub fn is_empty(&self) -> bool {
        self.plugins.is_empty()
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_plugin_header() {
        let content = r#"
//! Name: TestPlugin
//! Version: 1.0.0
//! Description: A test plugin
//! Author: Test Author
//! Type: tool

use something;
"#;
        
        let metadata = parse_plugin_header(content).unwrap();
        assert_eq!(metadata.name, "TestPlugin");
        assert_eq!(metadata.version, "1.0.0");
        assert_eq!(metadata.description, "A test plugin");
        assert_eq!(metadata.author, Some("Test Author".to_string()));
        assert_eq!(metadata.plugin_type, PluginType::Tool);
    }

    #[test]
    fn test_parse_plugin_header_missing_name() {
        let content = r#"
//! Version: 1.0.0
//! Description: A test plugin
"#;
        
        let result = parse_plugin_header(content);
        assert!(matches!(result, Err(PluginParseError::MissingField(_))));
    }

    #[test]
    fn test_plugin_registry() {
        let mut registry = PluginRegistry::new();
        
        let metadata = PluginMetadata {
            name: "TestPlugin".to_string(),
            version: "1.0.0".to_string(),
            description: "Test".to_string(),
            ..Default::default()
        };
        
        registry.register(metadata);
        
        assert!(registry.has("TestPlugin"));
        assert!(registry.is_enabled("TestPlugin"));
        assert_eq!(registry.len(), 1);
        
        registry.disable("TestPlugin");
        assert!(!registry.is_enabled("TestPlugin"));
        
        registry.enable("TestPlugin");
        assert!(registry.is_enabled("TestPlugin"));
    }

    #[test]
    fn test_get_plugin_template() {
        let template = get_plugin_template(PluginType::Tool, "MyTool");
        assert!(template.contains("MyTool"));
        assert!(template.contains("ToolPluginProtocol"));
    }

    #[test]
    fn test_default_plugin_dirs() {
        let dirs = get_default_plugin_dirs();
        assert!(!dirs.is_empty());
        assert!(dirs[0].to_string_lossy().contains(".praisonai/plugins"));
    }
}
