//! Display and callback system for PraisonAI
//!
//! This module provides display functions and callback registration matching the Python SDK's
//! main.py display system.
//!
//! # Features
//!
//! - Display functions for various output types (interaction, tool calls, errors, etc.)
//! - Callback registration for custom display handling
//! - Approval callback for dangerous operations
//! - Color palette for consistent UI
//!
//! # Example
//!
//! ```rust,ignore
//! use praisonai::display::{register_display_callback, display_interaction, DisplayType};
//!
//! // Register a custom callback
//! register_display_callback(DisplayType::Interaction, |event| {
//!     println!("Agent: {} said: {}", event.agent_name, event.content);
//! });
//!
//! // Display an interaction
//! display_interaction("assistant", "Hello!", None);
//! ```

use once_cell::sync::Lazy;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::{Arc, RwLock};

// =============================================================================
// COLOR PALETTE
// =============================================================================

/// PraisonAI color palette for consistent UI
#[derive(Debug, Clone)]
pub struct ColorPalette {
    /// Agent identity color
    pub agent: &'static str,
    /// Agent text color
    pub agent_text: &'static str,
    /// Task/Question color
    pub task: &'static str,
    /// Task text color
    pub task_text: &'static str,
    /// Working/Processing color
    pub working: &'static str,
    /// Working text color
    pub working_text: &'static str,
    /// Response/Output color
    pub response: &'static str,
    /// Response text color
    pub response_text: &'static str,
    /// Tool calls color
    pub tool: &'static str,
    /// Tool text color
    pub tool_text: &'static str,
    /// Reasoning color
    pub reasoning: &'static str,
    /// Reasoning text color
    pub reasoning_text: &'static str,
    /// Error/Warning color
    pub error: &'static str,
    /// Error text color
    pub error_text: &'static str,
    /// Metrics color
    pub metrics: &'static str,
    /// Metrics text color
    pub metrics_text: &'static str,
}

/// Default PraisonAI color palette
pub static PRAISON_COLORS: Lazy<ColorPalette> = Lazy::new(|| ColorPalette {
    agent: "#86A789",
    agent_text: "#D2E3C8",
    task: "#FF9B9B",
    task_text: "#FFE5E5",
    working: "#FFB347",
    working_text: "#FFF3E0",
    response: "#4A90D9",
    response_text: "#E3F2FD",
    tool: "#9B7EDE",
    tool_text: "#EDE7F6",
    reasoning: "#78909C",
    reasoning_text: "#ECEFF1",
    error: "#E57373",
    error_text: "#FFEBEE",
    metrics: "#B4B4B3",
    metrics_text: "#FAFAFA",
});

/// Working animation frames
pub static WORKING_FRAMES: &[&str] = &["●○○", "○●○", "○○●", "○●○"];

/// Working animation phases
pub static WORKING_PHASES: &[&str] = &[
    "Analyzing query...",
    "Processing context...",
    "Generating response...",
    "Finalizing output...",
];

// =============================================================================
// DISPLAY TYPES
// =============================================================================

/// Types of display events
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DisplayType {
    /// Agent interaction (prompt/response)
    Interaction,
    /// Self-reflection output
    SelfReflection,
    /// Tool call execution
    ToolCall,
    /// Error message
    Error,
    /// Generating/working status
    Generating,
    /// Instruction display
    Instruction,
    /// Reasoning steps
    Reasoning,
    /// Working status animation
    Working,
}

impl std::fmt::Display for DisplayType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            DisplayType::Interaction => write!(f, "interaction"),
            DisplayType::SelfReflection => write!(f, "self_reflection"),
            DisplayType::ToolCall => write!(f, "tool_call"),
            DisplayType::Error => write!(f, "error"),
            DisplayType::Generating => write!(f, "generating"),
            DisplayType::Instruction => write!(f, "instruction"),
            DisplayType::Reasoning => write!(f, "reasoning"),
            DisplayType::Working => write!(f, "working"),
        }
    }
}

// =============================================================================
// DISPLAY EVENT
// =============================================================================

/// Event data passed to display callbacks
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DisplayEvent {
    /// Type of display event
    pub display_type: DisplayType,
    /// Agent name (if applicable)
    pub agent_name: Option<String>,
    /// Content to display
    pub content: String,
    /// Tool name (for tool calls)
    pub tool_name: Option<String>,
    /// Tool arguments (for tool calls)
    pub tool_args: Option<serde_json::Value>,
    /// Tool result (for tool calls)
    pub tool_result: Option<String>,
    /// Error message (for errors)
    pub error_message: Option<String>,
    /// Additional metadata
    pub metadata: HashMap<String, serde_json::Value>,
}

impl DisplayEvent {
    /// Create a new display event
    pub fn new(display_type: DisplayType, content: impl Into<String>) -> Self {
        Self {
            display_type,
            agent_name: None,
            content: content.into(),
            tool_name: None,
            tool_args: None,
            tool_result: None,
            error_message: None,
            metadata: HashMap::new(),
        }
    }

    /// Set agent name
    pub fn agent(mut self, name: impl Into<String>) -> Self {
        self.agent_name = Some(name.into());
        self
    }

    /// Set tool name
    pub fn tool(mut self, name: impl Into<String>) -> Self {
        self.tool_name = Some(name.into());
        self
    }

    /// Set tool arguments
    pub fn args(mut self, args: serde_json::Value) -> Self {
        self.tool_args = Some(args);
        self
    }

    /// Set tool result
    pub fn result(mut self, result: impl Into<String>) -> Self {
        self.tool_result = Some(result.into());
        self
    }

    /// Set error message
    pub fn error(mut self, error: impl Into<String>) -> Self {
        self.error_message = Some(error.into());
        self
    }

    /// Add metadata
    pub fn meta(mut self, key: impl Into<String>, value: impl Into<serde_json::Value>) -> Self {
        self.metadata.insert(key.into(), value.into());
        self
    }
}

// =============================================================================
// CALLBACK TYPES
// =============================================================================

/// Synchronous display callback function type
pub type SyncDisplayCallback = Box<dyn Fn(&DisplayEvent) + Send + Sync>;

/// Asynchronous display callback function type
pub type AsyncDisplayCallback = Box<dyn Fn(&DisplayEvent) -> std::pin::Pin<Box<dyn std::future::Future<Output = ()> + Send>> + Send + Sync>;

/// Approval decision for dangerous operations
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ApprovalDecision {
    /// Approve the operation
    Approve,
    /// Deny the operation
    Deny,
    /// Approve all similar operations
    ApproveAll,
    /// Deny all similar operations
    DenyAll,
}

/// Risk level for operations requiring approval
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RiskLevel {
    /// Low risk operation
    Low,
    /// Medium risk operation
    Medium,
    /// High risk operation
    High,
    /// Critical risk operation
    Critical,
}

/// Approval callback function type
pub type ApprovalCallback = Box<dyn Fn(&str, &serde_json::Value, RiskLevel) -> ApprovalDecision + Send + Sync>;

// =============================================================================
// CALLBACK REGISTRY
// =============================================================================

/// Global callback registry
struct CallbackRegistry {
    sync_callbacks: HashMap<DisplayType, Vec<SyncDisplayCallback>>,
    async_callbacks: HashMap<DisplayType, Vec<AsyncDisplayCallback>>,
    approval_callback: Option<ApprovalCallback>,
}

impl CallbackRegistry {
    fn new() -> Self {
        Self {
            sync_callbacks: HashMap::new(),
            async_callbacks: HashMap::new(),
            approval_callback: None,
        }
    }
}

static CALLBACK_REGISTRY: Lazy<RwLock<CallbackRegistry>> =
    Lazy::new(|| RwLock::new(CallbackRegistry::new()));

// =============================================================================
// CALLBACK REGISTRATION
// =============================================================================

/// Register a synchronous display callback
pub fn register_display_callback<F>(display_type: DisplayType, callback: F)
where
    F: Fn(&DisplayEvent) + Send + Sync + 'static,
{
    let mut registry = CALLBACK_REGISTRY.write().unwrap();
    registry
        .sync_callbacks
        .entry(display_type)
        .or_insert_with(Vec::new)
        .push(Box::new(callback));
}

/// Register an asynchronous display callback
pub fn register_async_display_callback<F, Fut>(display_type: DisplayType, callback: F)
where
    F: Fn(&DisplayEvent) -> Fut + Send + Sync + 'static,
    Fut: std::future::Future<Output = ()> + Send + 'static,
{
    let mut registry = CALLBACK_REGISTRY.write().unwrap();
    registry
        .async_callbacks
        .entry(display_type)
        .or_insert_with(Vec::new)
        .push(Box::new(move |event| {
            let fut = callback(event);
            Box::pin(fut)
        }));
}

/// Register an approval callback for dangerous operations
pub fn register_approval_callback<F>(callback: F)
where
    F: Fn(&str, &serde_json::Value, RiskLevel) -> ApprovalDecision + Send + Sync + 'static,
{
    let mut registry = CALLBACK_REGISTRY.write().unwrap();
    registry.approval_callback = Some(Box::new(callback));
}

/// Alias for register_display_callback (consistent naming)
pub fn add_display_callback<F>(display_type: DisplayType, callback: F)
where
    F: Fn(&DisplayEvent) + Send + Sync + 'static,
{
    register_display_callback(display_type, callback);
}

/// Alias for register_approval_callback (consistent naming)
pub fn add_approval_callback<F>(callback: F)
where
    F: Fn(&str, &serde_json::Value, RiskLevel) -> ApprovalDecision + Send + Sync + 'static,
{
    register_approval_callback(callback);
}

/// Clear all callbacks for a display type
pub fn clear_display_callbacks(display_type: DisplayType) {
    let mut registry = CALLBACK_REGISTRY.write().unwrap();
    registry.sync_callbacks.remove(&display_type);
    registry.async_callbacks.remove(&display_type);
}

/// Clear all callbacks
pub fn clear_all_callbacks() {
    let mut registry = CALLBACK_REGISTRY.write().unwrap();
    registry.sync_callbacks.clear();
    registry.async_callbacks.clear();
    registry.approval_callback = None;
}

// =============================================================================
// CALLBACK EXECUTION
// =============================================================================

/// Execute synchronous callbacks for a display event
pub fn execute_sync_callbacks(event: &DisplayEvent) {
    let registry = CALLBACK_REGISTRY.read().unwrap();
    if let Some(callbacks) = registry.sync_callbacks.get(&event.display_type) {
        for callback in callbacks {
            callback(event);
        }
    }
}

/// Execute asynchronous callbacks for a display event
pub async fn execute_async_callbacks(event: &DisplayEvent) {
    let callbacks: Vec<_> = {
        let registry = CALLBACK_REGISTRY.read().unwrap();
        registry
            .async_callbacks
            .get(&event.display_type)
            .map(|cbs| cbs.iter().map(|cb| cb(event)).collect())
            .unwrap_or_default()
    };

    for fut in callbacks {
        fut.await;
    }
}

/// Execute all callbacks (sync and async) for a display event
pub async fn execute_callbacks(event: &DisplayEvent) {
    execute_sync_callbacks(event);
    execute_async_callbacks(event).await;
}

/// Request approval for a dangerous operation
pub fn request_approval(
    function_name: &str,
    arguments: &serde_json::Value,
    risk_level: RiskLevel,
) -> ApprovalDecision {
    let registry = CALLBACK_REGISTRY.read().unwrap();
    if let Some(callback) = &registry.approval_callback {
        callback(function_name, arguments, risk_level)
    } else {
        // Default to deny if no callback is registered
        ApprovalDecision::Deny
    }
}

// =============================================================================
// DISPLAY FUNCTIONS
// =============================================================================

/// Display an agent interaction
pub fn display_interaction(agent_name: &str, content: &str, response_type: Option<&str>) {
    let event = DisplayEvent::new(DisplayType::Interaction, content)
        .agent(agent_name)
        .meta("response_type", response_type.unwrap_or("response"));

    execute_sync_callbacks(&event);

    // Default console output if no callbacks registered
    let registry = CALLBACK_REGISTRY.read().unwrap();
    if registry.sync_callbacks.get(&DisplayType::Interaction).is_none() {
        println!("[{}] {}", agent_name, content);
    }
}

/// Display an instruction
pub fn display_instruction(agent_name: &str, instruction: &str) {
    let event = DisplayEvent::new(DisplayType::Instruction, instruction).agent(agent_name);

    execute_sync_callbacks(&event);

    let registry = CALLBACK_REGISTRY.read().unwrap();
    if registry.sync_callbacks.get(&DisplayType::Instruction).is_none() {
        println!("📋 [{}] Instruction: {}", agent_name, instruction);
    }
}

/// Display a tool call
pub fn display_tool_call(
    agent_name: &str,
    tool_name: &str,
    arguments: &serde_json::Value,
    result: Option<&str>,
) {
    let mut event = DisplayEvent::new(DisplayType::ToolCall, format!("Calling {}", tool_name))
        .agent(agent_name)
        .tool(tool_name)
        .args(arguments.clone());

    if let Some(r) = result {
        event = event.result(r);
    }

    execute_sync_callbacks(&event);

    let registry = CALLBACK_REGISTRY.read().unwrap();
    if registry.sync_callbacks.get(&DisplayType::ToolCall).is_none() {
        println!("🔧 [{}] Tool: {} with args: {}", agent_name, tool_name, arguments);
        if let Some(r) = result {
            println!("   Result: {}", r);
        }
    }
}

/// Display an error
pub fn display_error(agent_name: Option<&str>, error_message: &str) {
    let mut event = DisplayEvent::new(DisplayType::Error, error_message).error(error_message);

    if let Some(name) = agent_name {
        event = event.agent(name);
    }

    execute_sync_callbacks(&event);

    let registry = CALLBACK_REGISTRY.read().unwrap();
    if registry.sync_callbacks.get(&DisplayType::Error).is_none() {
        if let Some(name) = agent_name {
            eprintln!("❌ [{}] Error: {}", name, error_message);
        } else {
            eprintln!("❌ Error: {}", error_message);
        }
    }
}

/// Display generating/working status
pub fn display_generating(agent_name: &str, status: &str) {
    let event = DisplayEvent::new(DisplayType::Generating, status).agent(agent_name);

    execute_sync_callbacks(&event);

    let registry = CALLBACK_REGISTRY.read().unwrap();
    if registry.sync_callbacks.get(&DisplayType::Generating).is_none() {
        println!("⏳ [{}] {}", agent_name, status);
    }
}

/// Display reasoning steps
pub fn display_reasoning_steps(agent_name: &str, steps: &[String]) {
    let content = steps.join("\n");
    let event = DisplayEvent::new(DisplayType::Reasoning, &content)
        .agent(agent_name)
        .meta("step_count", steps.len());

    execute_sync_callbacks(&event);

    let registry = CALLBACK_REGISTRY.read().unwrap();
    if registry.sync_callbacks.get(&DisplayType::Reasoning).is_none() {
        println!("🧠 [{}] Reasoning:", agent_name);
        for (i, step) in steps.iter().enumerate() {
            println!("   {}. {}", i + 1, step);
        }
    }
}

/// Display working status with animation frame
pub fn display_working_status(agent_name: &str, phase_index: usize, frame_index: usize) {
    let phase = WORKING_PHASES.get(phase_index % WORKING_PHASES.len()).unwrap_or(&"Working...");
    let frame = WORKING_FRAMES.get(frame_index % WORKING_FRAMES.len()).unwrap_or(&"...");

    let event = DisplayEvent::new(DisplayType::Working, format!("{} {}", frame, phase))
        .agent(agent_name)
        .meta("phase_index", phase_index)
        .meta("frame_index", frame_index);

    execute_sync_callbacks(&event);

    let registry = CALLBACK_REGISTRY.read().unwrap();
    if registry.sync_callbacks.get(&DisplayType::Working).is_none() {
        print!("\r{} [{}] {}", frame, agent_name, phase);
        use std::io::Write;
        std::io::stdout().flush().ok();
    }
}

/// Display self-reflection output
pub fn display_self_reflection(agent_name: &str, reflection: &str, iteration: usize) {
    let event = DisplayEvent::new(DisplayType::SelfReflection, reflection)
        .agent(agent_name)
        .meta("iteration", iteration);

    execute_sync_callbacks(&event);

    let registry = CALLBACK_REGISTRY.read().unwrap();
    if registry.sync_callbacks.get(&DisplayType::SelfReflection).is_none() {
        println!("🔄 [{}] Reflection (iteration {}): {}", agent_name, iteration, reflection);
    }
}

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

/// Clean content for display (truncate if too long)
pub fn clean_display_content(content: &str, max_length: usize) -> String {
    if content.len() <= max_length {
        content.to_string()
    } else {
        format!("{}...", &content[..max_length - 3])
    }
}

/// Check if callbacks are registered for a display type
pub fn has_callbacks(display_type: DisplayType) -> bool {
    let registry = CALLBACK_REGISTRY.read().unwrap();
    registry.sync_callbacks.contains_key(&display_type)
        || registry.async_callbacks.contains_key(&display_type)
}

/// Get the number of registered callbacks for a display type
pub fn callback_count(display_type: DisplayType) -> usize {
    let registry = CALLBACK_REGISTRY.read().unwrap();
    let sync_count = registry
        .sync_callbacks
        .get(&display_type)
        .map(|v| v.len())
        .unwrap_or(0);
    let async_count = registry
        .async_callbacks
        .get(&display_type)
        .map(|v| v.len())
        .unwrap_or(0);
    sync_count + async_count
}

// =============================================================================
// TESTS
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    #[test]
    fn test_display_event_builder() {
        let event = DisplayEvent::new(DisplayType::Interaction, "Hello")
            .agent("assistant")
            .tool("search")
            .args(serde_json::json!({"query": "test"}))
            .result("Found 5 results")
            .meta("custom", "value");

        assert_eq!(event.display_type, DisplayType::Interaction);
        assert_eq!(event.content, "Hello");
        assert_eq!(event.agent_name, Some("assistant".to_string()));
        assert_eq!(event.tool_name, Some("search".to_string()));
        assert!(event.tool_args.is_some());
        assert_eq!(event.tool_result, Some("Found 5 results".to_string()));
        assert!(event.metadata.contains_key("custom"));
    }

    #[test]
    fn test_display_type_display() {
        assert_eq!(DisplayType::Interaction.to_string(), "interaction");
        assert_eq!(DisplayType::ToolCall.to_string(), "tool_call");
        assert_eq!(DisplayType::Error.to_string(), "error");
    }

    #[test]
    fn test_clean_display_content() {
        let short = "Hello";
        assert_eq!(clean_display_content(short, 100), "Hello");

        let long = "a".repeat(100);
        let cleaned = clean_display_content(&long, 50);
        assert_eq!(cleaned.len(), 50);
        assert!(cleaned.ends_with("..."));
    }

    #[test]
    fn test_callback_registration() {
        // Clear any existing callbacks first
        clear_all_callbacks();

        static CALL_COUNT: AtomicUsize = AtomicUsize::new(0);

        register_display_callback(DisplayType::Interaction, |_event| {
            CALL_COUNT.fetch_add(1, Ordering::SeqCst);
        });

        assert!(has_callbacks(DisplayType::Interaction));
        assert_eq!(callback_count(DisplayType::Interaction), 1);

        let event = DisplayEvent::new(DisplayType::Interaction, "test");
        execute_sync_callbacks(&event);

        assert!(CALL_COUNT.load(Ordering::SeqCst) >= 1);

        clear_display_callbacks(DisplayType::Interaction);
        assert!(!has_callbacks(DisplayType::Interaction));
    }

    #[test]
    fn test_approval_decision() {
        clear_all_callbacks();

        // Without callback, should deny
        let decision = request_approval("delete_file", &serde_json::json!({}), RiskLevel::High);
        assert_eq!(decision, ApprovalDecision::Deny);

        // With callback
        register_approval_callback(|_name, _args, _risk| ApprovalDecision::Approve);

        let decision = request_approval("delete_file", &serde_json::json!({}), RiskLevel::High);
        assert_eq!(decision, ApprovalDecision::Approve);

        clear_all_callbacks();
    }

    #[test]
    fn test_color_palette() {
        assert_eq!(PRAISON_COLORS.agent, "#86A789");
        assert_eq!(PRAISON_COLORS.error, "#E57373");
    }

    #[test]
    fn test_working_frames() {
        assert_eq!(WORKING_FRAMES.len(), 4);
        assert_eq!(WORKING_PHASES.len(), 4);
    }
}
