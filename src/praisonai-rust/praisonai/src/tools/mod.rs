//! Tool system for PraisonAI
//!
//! This module provides the tool abstraction for agents.
//! Tools are functions that agents can call to perform actions.
//!
//! # Example
//!
//! ```rust,ignore
//! use praisonai_core::{tool, Tool};
//!
//! #[tool(description = "Search the web")]
//! async fn search(query: String) -> String {
//!     format!("Results for: {}", query)
//! }
//! ```

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::sync::Arc;

use crate::error::{Error, Result};

/// Result of a tool execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolResult {
    /// The tool name
    pub name: String,
    /// The result value (JSON)
    pub value: Value,
    /// Whether the execution was successful
    pub success: bool,
    /// Error message if failed
    pub error: Option<String>,
}

impl ToolResult {
    /// Create a successful result
    pub fn success(name: impl Into<String>, value: Value) -> Self {
        Self {
            name: name.into(),
            value,
            success: true,
            error: None,
        }
    }

    /// Create a failed result
    pub fn failure(name: impl Into<String>, error: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            value: Value::Null,
            success: false,
            error: Some(error.into()),
        }
    }
}

/// Trait for tools that can be used by agents
///
/// This trait defines the interface for tools. Tools can be created
/// using the `#[tool]` macro or by implementing this trait directly.
#[async_trait]
pub trait Tool: Send + Sync {
    /// Get the tool name
    fn name(&self) -> &str;

    /// Get the tool description
    fn description(&self) -> &str;

    /// Get the parameter schema as JSON Schema
    fn parameters_schema(&self) -> Value;

    /// Execute the tool with the given arguments
    async fn execute(&self, args: Value) -> Result<Value>;

    /// Get the tool definition for LLM function calling
    fn definition(&self) -> ToolDefinition {
        ToolDefinition {
            name: self.name().to_string(),
            description: self.description().to_string(),
            parameters: self.parameters_schema(),
        }
    }
}

/// Tool definition for LLM function calling
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolDefinition {
    /// Tool name
    pub name: String,
    /// Tool description
    pub description: String,
    /// Parameter schema (JSON Schema)
    pub parameters: Value,
}

/// Registry for managing tools
#[derive(Default)]
pub struct ToolRegistry {
    tools: HashMap<String, Arc<dyn Tool>>,
}

impl ToolRegistry {
    /// Create a new empty registry
    pub fn new() -> Self {
        Self::default()
    }

    /// Register a tool
    pub fn register(&mut self, tool: impl Tool + 'static) {
        let name = tool.name().to_string();
        self.tools.insert(name, Arc::new(tool));
    }

    /// Get a tool by name
    pub fn get(&self, name: &str) -> Option<Arc<dyn Tool>> {
        self.tools.get(name).cloned()
    }

    /// Check if a tool exists
    pub fn has(&self, name: &str) -> bool {
        self.tools.contains_key(name)
    }

    /// List all tool names
    pub fn list(&self) -> Vec<&str> {
        self.tools.keys().map(|s| s.as_str()).collect()
    }

    /// Get all tool definitions
    pub fn definitions(&self) -> Vec<ToolDefinition> {
        self.tools.values().map(|t| t.definition()).collect()
    }

    /// Execute a tool by name
    pub async fn execute(&self, name: &str, args: Value) -> Result<ToolResult> {
        match self.get(name) {
            Some(tool) => match tool.execute(args).await {
                Ok(value) => Ok(ToolResult::success(name, value)),
                Err(e) => Ok(ToolResult::failure(name, e.to_string())),
            },
            None => Err(Error::tool(format!("Tool not found: {}", name))),
        }
    }

    /// Get the number of registered tools
    pub fn len(&self) -> usize {
        self.tools.len()
    }

    /// Check if the registry is empty
    pub fn is_empty(&self) -> bool {
        self.tools.is_empty()
    }
}

impl std::fmt::Debug for ToolRegistry {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("ToolRegistry")
            .field("tools", &self.list())
            .finish()
    }
}

/// A simple function-based tool
pub struct FunctionTool<F, Fut>
where
    F: Fn(Value) -> Fut + Send + Sync,
    Fut: std::future::Future<Output = Result<Value>> + Send,
{
    name: String,
    description: String,
    parameters: Value,
    func: F,
}

impl<F, Fut> FunctionTool<F, Fut>
where
    F: Fn(Value) -> Fut + Send + Sync,
    Fut: std::future::Future<Output = Result<Value>> + Send,
{
    /// Create a new function tool
    pub fn new(
        name: impl Into<String>,
        description: impl Into<String>,
        parameters: Value,
        func: F,
    ) -> Self {
        Self {
            name: name.into(),
            description: description.into(),
            parameters,
            func,
        }
    }
}

#[async_trait]
impl<F, Fut> Tool for FunctionTool<F, Fut>
where
    F: Fn(Value) -> Fut + Send + Sync,
    Fut: std::future::Future<Output = Result<Value>> + Send,
{
    fn name(&self) -> &str {
        &self.name
    }

    fn description(&self) -> &str {
        &self.description
    }

    fn parameters_schema(&self) -> Value {
        self.parameters.clone()
    }

    async fn execute(&self, args: Value) -> Result<Value> {
        (self.func)(args).await
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tool_result_success() {
        let result = ToolResult::success("test", serde_json::json!("hello"));
        assert!(result.success);
        assert_eq!(result.name, "test");
        assert!(result.error.is_none());
    }

    #[test]
    fn test_tool_result_failure() {
        let result = ToolResult::failure("test", "something went wrong");
        assert!(!result.success);
        assert_eq!(result.error, Some("something went wrong".to_string()));
    }

    #[test]
    fn test_tool_registry() {
        let registry = ToolRegistry::new();
        assert!(registry.is_empty());
        assert_eq!(registry.len(), 0);
    }
}
