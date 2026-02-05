//! Display and Callback Types
//!
//! Provides display callback types and error logging matching Python SDK:
//! - sync_display_callbacks, async_display_callbacks
//! - error_logs, ApprovalCallback
//! - Display functions and callback registration

use std::collections::HashMap;
use std::sync::{Arc, RwLock};

// =============================================================================
// Global State
// =============================================================================

lazy_static::lazy_static! {
    /// Global error logs
    static ref ERROR_LOGS: RwLock<Vec<ErrorLog>> = RwLock::new(Vec::new());
    
    /// Sync display callbacks registry
    static ref SYNC_DISPLAY_CALLBACKS: RwLock<HashMap<String, Arc<dyn DisplayCallback>>> = 
        RwLock::new(HashMap::new());
    
    /// Async display callbacks registry  
    static ref ASYNC_DISPLAY_CALLBACKS: RwLock<HashMap<String, Arc<dyn AsyncDisplayCallback>>> = 
        RwLock::new(HashMap::new());
    
    /// Global approval callback
    static ref APPROVAL_CALLBACK: RwLock<Option<Arc<dyn ApprovalCallback>>> = 
        RwLock::new(None);
}

// =============================================================================
// Error Log Types
// =============================================================================

/// Error log entry
#[derive(Debug, Clone)]
pub struct ErrorLog {
    /// Error message
    pub message: String,
    /// Error type/category
    pub error_type: String,
    /// Timestamp
    pub timestamp: std::time::SystemTime,
    /// Additional context
    pub context: HashMap<String, String>,
}

impl ErrorLog {
    /// Create a new error log
    pub fn new(message: impl Into<String>, error_type: impl Into<String>) -> Self {
        Self {
            message: message.into(),
            error_type: error_type.into(),
            timestamp: std::time::SystemTime::now(),
            context: HashMap::new(),
        }
    }

    /// Add context
    pub fn with_context(mut self, key: impl Into<String>, value: impl Into<String>) -> Self {
        self.context.insert(key.into(), value.into());
        self
    }
}

/// Get all error logs
pub fn get_error_logs() -> Vec<ErrorLog> {
    ERROR_LOGS.read().unwrap().clone()
}

/// Add an error log
pub fn add_error_log(log: ErrorLog) {
    ERROR_LOGS.write().unwrap().push(log);
}

/// Clear error logs
pub fn clear_error_logs() {
    ERROR_LOGS.write().unwrap().clear();
}

/// Log an error (convenience function)
pub fn log_error(message: impl Into<String>, error_type: impl Into<String>) {
    add_error_log(ErrorLog::new(message, error_type));
}

// =============================================================================
// Display Callback Traits
// =============================================================================

/// Display callback trait for synchronous callbacks
pub trait DisplayCallback: Send + Sync {
    /// Handle display event
    fn on_display(&self, event: &DisplayEvent);
}

/// Display callback trait for asynchronous callbacks
#[async_trait::async_trait]
pub trait AsyncDisplayCallback: Send + Sync {
    /// Handle display event asynchronously
    async fn on_display(&self, event: &DisplayEvent);
}

/// Display event types
#[derive(Debug, Clone)]
pub enum DisplayEventType {
    /// Agent interaction
    Interaction,
    /// Self reflection
    SelfReflection,
    /// Tool call
    ToolCall,
    /// Error
    Error,
    /// Generating response
    Generating,
    /// Reasoning steps
    ReasoningSteps,
    /// Working status
    WorkingStatus,
    /// Instruction
    Instruction,
    /// Custom event
    Custom(String),
}

/// Display event
#[derive(Debug, Clone)]
pub struct DisplayEvent {
    /// Event type
    pub event_type: DisplayEventType,
    /// Agent name (if applicable)
    pub agent_name: Option<String>,
    /// Content/message
    pub content: Option<String>,
    /// Additional data
    pub data: HashMap<String, serde_json::Value>,
}

impl DisplayEvent {
    /// Create a new display event
    pub fn new(event_type: DisplayEventType) -> Self {
        Self {
            event_type,
            agent_name: None,
            content: None,
            data: HashMap::new(),
        }
    }

    /// Set agent name
    pub fn agent(mut self, name: impl Into<String>) -> Self {
        self.agent_name = Some(name.into());
        self
    }

    /// Set content
    pub fn content(mut self, content: impl Into<String>) -> Self {
        self.content = Some(content.into());
        self
    }

    /// Add data
    pub fn data(mut self, key: impl Into<String>, value: serde_json::Value) -> Self {
        self.data.insert(key.into(), value);
        self
    }
}

// =============================================================================
// Callback Registration
// =============================================================================

/// Register a synchronous display callback
pub fn register_display_callback(
    display_type: impl Into<String>,
    callback: Arc<dyn DisplayCallback>,
) {
    SYNC_DISPLAY_CALLBACKS
        .write()
        .unwrap()
        .insert(display_type.into(), callback);
}

/// Register an asynchronous display callback
pub fn register_async_display_callback(
    display_type: impl Into<String>,
    callback: Arc<dyn AsyncDisplayCallback>,
) {
    ASYNC_DISPLAY_CALLBACKS
        .write()
        .unwrap()
        .insert(display_type.into(), callback);
}

/// Alias for register_display_callback
pub fn add_display_callback(
    display_type: impl Into<String>,
    callback: Arc<dyn DisplayCallback>,
) {
    register_display_callback(display_type, callback);
}

/// Remove a display callback
pub fn remove_display_callback(display_type: &str) {
    SYNC_DISPLAY_CALLBACKS.write().unwrap().remove(display_type);
    ASYNC_DISPLAY_CALLBACKS.write().unwrap().remove(display_type);
}

/// Execute sync callback for a display type
pub fn execute_callback(display_type: &str, event: &DisplayEvent) {
    if let Some(callback) = SYNC_DISPLAY_CALLBACKS.read().unwrap().get(display_type) {
        callback.on_display(event);
    }
}

/// Execute async callback for a display type
pub async fn execute_async_callback(display_type: &str, event: &DisplayEvent) {
    if let Some(callback) = ASYNC_DISPLAY_CALLBACKS.read().unwrap().get(display_type) {
        callback.on_display(event).await;
    }
}

// =============================================================================
// Approval Callback
// =============================================================================

/// Approval decision
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ApprovalDecision {
    /// Approve the action
    Approve,
    /// Deny the action
    Deny,
    /// Ask for more information
    AskMore,
}

/// Risk level for approval
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum RiskLevel {
    /// Low risk
    Low,
    /// Medium risk
    Medium,
    /// High risk
    High,
    /// Critical risk
    Critical,
}

/// Approval callback trait
pub trait ApprovalCallback: Send + Sync {
    /// Request approval for an action
    fn request_approval(
        &self,
        function_name: &str,
        arguments: &serde_json::Value,
        risk_level: RiskLevel,
    ) -> ApprovalDecision;
}

/// Register the global approval callback
pub fn register_approval_callback(callback: Arc<dyn ApprovalCallback>) {
    *APPROVAL_CALLBACK.write().unwrap() = Some(callback);
}

/// Alias for register_approval_callback
pub fn add_approval_callback(callback: Arc<dyn ApprovalCallback>) {
    register_approval_callback(callback);
}

/// Remove the approval callback
pub fn remove_approval_callback() {
    *APPROVAL_CALLBACK.write().unwrap() = None;
}

/// Request approval using the global callback
pub fn request_approval(
    function_name: &str,
    arguments: &serde_json::Value,
    risk_level: RiskLevel,
) -> ApprovalDecision {
    if let Some(callback) = APPROVAL_CALLBACK.read().unwrap().as_ref() {
        callback.request_approval(function_name, arguments, risk_level)
    } else {
        // Default: approve low/medium risk, deny high/critical
        match risk_level {
            RiskLevel::Low | RiskLevel::Medium => ApprovalDecision::Approve,
            RiskLevel::High | RiskLevel::Critical => ApprovalDecision::Deny,
        }
    }
}

// =============================================================================
// Display Color Palette
// =============================================================================

/// PraisonAI color palette
pub struct PraisonColors;

impl PraisonColors {
    /// Agent identity - grounded, stable
    pub const AGENT: &'static str = "#86A789";
    pub const AGENT_TEXT: &'static str = "#D2E3C8";

    /// Task/Question - input, attention-grabbing
    pub const TASK: &'static str = "#FF9B9B";
    pub const TASK_TEXT: &'static str = "#FFE5E5";

    /// Working/Processing - action, energy
    pub const WORKING: &'static str = "#FFB347";
    pub const WORKING_TEXT: &'static str = "#FFF3E0";

    /// Response/Output - completion, calm
    pub const RESPONSE: &'static str = "#4A90D9";
    pub const RESPONSE_TEXT: &'static str = "#E3F2FD";

    /// Tool calls - special action
    pub const TOOL: &'static str = "#9B7EDE";
    pub const TOOL_TEXT: &'static str = "#EDE7F6";

    /// Reasoning - thought process
    pub const REASONING: &'static str = "#78909C";
    pub const REASONING_TEXT: &'static str = "#ECEFF1";

    /// Error/Warning - alert
    pub const ERROR: &'static str = "#E57373";
    pub const ERROR_TEXT: &'static str = "#FFEBEE";

    /// Metrics - meta information
    pub const METRICS: &'static str = "#B4B4B3";
    pub const METRICS_TEXT: &'static str = "#FAFAFA";
}

// =============================================================================
// Working Animation
// =============================================================================

/// Working animation frames
pub const WORKING_FRAMES: &[&str] = &["●○○", "○●○", "○○●", "○●○"];

/// Working phases
pub const WORKING_PHASES: &[&str] = &[
    "Analyzing query...",
    "Processing context...",
    "Generating response...",
    "Finalizing output...",
];

// =============================================================================
// Flow Display
// =============================================================================

/// Flow display for workflow visualization
#[derive(Debug, Clone, Default)]
pub struct FlowDisplay {
    /// Current step index
    pub current_step: usize,
    /// Total steps
    pub total_steps: usize,
    /// Step names
    pub steps: Vec<String>,
    /// Completed steps
    pub completed: Vec<bool>,
    /// Current status message
    pub status: Option<String>,
}

impl FlowDisplay {
    /// Create a new flow display
    pub fn new(steps: Vec<String>) -> Self {
        let total = steps.len();
        Self {
            current_step: 0,
            total_steps: total,
            steps,
            completed: vec![false; total],
            status: None,
        }
    }

    /// Mark current step as complete and move to next
    pub fn complete_step(&mut self) {
        if self.current_step < self.total_steps {
            self.completed[self.current_step] = true;
            self.current_step += 1;
        }
    }

    /// Set status message
    pub fn set_status(&mut self, status: impl Into<String>) {
        self.status = Some(status.into());
    }

    /// Get progress percentage
    pub fn progress(&self) -> f32 {
        if self.total_steps == 0 {
            return 100.0;
        }
        (self.completed.iter().filter(|&&c| c).count() as f32 / self.total_steps as f32) * 100.0
    }

    /// Check if all steps are complete
    pub fn is_complete(&self) -> bool {
        self.completed.iter().all(|&c| c)
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_error_log() {
        let log = ErrorLog::new("Test error", "TestType")
            .with_context("key1", "value1");

        assert_eq!(log.message, "Test error");
        assert_eq!(log.error_type, "TestType");
        assert_eq!(log.context.get("key1"), Some(&"value1".to_string()));
    }

    #[test]
    fn test_display_event() {
        let event = DisplayEvent::new(DisplayEventType::Interaction)
            .agent("TestAgent")
            .content("Hello")
            .data("key", serde_json::json!("value"));

        assert!(matches!(event.event_type, DisplayEventType::Interaction));
        assert_eq!(event.agent_name, Some("TestAgent".to_string()));
        assert_eq!(event.content, Some("Hello".to_string()));
    }

    #[test]
    fn test_approval_decision_default() {
        // Without callback, low/medium risk should be approved
        assert_eq!(
            request_approval("test", &serde_json::json!({}), RiskLevel::Low),
            ApprovalDecision::Approve
        );
        assert_eq!(
            request_approval("test", &serde_json::json!({}), RiskLevel::Medium),
            ApprovalDecision::Approve
        );
        // High/critical should be denied
        assert_eq!(
            request_approval("test", &serde_json::json!({}), RiskLevel::High),
            ApprovalDecision::Deny
        );
    }

    #[test]
    fn test_flow_display() {
        let mut flow = FlowDisplay::new(vec![
            "Step 1".to_string(),
            "Step 2".to_string(),
            "Step 3".to_string(),
        ]);

        assert_eq!(flow.current_step, 0);
        assert_eq!(flow.progress(), 0.0);
        assert!(!flow.is_complete());

        flow.complete_step();
        assert_eq!(flow.current_step, 1);
        assert!((flow.progress() - 33.33).abs() < 1.0);

        flow.complete_step();
        flow.complete_step();
        assert!(flow.is_complete());
        assert_eq!(flow.progress(), 100.0);
    }

    #[test]
    fn test_praison_colors() {
        assert_eq!(PraisonColors::AGENT, "#86A789");
        assert_eq!(PraisonColors::TOOL, "#9B7EDE");
        assert_eq!(PraisonColors::ERROR, "#E57373");
    }
}
