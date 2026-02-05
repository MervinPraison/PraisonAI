//! Agent builder pattern implementation
//!
//! Provides a fluent API for constructing agents.

use std::sync::Arc;

use crate::config::MemoryConfig;
use crate::error::Result;
use crate::llm::{LlmConfig, LlmProvider, OpenAiProvider};
use crate::memory::Memory;
use crate::tools::{Tool, ToolRegistry};

use super::Agent;

/// Configuration for an agent
#[derive(Debug, Clone)]
pub struct AgentConfig {
    /// Maximum iterations for tool calling loop
    pub max_iterations: usize,
    /// Enable verbose output
    pub verbose: bool,
    /// Enable streaming
    pub stream: bool,
}

impl Default for AgentConfig {
    fn default() -> Self {
        Self {
            max_iterations: 10,
            verbose: false,
            stream: true,
        }
    }
}

/// Builder for creating agents
///
/// # Example
///
/// ```rust,ignore
/// let agent = Agent::new()
///     .name("assistant")
///     .instructions("You are helpful")
///     .model("gpt-4o-mini")
///     .build()?;
/// ```
pub struct AgentBuilder {
    name: Option<String>,
    instructions: Option<String>,
    llm_config: LlmConfig,
    tools: Vec<Box<dyn Tool>>,
    memory_config: MemoryConfig,
    config: AgentConfig,
}

impl AgentBuilder {
    /// Create a new agent builder
    pub fn new() -> Self {
        Self {
            name: None,
            instructions: None,
            llm_config: LlmConfig::default(),
            tools: Vec::new(),
            memory_config: MemoryConfig::default(),
            config: AgentConfig::default(),
        }
    }

    /// Set the agent name
    pub fn name(mut self, name: impl Into<String>) -> Self {
        self.name = Some(name.into());
        self
    }

    /// Set the system instructions
    pub fn instructions(mut self, instructions: impl Into<String>) -> Self {
        self.instructions = Some(instructions.into());
        self
    }

    /// Set the LLM model
    pub fn model(mut self, model: impl Into<String>) -> Self {
        self.llm_config.model = model.into();
        self
    }

    /// Alias for model() - matches Python SDK
    pub fn llm(self, model: impl Into<String>) -> Self {
        self.model(model)
    }

    /// Set the API key
    pub fn api_key(mut self, key: impl Into<String>) -> Self {
        self.llm_config.api_key = Some(key.into());
        self
    }

    /// Set the base URL for the LLM API
    pub fn base_url(mut self, url: impl Into<String>) -> Self {
        self.llm_config.base_url = Some(url.into());
        self
    }

    /// Set the temperature
    pub fn temperature(mut self, temp: f32) -> Self {
        self.llm_config.temperature = temp;
        self
    }

    /// Set max tokens
    pub fn max_tokens(mut self, max: u32) -> Self {
        self.llm_config.max_tokens = Some(max);
        self
    }

    /// Add a tool
    pub fn tool(mut self, tool: impl Tool + 'static) -> Self {
        self.tools.push(Box::new(tool));
        self
    }

    /// Add multiple tools
    pub fn tools(mut self, tools: impl IntoIterator<Item = impl Tool + 'static>) -> Self {
        for tool in tools {
            self.tools.push(Box::new(tool));
        }
        self
    }

    /// Enable memory
    pub fn memory(mut self, enabled: bool) -> Self {
        self.memory_config.use_short_term = enabled;
        self
    }

    /// Set memory configuration
    pub fn memory_config(mut self, config: MemoryConfig) -> Self {
        self.memory_config = config;
        self
    }

    /// Set max iterations for tool calling
    pub fn max_iterations(mut self, max: usize) -> Self {
        self.config.max_iterations = max;
        self
    }

    /// Enable verbose output
    pub fn verbose(mut self, enabled: bool) -> Self {
        self.config.verbose = enabled;
        self
    }

    /// Enable/disable streaming
    pub fn stream(mut self, enabled: bool) -> Self {
        self.config.stream = enabled;
        self
    }

    /// Build the agent
    pub fn build(self) -> Result<Agent> {
        let name = self.name.unwrap_or_else(|| "agent".to_string());
        let instructions = self
            .instructions
            .unwrap_or_else(|| "You are a helpful AI assistant.".to_string());

        // Create LLM provider
        let llm: Arc<dyn LlmProvider> = Arc::new(OpenAiProvider::new(self.llm_config));

        // Create tool registry
        let mut tool_registry = ToolRegistry::new();
        for tool in self.tools {
            // We need to register the boxed tool
            // This is a bit awkward but necessary for the builder pattern
            tool_registry.register(BoxedTool(tool));
        }

        // Create memory
        let memory = Memory::in_memory(self.memory_config);

        Ok(Agent::from_builder(
            name,
            instructions,
            llm,
            tool_registry,
            memory,
            self.config,
        ))
    }
}

impl Default for AgentBuilder {
    fn default() -> Self {
        Self::new()
    }
}

/// Wrapper to make Box<dyn Tool> implement Tool
struct BoxedTool(Box<dyn Tool>);

#[async_trait::async_trait]
impl crate::tools::Tool for BoxedTool {
    fn name(&self) -> &str {
        self.0.name()
    }

    fn description(&self) -> &str {
        self.0.description()
    }

    fn parameters_schema(&self) -> serde_json::Value {
        self.0.parameters_schema()
    }

    async fn execute(&self, args: serde_json::Value) -> Result<serde_json::Value> {
        self.0.execute(args).await
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_builder_defaults() {
        let builder = AgentBuilder::new();
        let agent = builder.build().unwrap();

        assert_eq!(agent.name(), "agent");
        assert!(agent.instructions().contains("helpful"));
    }

    #[test]
    fn test_builder_chain() {
        let agent = AgentBuilder::new()
            .name("test-agent")
            .instructions("Be concise")
            .model("gpt-4")
            .temperature(0.5)
            .max_iterations(5)
            .verbose(true)
            .build()
            .unwrap();

        assert_eq!(agent.name(), "test-agent");
        assert_eq!(agent.instructions(), "Be concise");
        assert_eq!(agent.model(), "gpt-4");
    }
}
