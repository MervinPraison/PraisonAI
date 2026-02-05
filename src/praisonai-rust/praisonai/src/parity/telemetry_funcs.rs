//! Telemetry Functions
//!
//! Provides telemetry management functions matching Python SDK:
//! - get_telemetry, enable_telemetry, disable_telemetry
//! - enable_performance_mode, disable_performance_mode
//! - cleanup_telemetry_resources
//! - MinimalTelemetry

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::OnceLock;

// =============================================================================
// Global State
// =============================================================================

static TELEMETRY_ENABLED: AtomicBool = AtomicBool::new(true);
static PERFORMANCE_MODE: AtomicBool = AtomicBool::new(false);
static TELEMETRY_INSTANCE: OnceLock<MinimalTelemetry> = OnceLock::new();

// =============================================================================
// Telemetry Types
// =============================================================================

/// Minimal telemetry implementation
///
/// Provides basic telemetry functionality with minimal overhead.
/// When performance mode is enabled, telemetry operations are no-ops.
#[derive(Debug, Clone)]
pub struct MinimalTelemetry {
    /// Whether telemetry is enabled
    enabled: bool,
    /// Session ID for correlation
    session_id: String,
    /// User ID (optional)
    user_id: Option<String>,
    /// Additional properties
    properties: std::collections::HashMap<String, serde_json::Value>,
}

impl Default for MinimalTelemetry {
    fn default() -> Self {
        Self::new()
    }
}

impl MinimalTelemetry {
    /// Create a new minimal telemetry instance
    pub fn new() -> Self {
        Self {
            enabled: true,
            session_id: uuid::Uuid::new_v4().to_string(),
            user_id: None,
            properties: std::collections::HashMap::new(),
        }
    }

    /// Create with specific session ID
    pub fn with_session_id(session_id: impl Into<String>) -> Self {
        Self {
            enabled: true,
            session_id: session_id.into(),
            user_id: None,
            properties: std::collections::HashMap::new(),
        }
    }

    /// Set user ID
    pub fn set_user_id(&mut self, user_id: impl Into<String>) {
        self.user_id = Some(user_id.into());
    }

    /// Get session ID
    pub fn session_id(&self) -> &str {
        &self.session_id
    }

    /// Get user ID
    pub fn user_id(&self) -> Option<&str> {
        self.user_id.as_deref()
    }

    /// Check if telemetry is enabled
    pub fn is_enabled(&self) -> bool {
        self.enabled && TELEMETRY_ENABLED.load(Ordering::Relaxed)
    }

    /// Enable telemetry
    pub fn enable(&mut self) {
        self.enabled = true;
    }

    /// Disable telemetry
    pub fn disable(&mut self) {
        self.enabled = false;
    }

    /// Set a property
    pub fn set_property(&mut self, key: impl Into<String>, value: serde_json::Value) {
        self.properties.insert(key.into(), value);
    }

    /// Get a property
    pub fn get_property(&self, key: &str) -> Option<&serde_json::Value> {
        self.properties.get(key)
    }

    /// Track an event (no-op if disabled or in performance mode)
    pub fn track_event(&self, event_name: &str, properties: Option<&serde_json::Value>) {
        if !self.is_enabled() || PERFORMANCE_MODE.load(Ordering::Relaxed) {
            return;
        }

        // In a real implementation, this would send to a telemetry backend
        tracing::debug!(
            event = event_name,
            session_id = %self.session_id,
            properties = ?properties,
            "Telemetry event"
        );
    }

    /// Track agent start
    pub fn track_agent_start(&self, agent_name: &str, model: &str) {
        self.track_event(
            "agent_start",
            Some(&serde_json::json!({
                "agent_name": agent_name,
                "model": model,
            })),
        );
    }

    /// Track agent completion
    pub fn track_agent_complete(&self, agent_name: &str, duration_ms: u64) {
        self.track_event(
            "agent_complete",
            Some(&serde_json::json!({
                "agent_name": agent_name,
                "duration_ms": duration_ms,
            })),
        );
    }

    /// Track tool execution
    pub fn track_tool_execution(&self, tool_name: &str, success: bool, duration_ms: u64) {
        self.track_event(
            "tool_execution",
            Some(&serde_json::json!({
                "tool_name": tool_name,
                "success": success,
                "duration_ms": duration_ms,
            })),
        );
    }

    /// Track LLM call
    pub fn track_llm_call(
        &self,
        model: &str,
        input_tokens: Option<u32>,
        output_tokens: Option<u32>,
        duration_ms: u64,
    ) {
        self.track_event(
            "llm_call",
            Some(&serde_json::json!({
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "duration_ms": duration_ms,
            })),
        );
    }

    /// Track error
    pub fn track_error(&self, error_type: &str, error_message: &str) {
        self.track_event(
            "error",
            Some(&serde_json::json!({
                "error_type": error_type,
                "error_message": error_message,
            })),
        );
    }

    /// Flush any pending events
    pub fn flush(&self) {
        // In a real implementation, this would flush to the backend
        tracing::debug!("Telemetry flush");
    }

    /// Cleanup resources
    pub fn cleanup(&self) {
        self.flush();
        tracing::debug!("Telemetry cleanup");
    }
}

// =============================================================================
// Global Functions
// =============================================================================

/// Get the global telemetry instance
pub fn get_telemetry() -> &'static MinimalTelemetry {
    TELEMETRY_INSTANCE.get_or_init(MinimalTelemetry::new)
}

/// Enable telemetry globally
pub fn enable_telemetry() {
    TELEMETRY_ENABLED.store(true, Ordering::Relaxed);
    tracing::info!("Telemetry enabled");
}

/// Disable telemetry globally
pub fn disable_telemetry() {
    TELEMETRY_ENABLED.store(false, Ordering::Relaxed);
    tracing::info!("Telemetry disabled");
}

/// Check if telemetry is enabled globally
pub fn is_telemetry_enabled() -> bool {
    TELEMETRY_ENABLED.load(Ordering::Relaxed)
}

/// Enable performance mode (disables telemetry overhead)
pub fn enable_performance_mode() {
    PERFORMANCE_MODE.store(true, Ordering::Relaxed);
    tracing::info!("Performance mode enabled - telemetry overhead disabled");
}

/// Disable performance mode
pub fn disable_performance_mode() {
    PERFORMANCE_MODE.store(false, Ordering::Relaxed);
    tracing::info!("Performance mode disabled");
}

/// Check if performance mode is enabled
pub fn is_performance_mode() -> bool {
    PERFORMANCE_MODE.load(Ordering::Relaxed)
}

/// Cleanup telemetry resources
pub fn cleanup_telemetry_resources() {
    if let Some(telemetry) = TELEMETRY_INSTANCE.get() {
        telemetry.cleanup();
    }
    tracing::info!("Telemetry resources cleaned up");
}

// =============================================================================
// Telemetry Context
// =============================================================================

/// Telemetry context for scoped tracking
#[derive(Debug)]
pub struct TelemetryContext {
    /// Context name
    pub name: String,
    /// Start time
    start_time: std::time::Instant,
    /// Properties
    properties: std::collections::HashMap<String, serde_json::Value>,
}

impl TelemetryContext {
    /// Create a new telemetry context
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            start_time: std::time::Instant::now(),
            properties: std::collections::HashMap::new(),
        }
    }

    /// Add a property
    pub fn property(mut self, key: impl Into<String>, value: serde_json::Value) -> Self {
        self.properties.insert(key.into(), value);
        self
    }

    /// Get elapsed time in milliseconds
    pub fn elapsed_ms(&self) -> u64 {
        self.start_time.elapsed().as_millis() as u64
    }

    /// Complete the context and track event
    pub fn complete(self) {
        let telemetry = get_telemetry();
        let mut props = self.properties.clone();
        props.insert("duration_ms".to_string(), serde_json::json!(self.elapsed_ms()));
        telemetry.track_event(&format!("{}_complete", self.name), Some(&serde_json::json!(props)));
        // Prevent Drop from running by forgetting self
        std::mem::forget(self);
    }
}

impl Drop for TelemetryContext {
    fn drop(&mut self) {
        // Auto-track on drop if not explicitly completed
        let telemetry = get_telemetry();
        let mut props = self.properties.clone();
        props.insert("duration_ms".to_string(), serde_json::json!(self.elapsed_ms()));
        props.insert("auto_completed".to_string(), serde_json::json!(true));
        telemetry.track_event(&format!("{}_complete", self.name), Some(&serde_json::json!(props)));
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_minimal_telemetry_creation() {
        let telemetry = MinimalTelemetry::new();
        assert!(telemetry.is_enabled());
        assert!(!telemetry.session_id().is_empty());
    }

    #[test]
    fn test_telemetry_enable_disable() {
        let mut telemetry = MinimalTelemetry::new();
        assert!(telemetry.is_enabled());

        telemetry.disable();
        assert!(!telemetry.is_enabled());

        telemetry.enable();
        assert!(telemetry.is_enabled());
    }

    #[test]
    fn test_telemetry_properties() {
        let mut telemetry = MinimalTelemetry::new();
        telemetry.set_property("key1", serde_json::json!("value1"));
        telemetry.set_property("key2", serde_json::json!(42));

        assert_eq!(
            telemetry.get_property("key1"),
            Some(&serde_json::json!("value1"))
        );
        assert_eq!(
            telemetry.get_property("key2"),
            Some(&serde_json::json!(42))
        );
        assert_eq!(telemetry.get_property("nonexistent"), None);
    }

    #[test]
    fn test_telemetry_user_id() {
        let mut telemetry = MinimalTelemetry::new();
        assert!(telemetry.user_id().is_none());

        telemetry.set_user_id("user123");
        assert_eq!(telemetry.user_id(), Some("user123"));
    }

    #[test]
    fn test_global_telemetry_functions() {
        // Test enable/disable
        enable_telemetry();
        assert!(is_telemetry_enabled());

        disable_telemetry();
        assert!(!is_telemetry_enabled());

        // Re-enable for other tests
        enable_telemetry();
    }

    #[test]
    fn test_performance_mode() {
        disable_performance_mode();
        assert!(!is_performance_mode());

        enable_performance_mode();
        assert!(is_performance_mode());

        disable_performance_mode();
        assert!(!is_performance_mode());
    }

    #[test]
    fn test_telemetry_context() {
        let context = TelemetryContext::new("test_operation")
            .property("key", serde_json::json!("value"));

        assert_eq!(context.name, "test_operation");
        std::thread::sleep(std::time::Duration::from_millis(10));
        assert!(context.elapsed_ms() >= 10);
    }

    #[test]
    fn test_get_telemetry() {
        let telemetry = get_telemetry();
        assert!(!telemetry.session_id().is_empty());
    }
}
