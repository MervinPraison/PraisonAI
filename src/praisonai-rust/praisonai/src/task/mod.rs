//! Task module for PraisonAI Rust SDK.
//!
//! A Task is a unit of work that can be executed by an Agent.
//! Tasks support dependencies, callbacks, guardrails, and various output formats.
//!
//! # Usage
//!
//! ```rust,ignore
//! use praisonai::{Task, Agent};
//!
//! let task = Task::new("Research AI trends")
//!     .expected_output("A summary of current AI trends")
//!     .build();
//!
//! let agent = Agent::new()
//!     .instructions("You are a researcher")
//!     .build()?;
//!
//! let result = task.execute(&agent).await?;
//! ```

use crate::error::{Error, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Task output containing the result of task execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskOutput {
    /// Raw output string
    pub raw: String,
    /// Parsed JSON output (if applicable)
    pub json: Option<serde_json::Value>,
    /// Task ID
    pub task_id: String,
    /// Agent name that executed the task
    pub agent_name: Option<String>,
    /// Execution duration in milliseconds
    pub duration_ms: Option<u64>,
    /// Token usage
    pub tokens_used: Option<u32>,
    /// Additional metadata
    #[serde(default)]
    pub metadata: HashMap<String, serde_json::Value>,
}

impl TaskOutput {
    /// Create a new task output
    pub fn new(raw: impl Into<String>, task_id: impl Into<String>) -> Self {
        Self {
            raw: raw.into(),
            json: None,
            task_id: task_id.into(),
            agent_name: None,
            duration_ms: None,
            tokens_used: None,
            metadata: HashMap::new(),
        }
    }

    /// Set JSON output
    pub fn with_json(mut self, json: serde_json::Value) -> Self {
        self.json = Some(json);
        self
    }

    /// Set agent name
    pub fn with_agent(mut self, name: impl Into<String>) -> Self {
        self.agent_name = Some(name.into());
        self
    }

    /// Set duration
    pub fn with_duration(mut self, ms: u64) -> Self {
        self.duration_ms = Some(ms);
        self
    }

    /// Set token usage
    pub fn with_tokens(mut self, tokens: u32) -> Self {
        self.tokens_used = Some(tokens);
        self
    }

    /// Add metadata
    pub fn with_metadata(mut self, key: impl Into<String>, value: serde_json::Value) -> Self {
        self.metadata.insert(key.into(), value);
        self
    }

    /// Get raw output as string
    pub fn as_str(&self) -> &str {
        &self.raw
    }

    /// Try to parse raw output as JSON
    pub fn parse_json(&self) -> Result<serde_json::Value> {
        serde_json::from_str(&self.raw)
            .map_err(|e| Error::config(format!("Failed to parse output as JSON: {}", e)))
    }
}

impl std::fmt::Display for TaskOutput {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.raw)
    }
}

/// Task status
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
#[derive(Default)]
pub enum TaskStatus {
    /// Not started
    #[default]
    NotStarted,
    /// In progress
    InProgress,
    /// Completed successfully
    Completed,
    /// Failed
    Failed,
    /// Skipped
    Skipped,
}

/// Task type
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
#[derive(Default)]
pub enum TaskType {
    /// Standard task
    #[default]
    Task,
    /// Decision task (routes to different tasks based on output)
    Decision,
    /// Loop task (repeats until condition is met)
    Loop,
}

/// Error handling behavior
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
#[derive(Default)]
pub enum OnError {
    /// Stop workflow on error
    #[default]
    Stop,
    /// Continue to next task
    Continue,
    /// Retry the task
    Retry,
}

/// Task configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskConfig {
    /// Maximum retries
    pub max_retries: u32,
    /// Retry delay in seconds
    pub retry_delay: f64,
    /// Error handling behavior
    pub on_error: OnError,
    /// Whether to skip on failure
    pub skip_on_failure: bool,
    /// Quality check enabled
    pub quality_check: bool,
    /// Async execution
    pub async_execution: bool,
}

impl Default for TaskConfig {
    fn default() -> Self {
        Self {
            max_retries: 3,
            retry_delay: 0.0,
            on_error: OnError::Stop,
            skip_on_failure: false,
            quality_check: true,
            async_execution: false,
        }
    }
}

/// A unit of work that can be executed by an Agent
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Task {
    /// Unique task ID
    pub id: String,
    /// Task name (optional)
    pub name: Option<String>,
    /// Task description (what to do)
    pub description: String,
    /// Expected output description
    pub expected_output: String,
    /// Task status
    pub status: TaskStatus,
    /// Task type
    pub task_type: TaskType,
    /// Task result
    #[serde(skip)]
    pub result: Option<TaskOutput>,
    /// Dependencies (task IDs or names)
    #[serde(default)]
    pub depends_on: Vec<String>,
    /// Next tasks to execute
    #[serde(default)]
    pub next_tasks: Vec<String>,
    /// Condition for routing (decision tasks)
    #[serde(default)]
    pub condition: HashMap<String, Vec<String>>,
    /// Task configuration
    #[serde(default)]
    pub config: TaskConfig,
    /// Output file path
    pub output_file: Option<String>,
    /// Output variable name
    pub output_variable: Option<String>,
    /// Variables for substitution
    #[serde(default)]
    pub variables: HashMap<String, serde_json::Value>,
    /// Retry count
    pub retry_count: u32,
    /// Is this the start task?
    pub is_start: bool,
}

impl Task {
    /// Create a new task with description
    pub fn new(description: impl Into<String>) -> TaskBuilder {
        TaskBuilder::new(description)
    }

    /// Get task ID
    pub fn id(&self) -> &str {
        &self.id
    }

    /// Get task name or description
    pub fn display_name(&self) -> &str {
        self.name.as_deref().unwrap_or(&self.description)
    }

    /// Check if task is completed
    pub fn is_completed(&self) -> bool {
        matches!(self.status, TaskStatus::Completed)
    }

    /// Check if task failed
    pub fn is_failed(&self) -> bool {
        matches!(self.status, TaskStatus::Failed)
    }

    /// Check if task can be retried
    pub fn can_retry(&self) -> bool {
        self.retry_count < self.config.max_retries
    }

    /// Increment retry count
    pub fn increment_retry(&mut self) {
        self.retry_count += 1;
    }

    /// Set task result
    pub fn set_result(&mut self, output: TaskOutput) {
        self.result = Some(output);
        self.status = TaskStatus::Completed;
    }

    /// Set task as failed
    pub fn set_failed(&mut self, error: &str) {
        self.status = TaskStatus::Failed;
        self.result = Some(TaskOutput::new(format!("Error: {}", error), &self.id));
    }

    /// Get result as string
    pub fn result_str(&self) -> Option<&str> {
        self.result.as_ref().map(|r| r.raw.as_str())
    }

    /// Substitute variables in description
    pub fn substitute_variables(&self, context: &HashMap<String, String>) -> String {
        let mut result = self.description.clone();

        // Substitute from context
        for (key, value) in context {
            result = result.replace(&format!("{{{{{}}}}}", key), value);
        }

        // Substitute from task variables
        for (key, value) in &self.variables {
            let value_str = match value {
                serde_json::Value::String(s) => s.clone(),
                _ => value.to_string(),
            };
            result = result.replace(&format!("{{{{{}}}}}", key), &value_str);
        }

        result
    }

    /// Convert to dictionary
    pub fn to_dict(&self) -> serde_json::Value {
        serde_json::json!({
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "expected_output": self.expected_output,
            "status": self.status,
            "task_type": self.task_type,
            "depends_on": self.depends_on,
            "next_tasks": self.next_tasks,
            "condition": self.condition,
            "is_start": self.is_start,
        })
    }
}

/// Builder for Task
pub struct TaskBuilder {
    description: String,
    name: Option<String>,
    expected_output: String,
    depends_on: Vec<String>,
    next_tasks: Vec<String>,
    condition: HashMap<String, Vec<String>>,
    config: TaskConfig,
    output_file: Option<String>,
    output_variable: Option<String>,
    variables: HashMap<String, serde_json::Value>,
    task_type: TaskType,
    is_start: bool,
}

impl TaskBuilder {
    /// Create a new task builder
    pub fn new(description: impl Into<String>) -> Self {
        Self {
            description: description.into(),
            name: None,
            expected_output: "Complete the task successfully".to_string(),
            depends_on: Vec::new(),
            next_tasks: Vec::new(),
            condition: HashMap::new(),
            config: TaskConfig::default(),
            output_file: None,
            output_variable: None,
            variables: HashMap::new(),
            task_type: TaskType::Task,
            is_start: false,
        }
    }

    /// Set task name
    pub fn name(mut self, name: impl Into<String>) -> Self {
        self.name = Some(name.into());
        self
    }

    /// Set expected output
    pub fn expected_output(mut self, output: impl Into<String>) -> Self {
        self.expected_output = output.into();
        self
    }

    /// Add dependency
    pub fn depends_on(mut self, task: impl Into<String>) -> Self {
        self.depends_on.push(task.into());
        self
    }

    /// Add next task
    pub fn next_task(mut self, task: impl Into<String>) -> Self {
        self.next_tasks.push(task.into());
        self
    }

    /// Set task type
    pub fn task_type(mut self, task_type: TaskType) -> Self {
        self.task_type = task_type;
        self
    }

    /// Set as decision task
    pub fn decision(mut self) -> Self {
        self.task_type = TaskType::Decision;
        self
    }

    /// Set as loop task
    pub fn loop_task(mut self) -> Self {
        self.task_type = TaskType::Loop;
        self
    }

    /// Set output file
    pub fn output_file(mut self, path: impl Into<String>) -> Self {
        self.output_file = Some(path.into());
        self
    }

    /// Set output variable
    pub fn output_variable(mut self, name: impl Into<String>) -> Self {
        self.output_variable = Some(name.into());
        self
    }

    /// Add variable
    pub fn variable(mut self, key: impl Into<String>, value: serde_json::Value) -> Self {
        self.variables.insert(key.into(), value);
        self
    }

    /// Set max retries
    pub fn max_retries(mut self, retries: u32) -> Self {
        self.config.max_retries = retries;
        self
    }

    /// Set error handling
    pub fn on_error(mut self, behavior: OnError) -> Self {
        self.config.on_error = behavior;
        self
    }

    /// Set as start task
    pub fn is_start(mut self, is_start: bool) -> Self {
        self.is_start = is_start;
        self
    }

    /// Build the task
    pub fn build(self) -> Task {
        Task {
            id: uuid::Uuid::new_v4().to_string(),
            name: self.name,
            description: self.description,
            expected_output: self.expected_output,
            status: TaskStatus::NotStarted,
            task_type: self.task_type,
            result: None,
            depends_on: self.depends_on,
            next_tasks: self.next_tasks,
            condition: self.condition,
            config: self.config,
            output_file: self.output_file,
            output_variable: self.output_variable,
            variables: self.variables,
            retry_count: 0,
            is_start: self.is_start,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_task_creation() {
        let task = Task::new("Research AI trends")
            .name("research_task")
            .expected_output("A summary of AI trends")
            .build();

        assert_eq!(task.description, "Research AI trends");
        assert_eq!(task.name, Some("research_task".to_string()));
        assert_eq!(task.status, TaskStatus::NotStarted);
    }

    #[test]
    fn test_task_output() {
        let output = TaskOutput::new("Hello world", "task-1")
            .with_agent("my-agent")
            .with_duration(100);

        assert_eq!(output.raw, "Hello world");
        assert_eq!(output.agent_name, Some("my-agent".to_string()));
        assert_eq!(output.duration_ms, Some(100));
    }

    #[test]
    fn test_task_dependencies() {
        let task = Task::new("Analyze data")
            .depends_on("collect_data")
            .depends_on("clean_data")
            .build();

        assert_eq!(task.depends_on.len(), 2);
        assert!(task.depends_on.contains(&"collect_data".to_string()));
    }

    #[test]
    fn test_variable_substitution() {
        let mut variables = HashMap::new();
        variables.insert("topic".to_string(), serde_json::json!("AI"));

        let task = Task::new("Research {{topic}} trends")
            .variable("topic", serde_json::json!("AI"))
            .build();

        let context = HashMap::new();
        let result = task.substitute_variables(&context);
        assert_eq!(result, "Research AI trends");
    }

    #[test]
    fn test_task_status() {
        let mut task = Task::new("Test task").build();

        assert!(!task.is_completed());
        assert!(!task.is_failed());

        task.set_result(TaskOutput::new("Done", &task.id));
        assert!(task.is_completed());

        let mut task2 = Task::new("Test task 2").build();
        task2.set_failed("Something went wrong");
        assert!(task2.is_failed());
    }

    #[test]
    fn test_retry_logic() {
        let mut task = Task::new("Retryable task").max_retries(3).build();

        assert!(task.can_retry());
        task.increment_retry();
        assert!(task.can_retry());
        task.increment_retry();
        assert!(task.can_retry());
        task.increment_retry();
        assert!(!task.can_retry());
    }
}
