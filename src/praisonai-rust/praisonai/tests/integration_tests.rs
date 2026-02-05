//! Integration tests for PraisonAI Rust SDK
//!
//! These tests verify end-to-end functionality using MockLlmProvider
//! to avoid API calls during testing.

use async_trait::async_trait;
use praisonai::{
    Agent, AgentBuilder, AgentTeam, Error, LlmProvider, Memory, MemoryConfig, Message,
    MockLlmProvider, Process, Result, Role, Tool, ToolCall, ToolRegistry, ToolResult,
};
use serde_json::{json, Value};
use std::sync::Arc;

// ============================================================================
// Test Tools
// ============================================================================

/// A simple search tool for testing
struct SearchTool;

#[async_trait]
impl Tool for SearchTool {
    fn name(&self) -> &str {
        "search"
    }

    fn description(&self) -> &str {
        "Search the web for information"
    }

    fn parameters_schema(&self) -> Value {
        json!({
            "type": "object",
            "properties": {
                "query": {"type": "string"}
            },
            "required": ["query"]
        })
    }

    async fn execute(&self, args: Value) -> Result<Value> {
        let query = args["query"].as_str().unwrap_or("unknown");
        Ok(json!({
            "results": [
                {"title": "Result 1", "snippet": format!("Info about {}", query)},
                {"title": "Result 2", "snippet": format!("More about {}", query)}
            ]
        }))
    }
}

/// A calculator tool for testing
struct CalculatorTool;

#[async_trait]
impl Tool for CalculatorTool {
    fn name(&self) -> &str {
        "calculator"
    }

    fn description(&self) -> &str {
        "Perform mathematical calculations"
    }

    fn parameters_schema(&self) -> Value {
        json!({
            "type": "object",
            "properties": {
                "expression": {"type": "string"}
            },
            "required": ["expression"]
        })
    }

    async fn execute(&self, args: Value) -> Result<Value> {
        let expr = args["expression"].as_str().unwrap_or("0");
        // Simple mock - just return the expression
        Ok(json!({"result": format!("Calculated: {}", expr)}))
    }
}

// ============================================================================
// Tool Registry Tests
// ============================================================================

#[tokio::test]
async fn test_tool_registry_register_and_execute() {
    let mut registry = ToolRegistry::new();
    registry.register(SearchTool);
    registry.register(CalculatorTool);

    assert_eq!(registry.len(), 2);
    assert!(registry.has("search"));
    assert!(registry.has("calculator"));
    assert!(!registry.has("unknown"));

    // Execute search tool
    let result = registry
        .execute("search", json!({"query": "rust programming"}))
        .await
        .unwrap();
    assert!(result.success);
    assert_eq!(result.name, "search");

    // Execute calculator tool
    let result = registry
        .execute("calculator", json!({"expression": "2 + 2"}))
        .await
        .unwrap();
    assert!(result.success);
}

#[tokio::test]
async fn test_tool_registry_execute_unknown_tool() {
    let registry = ToolRegistry::new();
    let result = registry.execute("unknown", json!({})).await;
    assert!(result.is_err());
}

#[tokio::test]
async fn test_tool_definitions() {
    let mut registry = ToolRegistry::new();
    registry.register(SearchTool);

    let definitions = registry.definitions();
    assert_eq!(definitions.len(), 1);
    assert_eq!(definitions[0].name, "search");
    assert_eq!(definitions[0].description, "Search the web for information");
}

// ============================================================================
// MockLlmProvider Tests
// ============================================================================

#[tokio::test]
async fn test_mock_provider_basic() {
    let provider = MockLlmProvider::with_response("Hello, I'm an AI assistant!");

    let messages = vec![Message::user("Hello")];
    let response = provider.chat(&messages, None).await.unwrap();

    assert_eq!(response.content, "Hello, I'm an AI assistant!");
    assert!(response.tool_calls.is_empty());
    assert!(response.usage.is_some());
}

#[tokio::test]
async fn test_mock_provider_multiple_responses() {
    let provider = MockLlmProvider::new();
    provider.add_response("First response");
    provider.add_response("Second response");

    let messages = vec![Message::user("Hi")];

    // Responses are LIFO (stack)
    let r1 = provider.chat(&messages, None).await.unwrap();
    assert_eq!(r1.content, "Second response");

    let r2 = provider.chat(&messages, None).await.unwrap();
    assert_eq!(r2.content, "First response");

    // Default response when empty
    let r3 = provider.chat(&messages, None).await.unwrap();
    assert_eq!(r3.content, "Mock response");
}

#[tokio::test]
async fn test_mock_provider_with_tool_calls() {
    let provider = MockLlmProvider::new();
    provider.add_response("I'll search for that");
    provider.add_tool_calls(vec![ToolCall::new(
        "call_123",
        "search",
        r#"{"query": "rust async"}"#,
    )]);

    let messages = vec![Message::user("Search for rust async")];
    let response = provider.chat(&messages, None).await.unwrap();

    assert_eq!(response.tool_calls.len(), 1);
    assert_eq!(response.tool_calls[0].name(), "search");
    assert_eq!(response.tool_calls[0].id, "call_123");
}

// ============================================================================
// Memory Tests
// ============================================================================

#[tokio::test]
async fn test_memory_store_and_retrieve() {
    let mut memory = Memory::default_memory();

    memory.store(Message::user("Hello")).await.unwrap();
    memory.store(Message::assistant("Hi there!")).await.unwrap();

    let history = memory.history().await.unwrap();
    assert_eq!(history.len(), 2);
    assert_eq!(history[0].role, Role::User);
    assert_eq!(history[1].role, Role::Assistant);
}

#[tokio::test]
async fn test_memory_search() {
    let mut memory = Memory::default_memory();

    memory
        .store(Message::user("Tell me about Rust"))
        .await
        .unwrap();
    memory
        .store(Message::assistant("Rust is a systems programming language"))
        .await
        .unwrap();
    memory
        .store(Message::user("What about Python?"))
        .await
        .unwrap();

    let results = memory.search("Rust", 10).await.unwrap();
    assert_eq!(results.len(), 2); // Both messages contain "Rust"
}

#[tokio::test]
async fn test_memory_clear() {
    let mut memory = Memory::default_memory();

    memory.store(Message::user("Hello")).await.unwrap();
    memory.store(Message::assistant("Hi!")).await.unwrap();

    let history = memory.history().await.unwrap();
    assert_eq!(history.len(), 2);

    memory.clear().await.unwrap();

    let history = memory.history().await.unwrap();
    assert!(history.is_empty());
}

// ============================================================================
// Message Tests
// ============================================================================

#[test]
fn test_message_creation() {
    let system = Message::system("You are helpful");
    assert_eq!(system.role, Role::System);
    assert_eq!(system.content, "You are helpful");

    let user = Message::user("Hello");
    assert_eq!(user.role, Role::User);

    let assistant = Message::assistant("Hi there!");
    assert_eq!(assistant.role, Role::Assistant);

    let tool = Message::tool("call_123", "Result data");
    assert_eq!(tool.role, Role::Tool);
    assert_eq!(tool.tool_call_id, Some("call_123".to_string()));
}

// ============================================================================
// Error Handling Tests
// ============================================================================

#[test]
fn test_error_types() {
    let agent_err = Error::agent("Agent failed");
    assert!(agent_err.to_string().contains("Agent"));

    let tool_err = Error::tool("Tool failed");
    assert!(tool_err.to_string().contains("Tool"));

    let llm_err = Error::llm("LLM failed");
    assert!(llm_err.to_string().contains("LLM"));
}

// ============================================================================
// Config Tests
// ============================================================================

#[test]
fn test_memory_config() {
    let config = MemoryConfig::default();
    assert!(config.use_short_term);
    assert!(!config.use_long_term);
    assert_eq!(config.max_messages, 100);

    let custom = MemoryConfig::default().max_messages(50).with_long_term();
    assert_eq!(custom.max_messages, 50);
    assert!(custom.use_long_term);
}

// ============================================================================
// Smoke Tests
// ============================================================================

#[test]
fn smoke_test_imports() {
    // Verify all major types can be imported
    use praisonai::{
        Agent, AgentBuilder, AgentConfig, AgentFlow, AgentTeam, Error, LlmConfig, LlmProvider,
        Memory, MemoryConfig, Message, MockLlmProvider, Process, Result, Role, Tool, ToolRegistry,
        ToolResult,
    };

    // Just verify compilation
    let _ = ToolRegistry::new();
    let _ = MockLlmProvider::new();
    let _ = Memory::default_memory();
    let _ = MemoryConfig::default();
}

#[test]
fn smoke_test_prelude() {
    use praisonai::prelude::*;

    // Verify prelude exports work
    let _ = ToolRegistry::new();
    let _ = MemoryConfig::default();
}

// ============================================================================
// Session Module Tests
// ============================================================================

#[test]
fn test_session_message_creation() {
    use praisonai::SessionMessage;

    let user_msg = SessionMessage::user("Hello");
    assert_eq!(user_msg.role, "user");
    assert_eq!(user_msg.content, "Hello");
    assert!(user_msg.timestamp > 0.0);

    let assistant_msg = SessionMessage::assistant("Hi there!");
    assert_eq!(assistant_msg.role, "assistant");

    let system_msg = SessionMessage::system("You are helpful");
    assert_eq!(system_msg.role, "system");
}

#[test]
fn test_session_data() {
    use praisonai::{SessionData, SessionMessage};

    let mut data = SessionData::new("test-session-123");
    assert_eq!(data.session_id, "test-session-123");
    assert!(data.messages.is_empty());

    data.add_message(SessionMessage::user("Hello"));
    data.add_message(SessionMessage::assistant("Hi!"));

    assert_eq!(data.messages.len(), 2);

    let history = data.get_chat_history(None);
    assert_eq!(history.len(), 2);

    // Test history limit
    let limited = data.get_chat_history(Some(1));
    assert_eq!(limited.len(), 1);
}

#[test]
fn test_in_memory_session_store() {
    use praisonai::{InMemorySessionStore, SessionData, SessionMessage, SessionStore};

    let store = InMemorySessionStore::new();

    // Create and save session
    let mut session = SessionData::new("test-mem");
    session.add_message(SessionMessage::user("Hello"));
    store.save(&session).unwrap();

    assert!(store.exists("test-mem"));

    // Load session
    let loaded = store.load("test-mem").unwrap();
    assert_eq!(loaded.messages.len(), 1);

    // Delete session
    store.delete("test-mem").unwrap();
    assert!(!store.exists("test-mem"));
}

#[test]
fn test_session_api() {
    use praisonai::{InMemorySessionStore, Session, SessionStore};
    use std::sync::Arc;

    let store = Arc::new(InMemorySessionStore::new());
    let mut session = Session::with_store("api-test", store.clone());

    session.add_user_message("Hello").unwrap();
    session.add_assistant_message("Hi!").unwrap();

    assert_eq!(session.message_count(), 2);
    assert_eq!(session.id(), "api-test");

    let history = session.get_history(None);
    assert_eq!(history.len(), 2);

    session.clear().unwrap();
    assert_eq!(session.message_count(), 0);
}

// ============================================================================
// Hooks Module Tests
// ============================================================================

#[test]
fn test_hook_event_types() {
    use praisonai::{HookDecision, HookEvent};

    // Test all event types exist
    let events = vec![
        HookEvent::BeforeTool,
        HookEvent::AfterTool,
        HookEvent::BeforeAgent,
        HookEvent::AfterAgent,
        HookEvent::BeforeLlm,
        HookEvent::AfterLlm,
        HookEvent::OnError,
    ];

    assert_eq!(events.len(), 7);

    // Test decision types
    assert_eq!(HookDecision::default(), HookDecision::Allow);
}

#[test]
fn test_hook_result_creation() {
    use praisonai::HookResult;

    let allow = HookResult::allow();
    assert!(allow.is_allowed());
    assert!(!allow.is_denied());

    let deny = HookResult::deny("Not allowed");
    assert!(!deny.is_allowed());
    assert!(deny.is_denied());
    assert_eq!(deny.reason, Some("Not allowed".to_string()));

    let block = HookResult::block("Blocked");
    assert!(block.is_denied());
}

#[test]
fn test_hook_registry() {
    use praisonai::{HookEvent, HookInput, HookRegistry, HookResult};

    let mut registry = HookRegistry::new();

    // Add a hook that allows everything
    registry.add_hook(HookEvent::BeforeTool, |_| HookResult::allow());

    assert!(registry.has_hooks(HookEvent::BeforeTool));
    assert!(!registry.has_hooks(HookEvent::AfterTool));
    assert_eq!(registry.hook_count(HookEvent::BeforeTool), 1);

    // Execute hook
    let input = HookInput::new(HookEvent::BeforeTool, "session-1")
        .with_tool("search", serde_json::json!({"query": "test"}));

    let result = registry.execute(HookEvent::BeforeTool, &input);
    assert!(result.is_allowed());
}

#[test]
fn test_hook_blocking() {
    use praisonai::{HookEvent, HookInput, HookRegistry, HookResult};

    let mut registry = HookRegistry::new();

    // Add a hook that blocks dangerous tools
    registry.add_hook(HookEvent::BeforeTool, |input| {
        if input.tool_name.as_deref() == Some("dangerous_tool") {
            HookResult::deny("Dangerous tool blocked")
        } else {
            HookResult::allow()
        }
    });

    // Safe tool should be allowed
    let safe_input = HookInput::new(HookEvent::BeforeTool, "session-1")
        .with_tool("search", serde_json::json!({}));
    assert!(registry
        .execute(HookEvent::BeforeTool, &safe_input)
        .is_allowed());

    // Dangerous tool should be blocked
    let dangerous_input = HookInput::new(HookEvent::BeforeTool, "session-1")
        .with_tool("dangerous_tool", serde_json::json!({}));
    assert!(registry
        .execute(HookEvent::BeforeTool, &dangerous_input)
        .is_denied());
}

#[test]
fn test_hook_runner() {
    use praisonai::{HookEvent, HookRegistry, HookResult, HookRunner};

    let mut registry = HookRegistry::new();
    registry.add_hook(HookEvent::BeforeTool, |_| HookResult::allow());
    registry.add_hook(HookEvent::OnError, |_| HookResult::allow());

    let runner = HookRunner::new(registry);

    let result = runner
        .before_tool("session-1", "search", serde_json::json!({"q": "test"}))
        .unwrap();
    assert!(result.is_allowed());

    let error_result = runner
        .on_error("session-1", "Something went wrong")
        .unwrap();
    assert!(error_result.is_allowed());
}

// ============================================================================
// Task Module Tests
// ============================================================================

#[test]
fn test_task_creation() {
    use praisonai::{Task, TaskStatus, TaskType};

    let task = Task::new("Research AI trends")
        .name("research_task")
        .expected_output("A summary of AI trends")
        .build();

    assert_eq!(task.description, "Research AI trends");
    assert_eq!(task.name, Some("research_task".to_string()));
    assert_eq!(task.expected_output, "A summary of AI trends");
    assert_eq!(task.status, TaskStatus::NotStarted);
    assert_eq!(task.task_type, TaskType::Task);
}

#[test]
fn test_task_output() {
    use praisonai::TaskOutput;

    let output = TaskOutput::new("Hello world", "task-1")
        .with_agent("my-agent")
        .with_duration(100)
        .with_tokens(50);

    assert_eq!(output.raw, "Hello world");
    assert_eq!(output.task_id, "task-1");
    assert_eq!(output.agent_name, Some("my-agent".to_string()));
    assert_eq!(output.duration_ms, Some(100));
    assert_eq!(output.tokens_used, Some(50));
    assert_eq!(output.as_str(), "Hello world");
}

#[test]
fn test_task_dependencies() {
    use praisonai::Task;

    let task = Task::new("Analyze data")
        .depends_on("collect_data")
        .depends_on("clean_data")
        .next_task("report")
        .build();

    assert_eq!(task.depends_on.len(), 2);
    assert!(task.depends_on.contains(&"collect_data".to_string()));
    assert!(task.depends_on.contains(&"clean_data".to_string()));
    assert_eq!(task.next_tasks.len(), 1);
}

#[test]
fn test_task_status_transitions() {
    use praisonai::{Task, TaskOutput, TaskStatus};

    let mut task = Task::new("Test task").build();

    assert!(!task.is_completed());
    assert!(!task.is_failed());

    // Complete the task
    task.set_result(TaskOutput::new("Done", &task.id.clone()));
    assert!(task.is_completed());
    assert_eq!(task.status, TaskStatus::Completed);

    // Test failure
    let mut task2 = Task::new("Test task 2").build();
    task2.set_failed("Something went wrong");
    assert!(task2.is_failed());
    assert_eq!(task2.status, TaskStatus::Failed);
}

#[test]
fn test_task_retry_logic() {
    use praisonai::Task;

    let mut task = Task::new("Retryable task").max_retries(3).build();

    assert!(task.can_retry());
    assert_eq!(task.retry_count, 0);

    task.increment_retry();
    assert!(task.can_retry());
    assert_eq!(task.retry_count, 1);

    task.increment_retry();
    task.increment_retry();
    assert!(!task.can_retry());
    assert_eq!(task.retry_count, 3);
}

#[test]
fn test_task_variable_substitution() {
    use praisonai::Task;
    use std::collections::HashMap;

    let task = Task::new("Research {{topic}} trends")
        .variable("topic", serde_json::json!("AI"))
        .build();

    let context = HashMap::new();
    let result = task.substitute_variables(&context);
    assert_eq!(result, "Research AI trends");
}

#[test]
fn test_task_types() {
    use praisonai::{Task, TaskType};

    let decision_task = Task::new("Make a decision").decision().build();
    assert_eq!(decision_task.task_type, TaskType::Decision);

    let loop_task = Task::new("Loop task").loop_task().build();
    assert_eq!(loop_task.task_type, TaskType::Loop);
}

// ============================================================================
// Combined Smoke Tests for New Modules
// ============================================================================

#[test]
fn smoke_test_new_modules() {
    use praisonai::{
        FileSessionStore, HookDecision, HookEvent, HookInput, HookRegistry, HookResult, HookRunner,
        InMemorySessionStore, OnError, Session, SessionData, SessionInfo, SessionMessage,
        SessionStore, Task, TaskBuilder, TaskConfig, TaskOutput, TaskStatus, TaskType,
    };

    // Session types
    let _ = SessionMessage::user("test");
    let _ = SessionData::new("test");
    let _ = InMemorySessionStore::new();

    // Hook types
    let _ = HookRegistry::new();
    let _ = HookResult::allow();
    let _ = HookInput::new(HookEvent::BeforeTool, "session");

    // Task types
    let _ = Task::new("test").build();
    let _ = TaskOutput::new("output", "task-id");
    let _ = TaskConfig::default();
}
