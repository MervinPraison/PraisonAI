//! LLM Provider abstraction for PraisonAI
//!
//! This module provides the LLM provider trait and implementations.
//! Uses rig-core for multi-provider support (OpenAI, Anthropic, Ollama, etc.)

use async_trait::async_trait;
use serde::{Deserialize, Serialize};

use crate::error::Result;
use crate::tools::ToolDefinition;

/// Message role in a conversation
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Role {
    /// System message (instructions)
    System,
    /// User message
    User,
    /// Assistant message
    Assistant,
    /// Tool/function result
    Tool,
}

impl std::fmt::Display for Role {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Role::System => write!(f, "system"),
            Role::User => write!(f, "user"),
            Role::Assistant => write!(f, "assistant"),
            Role::Tool => write!(f, "tool"),
        }
    }
}

/// A message in a conversation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Message {
    /// The role of the message sender
    pub role: Role,
    /// The content of the message
    pub content: String,
    /// Tool call ID (for tool responses)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_call_id: Option<String>,
    /// Tool calls made by the assistant
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_calls: Option<Vec<ToolCall>>,
}

impl Message {
    /// Create a system message
    pub fn system(content: impl Into<String>) -> Self {
        Self {
            role: Role::System,
            content: content.into(),
            tool_call_id: None,
            tool_calls: None,
        }
    }

    /// Create a user message
    pub fn user(content: impl Into<String>) -> Self {
        Self {
            role: Role::User,
            content: content.into(),
            tool_call_id: None,
            tool_calls: None,
        }
    }

    /// Create an assistant message
    pub fn assistant(content: impl Into<String>) -> Self {
        Self {
            role: Role::Assistant,
            content: content.into(),
            tool_call_id: None,
            tool_calls: None,
        }
    }

    /// Create a tool response message
    pub fn tool(tool_call_id: impl Into<String>, content: impl Into<String>) -> Self {
        Self {
            role: Role::Tool,
            content: content.into(),
            tool_call_id: Some(tool_call_id.into()),
            tool_calls: None,
        }
    }
}

/// Function details within a tool call
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCallFunction {
    /// The tool/function name
    pub name: String,
    /// The arguments as JSON string
    pub arguments: String,
}

/// A tool call made by the LLM
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCall {
    /// Unique ID for this tool call
    pub id: String,
    /// The type of tool call (always "function" for now)
    #[serde(rename = "type")]
    pub call_type: String,
    /// The function details
    pub function: ToolCallFunction,
}

impl ToolCall {
    /// Create a new tool call
    pub fn new(id: impl Into<String>, name: impl Into<String>, arguments: impl Into<String>) -> Self {
        Self {
            id: id.into(),
            call_type: "function".to_string(),
            function: ToolCallFunction {
                name: name.into(),
                arguments: arguments.into(),
            },
        }
    }

    /// Get the function name (convenience method)
    pub fn name(&self) -> &str {
        &self.function.name
    }

    /// Get the function arguments (convenience method)
    pub fn arguments(&self) -> &str {
        &self.function.arguments
    }
}

/// LLM response
#[derive(Debug, Clone)]
pub struct LlmResponse {
    /// The response content
    pub content: String,
    /// Tool calls (if any)
    pub tool_calls: Vec<ToolCall>,
    /// Finish reason
    pub finish_reason: Option<String>,
    /// Usage statistics
    pub usage: Option<Usage>,
}

/// Token usage statistics
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Usage {
    /// Prompt tokens
    pub prompt_tokens: u32,
    /// Completion tokens
    pub completion_tokens: u32,
    /// Total tokens
    pub total_tokens: u32,
}

/// LLM configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LlmConfig {
    /// Model name (e.g., "gpt-4o-mini", "claude-3-sonnet")
    pub model: String,
    /// API key (optional, can use env var)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub api_key: Option<String>,
    /// Base URL (optional, for custom endpoints)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub base_url: Option<String>,
    /// Temperature (0.0 - 2.0)
    #[serde(default = "default_temperature")]
    pub temperature: f32,
    /// Max tokens
    #[serde(skip_serializing_if = "Option::is_none")]
    pub max_tokens: Option<u32>,
}

fn default_temperature() -> f32 {
    0.7
}

impl Default for LlmConfig {
    fn default() -> Self {
        Self {
            model: "gpt-4o-mini".to_string(),
            api_key: None,
            base_url: None,
            temperature: default_temperature(),
            max_tokens: None,
        }
    }
}

impl LlmConfig {
    /// Create a new LLM config with the given model
    pub fn new(model: impl Into<String>) -> Self {
        Self {
            model: model.into(),
            ..Default::default()
        }
    }

    /// Set the API key
    pub fn api_key(mut self, key: impl Into<String>) -> Self {
        self.api_key = Some(key.into());
        self
    }

    /// Set the base URL
    pub fn base_url(mut self, url: impl Into<String>) -> Self {
        self.base_url = Some(url.into());
        self
    }

    /// Set the temperature
    pub fn temperature(mut self, temp: f32) -> Self {
        self.temperature = temp;
        self
    }

    /// Set max tokens
    pub fn max_tokens(mut self, max: u32) -> Self {
        self.max_tokens = Some(max);
        self
    }
}

/// Trait for LLM providers
#[async_trait]
pub trait LlmProvider: Send + Sync {
    /// Send a chat completion request
    async fn chat(
        &self,
        messages: &[Message],
        tools: Option<&[ToolDefinition]>,
    ) -> Result<LlmResponse>;

    /// Stream a chat completion (returns chunks)
    async fn chat_stream(
        &self,
        messages: &[Message],
        tools: Option<&[ToolDefinition]>,
    ) -> Result<Box<dyn futures::Stream<Item = Result<String>> + Send + Unpin>>;

    /// Get the model name
    fn model(&self) -> &str;
}

/// OpenAI-compatible LLM provider
pub struct OpenAiProvider {
    config: LlmConfig,
    client: reqwest::Client,
}

impl OpenAiProvider {
    /// Create a new OpenAI provider
    pub fn new(config: LlmConfig) -> Self {
        Self {
            config,
            client: reqwest::Client::new(),
        }
    }

    /// Create with default config
    pub fn default_model() -> Self {
        Self::new(LlmConfig::default())
    }
}

#[async_trait]
impl LlmProvider for OpenAiProvider {
    async fn chat(
        &self,
        messages: &[Message],
        tools: Option<&[ToolDefinition]>,
    ) -> Result<LlmResponse> {
        let api_key = self
            .config
            .api_key
            .clone()
            .or_else(|| std::env::var("OPENAI_API_KEY").ok())
            .ok_or_else(|| crate::error::Error::llm("OPENAI_API_KEY not set"))?;

        let base_url = self
            .config
            .base_url
            .as_deref()
            .unwrap_or("https://api.openai.com/v1");

        let mut body = serde_json::json!({
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
        });

        if let Some(max_tokens) = self.config.max_tokens {
            body["max_tokens"] = serde_json::json!(max_tokens);
        }

        if let Some(tools) = tools {
            if !tools.is_empty() {
                let tool_defs: Vec<_> = tools
                    .iter()
                    .map(|t| {
                        serde_json::json!({
                            "type": "function",
                            "function": {
                                "name": t.name,
                                "description": t.description,
                                "parameters": t.parameters,
                            }
                        })
                    })
                    .collect();
                body["tools"] = serde_json::json!(tool_defs);
            }
        }

        let response = self
            .client
            .post(format!("{}/chat/completions", base_url))
            .header("Authorization", format!("Bearer {}", api_key))
            .header("Content-Type", "application/json")
            .json(&body)
            .send()
            .await?;

        if !response.status().is_success() {
            let error_text = response.text().await.unwrap_or_default();
            return Err(crate::error::Error::llm(format!(
                "API error: {}",
                error_text
            )));
        }

        let data: serde_json::Value = response.json().await?;

        let choice = data["choices"]
            .get(0)
            .ok_or_else(|| crate::error::Error::llm("No choices in response"))?;

        let message = &choice["message"];
        let content = message["content"].as_str().unwrap_or("").to_string();

        let tool_calls = if let Some(calls) = message["tool_calls"].as_array() {
            calls
                .iter()
                .filter_map(|call| {
                    Some(ToolCall::new(
                        call["id"].as_str()?.to_string(),
                        call["function"]["name"].as_str()?.to_string(),
                        call["function"]["arguments"].as_str()?.to_string(),
                    ))
                })
                .collect()
        } else {
            vec![]
        };

        let usage = data["usage"].as_object().map(|u| Usage {
            prompt_tokens: u["prompt_tokens"].as_u64().unwrap_or(0) as u32,
            completion_tokens: u["completion_tokens"].as_u64().unwrap_or(0) as u32,
            total_tokens: u["total_tokens"].as_u64().unwrap_or(0) as u32,
        });

        Ok(LlmResponse {
            content,
            tool_calls,
            finish_reason: choice["finish_reason"].as_str().map(|s| s.to_string()),
            usage,
        })
    }

    async fn chat_stream(
        &self,
        _messages: &[Message],
        _tools: Option<&[ToolDefinition]>,
    ) -> Result<Box<dyn futures::Stream<Item = Result<String>> + Send + Unpin>> {
        // TODO: Implement streaming
        Err(crate::error::Error::llm("Streaming not yet implemented"))
    }

    fn model(&self) -> &str {
        &self.config.model
    }
}

/// Mock LLM provider for testing (no API calls)
pub struct MockLlmProvider {
    model: String,
    responses: std::sync::Mutex<Vec<String>>,
    tool_calls: std::sync::Mutex<Vec<Vec<ToolCall>>>,
}

impl MockLlmProvider {
    /// Create a new mock provider
    pub fn new() -> Self {
        Self {
            model: "mock-model".to_string(),
            responses: std::sync::Mutex::new(vec![]),
            tool_calls: std::sync::Mutex::new(vec![]),
        }
    }

    /// Add a response to return (FIFO queue)
    pub fn add_response(&self, response: impl Into<String>) {
        self.responses.lock().unwrap().push(response.into());
    }

    /// Add tool calls to return with next response
    pub fn add_tool_calls(&self, calls: Vec<ToolCall>) {
        self.tool_calls.lock().unwrap().push(calls);
    }

    /// Create with a single response
    pub fn with_response(response: impl Into<String>) -> Self {
        let provider = Self::new();
        provider.add_response(response);
        provider
    }
}

impl Default for MockLlmProvider {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl LlmProvider for MockLlmProvider {
    async fn chat(
        &self,
        _messages: &[Message],
        _tools: Option<&[ToolDefinition]>,
    ) -> Result<LlmResponse> {
        let content = self
            .responses
            .lock()
            .unwrap()
            .pop()
            .unwrap_or_else(|| "Mock response".to_string());

        let tool_calls = self.tool_calls.lock().unwrap().pop().unwrap_or_default();

        Ok(LlmResponse {
            content,
            tool_calls,
            finish_reason: Some("stop".to_string()),
            usage: Some(Usage {
                prompt_tokens: 10,
                completion_tokens: 20,
                total_tokens: 30,
            }),
        })
    }

    async fn chat_stream(
        &self,
        _messages: &[Message],
        _tools: Option<&[ToolDefinition]>,
    ) -> Result<Box<dyn futures::Stream<Item = Result<String>> + Send + Unpin>> {
        Err(crate::error::Error::llm("Streaming not supported in mock"))
    }

    fn model(&self) -> &str {
        &self.model
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_message_creation() {
        let msg = Message::user("Hello");
        assert_eq!(msg.role, Role::User);
        assert_eq!(msg.content, "Hello");
    }

    #[test]
    fn test_llm_config() {
        let config = LlmConfig::new("gpt-4").temperature(0.5).max_tokens(1000);

        assert_eq!(config.model, "gpt-4");
        assert_eq!(config.temperature, 0.5);
        assert_eq!(config.max_tokens, Some(1000));
    }

    #[tokio::test]
    async fn test_mock_provider() {
        let provider = MockLlmProvider::with_response("Hello from mock!");

        let response = provider.chat(&[Message::user("Hi")], None).await.unwrap();
        assert_eq!(response.content, "Hello from mock!");
        assert!(response.tool_calls.is_empty());
    }

    #[tokio::test]
    async fn test_mock_provider_with_tool_calls() {
        let provider = MockLlmProvider::new();
        provider.add_response("I'll search for that");
        provider.add_tool_calls(vec![ToolCall::new(
            "call_1",
            "search",
            r#"{"query": "rust"}"#,
        )]);

        let response = provider
            .chat(&[Message::user("Search for rust")], None)
            .await
            .unwrap();
        assert_eq!(response.tool_calls.len(), 1);
        assert_eq!(response.tool_calls[0].name(), "search");
    }
}
