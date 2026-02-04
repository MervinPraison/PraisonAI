//! Agent module for PraisonAI
//!
//! This module provides the core Agent struct and builder pattern.
//! Agents are the primary execution unit in PraisonAI.
//!
//! # Example
//!
//! ```rust,ignore
//! use praisonai_core::Agent;
//!
//! let agent = Agent::new()
//!     .name("assistant")
//!     .instructions("You are a helpful assistant")
//!     .build();
//!
//! let response = agent.chat("Hello!").await?;
//! ```

mod builder;

pub use builder::{AgentBuilder, AgentConfig};

use std::sync::Arc;
use tokio::sync::RwLock;
use uuid::Uuid;

use crate::error::{Error, Result};
use crate::llm::{LlmProvider, Message};
use crate::memory::Memory;
use crate::tools::{Tool, ToolRegistry, ToolResult};

/// The core Agent struct
///
/// Agents are the primary execution unit in PraisonAI. They combine:
/// - LLM provider for generating responses
/// - Tools for performing actions
/// - Memory for conversation history
/// - Instructions for behavior
pub struct Agent {
    /// Unique agent ID
    id: String,
    /// Agent name
    name: String,
    /// System instructions
    instructions: String,
    /// LLM provider
    llm: Arc<dyn LlmProvider>,
    /// Tool registry
    tools: Arc<RwLock<ToolRegistry>>,
    /// Memory
    memory: Arc<RwLock<Memory>>,
    /// Configuration
    config: AgentConfig,
}

impl Agent {
    /// Create a new agent builder
    #[allow(clippy::new_ret_no_self)]
    pub fn new() -> AgentBuilder {
        AgentBuilder::new()
    }
    
    /// Create an agent with minimal config
    pub fn simple(instructions: impl Into<String>) -> Result<Self> {
        AgentBuilder::new()
            .instructions(instructions)
            .build()
    }
    
    /// Get the agent ID
    pub fn id(&self) -> &str {
        &self.id
    }
    
    /// Get the agent name
    pub fn name(&self) -> &str {
        &self.name
    }
    
    /// Get the instructions
    pub fn instructions(&self) -> &str {
        &self.instructions
    }
    
    /// Get the LLM model name
    pub fn model(&self) -> &str {
        self.llm.model()
    }
    
    /// Chat with the agent (main entry point)
    ///
    /// This is the primary method for interacting with an agent.
    /// It handles the full conversation loop including tool calls.
    pub async fn chat(&self, prompt: &str) -> Result<String> {
        // Build messages
        let mut messages = vec![Message::system(&self.instructions)];
        
        // Add conversation history
        {
            let memory = self.memory.read().await;
            let history = memory.history().await?;
            messages.extend(history);
        }
        
        // Add user message
        let user_msg = Message::user(prompt);
        messages.push(user_msg.clone());
        
        // Store user message in memory
        {
            let mut memory = self.memory.write().await;
            memory.store(user_msg).await?;
        }
        
        // Get tool definitions
        let tool_defs = {
            let tools = self.tools.read().await;
            if tools.is_empty() {
                None
            } else {
                Some(tools.definitions())
            }
        };
        
        // Call LLM
        let mut iterations = 0;
        let max_iterations = self.config.max_iterations;
        
        loop {
            iterations += 1;
            if iterations > max_iterations {
                return Err(Error::agent(format!(
                    "Max iterations ({}) exceeded", max_iterations
                )));
            }
            
            let response = self.llm.chat(
                &messages,
                tool_defs.as_deref(),
            ).await?;
            
            // If no tool calls, return the response
            if response.tool_calls.is_empty() {
                let assistant_msg = Message::assistant(&response.content);
                
                // Store assistant message
                {
                    let mut memory = self.memory.write().await;
                    memory.store(assistant_msg).await?;
                }
                
                return Ok(response.content);
            }
            
            // Handle tool calls
            let mut assistant_msg = Message::assistant(&response.content);
            assistant_msg.tool_calls = Some(response.tool_calls.clone());
            messages.push(assistant_msg);
            
            for tool_call in &response.tool_calls {
                let args: serde_json::Value = serde_json::from_str(&tool_call.arguments)
                    .unwrap_or(serde_json::Value::Object(serde_json::Map::new()));
                
                let result = {
                    let tools = self.tools.read().await;
                    tools.execute(&tool_call.name, args).await
                };
                
                let tool_result = match result {
                    Ok(r) => r,
                    Err(e) => ToolResult::failure(&tool_call.name, e.to_string()),
                };
                
                let result_str = if tool_result.success {
                    serde_json::to_string(&tool_result.value).unwrap_or_default()
                } else {
                    format!("Error: {}", tool_result.error.unwrap_or_default())
                };
                
                messages.push(Message::tool(&tool_call.id, result_str));
            }
        }
    }
    
    /// Start a conversation (alias for chat)
    pub async fn start(&self, prompt: &str) -> Result<String> {
        self.chat(prompt).await
    }
    
    /// Run a task (alias for chat)
    pub async fn run(&self, task: &str) -> Result<String> {
        self.chat(task).await
    }
    
    /// Add a tool to the agent
    pub async fn add_tool(&self, tool: impl Tool + 'static) {
        let mut tools = self.tools.write().await;
        tools.register(tool);
    }
    
    /// Get the number of tools
    pub async fn tool_count(&self) -> usize {
        let tools = self.tools.read().await;
        tools.len()
    }
    
    /// Clear conversation memory
    pub async fn clear_memory(&self) -> Result<()> {
        let mut memory = self.memory.write().await;
        memory.clear().await
    }
    
    /// Get conversation history
    pub async fn history(&self) -> Result<Vec<Message>> {
        let memory = self.memory.read().await;
        memory.history().await
    }
}

impl Default for Agent {
    fn default() -> Self {
        AgentBuilder::new().build().expect("Default agent should build")
    }
}

impl std::fmt::Debug for Agent {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Agent")
            .field("id", &self.id)
            .field("name", &self.name)
            .field("model", &self.llm.model())
            .finish()
    }
}

// Internal constructor used by builder
impl Agent {
    pub(crate) fn from_builder(
        name: String,
        instructions: String,
        llm: Arc<dyn LlmProvider>,
        tools: ToolRegistry,
        memory: Memory,
        config: AgentConfig,
    ) -> Self {
        Self {
            id: Uuid::new_v4().to_string(),
            name,
            instructions,
            llm,
            tools: Arc::new(RwLock::new(tools)),
            memory: Arc::new(RwLock::new(memory)),
            config,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_agent_builder() {
        let agent = Agent::new()
            .name("test")
            .instructions("Be helpful")
            .build()
            .unwrap();
        
        assert_eq!(agent.name(), "test");
        assert_eq!(agent.instructions(), "Be helpful");
    }
    
    #[test]
    fn test_default_agent() {
        let agent = Agent::default();
        assert!(!agent.id().is_empty());
    }
}
