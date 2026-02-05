//! Streaming Module
//!
//! This module provides streaming event handling for LLM responses:
//! - `StreamEvent` - Streaming event representation
//! - `StreamEventType` - Types of streaming events
//! - `StreamMetrics` - Timing metrics for streaming
//! - `StreamCallback` - Callback trait for handling events
//!
//! # Example
//!
//! ```ignore
//! use praisonai::streaming::{StreamEvent, StreamEventType, StreamMetrics};
//!
//! let event = StreamEvent::new(StreamEventType::DeltaText)
//!     .content("Hello");
//!
//! let mut metrics = StreamMetrics::default();
//! metrics.update_from_event(&event);
//! ```

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::Instant;

// Note: Result is available for future async implementations

// =============================================================================
// STREAM EVENT TYPE
// =============================================================================

/// Types of streaming events emitted during LLM response streaming.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StreamEventType {
    /// Before API call is made
    RequestStart,
    /// When HTTP headers arrive
    HeadersReceived,
    /// First content delta received (TTFT marker)
    FirstToken,
    /// Text content delta
    DeltaText,
    /// Tool call delta
    DeltaToolCall,
    /// Tool call complete
    ToolCallEnd,
    /// Final content delta
    LastToken,
    /// Stream completed successfully
    StreamEnd,
    /// Error during streaming
    Error,
}

impl std::fmt::Display for StreamEventType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::RequestStart => write!(f, "request_start"),
            Self::HeadersReceived => write!(f, "headers_received"),
            Self::FirstToken => write!(f, "first_token"),
            Self::DeltaText => write!(f, "delta_text"),
            Self::DeltaToolCall => write!(f, "delta_tool_call"),
            Self::ToolCallEnd => write!(f, "tool_call_end"),
            Self::LastToken => write!(f, "last_token"),
            Self::StreamEnd => write!(f, "stream_end"),
            Self::Error => write!(f, "error"),
        }
    }
}

// =============================================================================
// TOOL CALL DATA
// =============================================================================

/// Tool call data for streaming events.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolCallData {
    /// Tool name
    pub name: String,
    /// Tool arguments (partial JSON)
    pub arguments: String,
    /// Tool call ID
    pub id: Option<String>,
    /// Index in the tool calls array
    pub index: Option<usize>,
}

impl ToolCallData {
    /// Create new tool call data
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            arguments: String::new(),
            id: None,
            index: None,
        }
    }

    /// Set arguments
    pub fn arguments(mut self, args: impl Into<String>) -> Self {
        self.arguments = args.into();
        self
    }

    /// Set ID
    pub fn id(mut self, id: impl Into<String>) -> Self {
        self.id = Some(id.into());
        self
    }
}

// =============================================================================
// STREAM EVENT
// =============================================================================

/// A single streaming event emitted during LLM response streaming.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StreamEvent {
    /// Event type
    pub event_type: StreamEventType,
    /// Timestamp (milliseconds since epoch)
    pub timestamp: u64,
    /// Text content for DeltaText events
    pub content: Option<String>,
    /// Tool call data for DeltaToolCall events
    pub tool_call: Option<ToolCallData>,
    /// Additional metadata
    pub metadata: HashMap<String, String>,
    /// Error message for Error events
    pub error: Option<String>,
    /// Whether this is reasoning/thinking content
    pub is_reasoning: bool,
    /// Agent ID for multi-agent scenarios
    pub agent_id: Option<String>,
    /// Session ID for tracking
    pub session_id: Option<String>,
    /// Run ID for correlation
    pub run_id: Option<String>,
}

impl StreamEvent {
    /// Create a new stream event
    pub fn new(event_type: StreamEventType) -> Self {
        Self {
            event_type,
            timestamp: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis() as u64,
            content: None,
            tool_call: None,
            metadata: HashMap::new(),
            error: None,
            is_reasoning: false,
            agent_id: None,
            session_id: None,
            run_id: None,
        }
    }

    /// Set content
    pub fn content(mut self, content: impl Into<String>) -> Self {
        self.content = Some(content.into());
        self
    }

    /// Set tool call
    pub fn tool_call(mut self, tool_call: ToolCallData) -> Self {
        self.tool_call = Some(tool_call);
        self
    }

    /// Set error
    pub fn error(mut self, error: impl Into<String>) -> Self {
        self.error = Some(error.into());
        self
    }

    /// Set as reasoning content
    pub fn reasoning(mut self, is_reasoning: bool) -> Self {
        self.is_reasoning = is_reasoning;
        self
    }

    /// Set agent ID
    pub fn agent_id(mut self, id: impl Into<String>) -> Self {
        self.agent_id = Some(id.into());
        self
    }

    /// Set session ID
    pub fn session_id(mut self, id: impl Into<String>) -> Self {
        self.session_id = Some(id.into());
        self
    }

    /// Set run ID
    pub fn run_id(mut self, id: impl Into<String>) -> Self {
        self.run_id = Some(id.into());
        self
    }

    /// Add metadata
    pub fn metadata(mut self, key: impl Into<String>, value: impl Into<String>) -> Self {
        self.metadata.insert(key.into(), value.into());
        self
    }

    /// Create a request start event
    pub fn request_start() -> Self {
        Self::new(StreamEventType::RequestStart)
    }

    /// Create a first token event
    pub fn first_token(content: impl Into<String>) -> Self {
        Self::new(StreamEventType::FirstToken).content(content)
    }

    /// Create a delta text event
    pub fn delta_text(content: impl Into<String>) -> Self {
        Self::new(StreamEventType::DeltaText).content(content)
    }

    /// Create a stream end event
    pub fn stream_end() -> Self {
        Self::new(StreamEventType::StreamEnd)
    }

    /// Create an error event
    pub fn error_event(message: impl Into<String>) -> Self {
        Self::new(StreamEventType::Error).error(message)
    }
}

// =============================================================================
// STREAM METRICS
// =============================================================================

/// Timing metrics for a streaming response.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct StreamMetrics {
    /// Request start time (ms)
    pub request_start: u64,
    /// Headers received time (ms)
    pub headers_received: u64,
    /// First token time (ms)
    pub first_token: u64,
    /// Last token time (ms)
    pub last_token: u64,
    /// Stream end time (ms)
    pub stream_end: u64,
    /// Token count
    pub token_count: usize,
    /// Internal start instant for precise timing
    #[serde(skip)]
    start_instant: Option<Instant>,
}

impl StreamMetrics {
    /// Create new metrics
    pub fn new() -> Self {
        Self {
            start_instant: Some(Instant::now()),
            ..Default::default()
        }
    }

    /// Time To First Token in milliseconds
    pub fn ttft_ms(&self) -> u64 {
        if self.first_token > 0 && self.request_start > 0 {
            self.first_token - self.request_start
        } else {
            0
        }
    }

    /// Stream duration in milliseconds
    pub fn stream_duration_ms(&self) -> u64 {
        if self.last_token > 0 && self.first_token > 0 {
            self.last_token - self.first_token
        } else {
            0
        }
    }

    /// Total time in milliseconds
    pub fn total_time_ms(&self) -> u64 {
        if self.stream_end > 0 && self.request_start > 0 {
            self.stream_end - self.request_start
        } else {
            0
        }
    }

    /// Tokens per second
    pub fn tokens_per_second(&self) -> f64 {
        let duration_ms = self.stream_duration_ms();
        if duration_ms > 0 && self.token_count > 0 {
            (self.token_count as f64 * 1000.0) / duration_ms as f64
        } else {
            0.0
        }
    }

    /// Update metrics from a stream event
    pub fn update_from_event(&mut self, event: &StreamEvent) {
        match event.event_type {
            StreamEventType::RequestStart => {
                self.request_start = event.timestamp;
            }
            StreamEventType::HeadersReceived => {
                self.headers_received = event.timestamp;
            }
            StreamEventType::FirstToken => {
                self.first_token = event.timestamp;
                self.token_count = 1;
            }
            StreamEventType::DeltaText => {
                self.token_count += 1;
            }
            StreamEventType::LastToken => {
                self.last_token = event.timestamp;
            }
            StreamEventType::StreamEnd => {
                self.stream_end = event.timestamp;
            }
            _ => {}
        }
    }

    /// Mark request start
    pub fn mark_request_start(&mut self) {
        self.request_start = Self::now_ms();
        self.start_instant = Some(Instant::now());
    }

    /// Mark first token
    pub fn mark_first_token(&mut self) {
        self.first_token = Self::now_ms();
        self.token_count = 1;
    }

    /// Mark last token
    pub fn mark_last_token(&mut self) {
        self.last_token = Self::now_ms();
    }

    /// Mark stream end
    pub fn mark_stream_end(&mut self) {
        self.stream_end = Self::now_ms();
    }

    /// Increment token count
    pub fn increment_tokens(&mut self) {
        self.token_count += 1;
    }

    fn now_ms() -> u64 {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis() as u64
    }
}

// =============================================================================
// STREAM CALLBACK
// =============================================================================

/// Trait for synchronous stream event callbacks.
pub trait StreamCallback: Send + Sync {
    /// Called when a stream event is emitted
    fn on_event(&self, event: &StreamEvent);
}

/// Trait for asynchronous stream event callbacks.
#[async_trait]
pub trait AsyncStreamCallback: Send + Sync {
    /// Called when a stream event is emitted (async)
    async fn on_event(&self, event: &StreamEvent);
}

// =============================================================================
// STREAM HANDLER
// =============================================================================

/// Handler for managing stream callbacks.
#[derive(Default)]
pub struct StreamHandler {
    callbacks: Vec<Box<dyn StreamCallback>>,
}

impl StreamHandler {
    /// Create a new stream handler
    pub fn new() -> Self {
        Self::default()
    }

    /// Add a callback
    pub fn add_callback(&mut self, callback: impl StreamCallback + 'static) {
        self.callbacks.push(Box::new(callback));
    }

    /// Emit an event to all callbacks
    pub fn emit(&self, event: &StreamEvent) {
        for callback in &self.callbacks {
            callback.on_event(event);
        }
    }

    /// Get callback count
    pub fn callback_count(&self) -> usize {
        self.callbacks.len()
    }
}

// =============================================================================
// STREAM COLLECTOR
// =============================================================================

/// Collects stream events and accumulated content.
#[derive(Debug, Default)]
pub struct StreamCollector {
    /// Collected events
    pub events: Vec<StreamEvent>,
    /// Accumulated content
    pub content: String,
    /// Metrics
    pub metrics: StreamMetrics,
}

impl StreamCollector {
    /// Create a new collector
    pub fn new() -> Self {
        Self {
            metrics: StreamMetrics::new(),
            ..Default::default()
        }
    }

    /// Process an event
    pub fn process(&mut self, event: StreamEvent) {
        // Update metrics
        self.metrics.update_from_event(&event);

        // Accumulate content
        if let Some(content) = &event.content {
            self.content.push_str(content);
        }

        // Store event
        self.events.push(event);
    }

    /// Get final content
    pub fn get_content(&self) -> &str {
        &self.content
    }

    /// Get event count
    pub fn event_count(&self) -> usize {
        self.events.len()
    }

    /// Check if streaming completed successfully
    pub fn is_complete(&self) -> bool {
        self.events
            .iter()
            .any(|e| e.event_type == StreamEventType::StreamEnd)
    }

    /// Check if there was an error
    pub fn has_error(&self) -> bool {
        self.events
            .iter()
            .any(|e| e.event_type == StreamEventType::Error)
    }

    /// Get error message if any
    pub fn get_error(&self) -> Option<&str> {
        self.events
            .iter()
            .find(|e| e.event_type == StreamEventType::Error)
            .and_then(|e| e.error.as_deref())
    }
}

impl StreamCallback for StreamCollector {
    fn on_event(&self, _event: &StreamEvent) {
        // Note: This is a read-only callback for the trait
        // Use process() method for mutable operations
    }
}

// =============================================================================
// TESTS
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_stream_event_type_display() {
        assert_eq!(StreamEventType::RequestStart.to_string(), "request_start");
        assert_eq!(StreamEventType::DeltaText.to_string(), "delta_text");
        assert_eq!(StreamEventType::StreamEnd.to_string(), "stream_end");
    }

    #[test]
    fn test_stream_event_creation() {
        let event = StreamEvent::new(StreamEventType::DeltaText)
            .content("Hello")
            .agent_id("agent-1")
            .session_id("session-1");

        assert_eq!(event.event_type, StreamEventType::DeltaText);
        assert_eq!(event.content, Some("Hello".to_string()));
        assert_eq!(event.agent_id, Some("agent-1".to_string()));
        assert_eq!(event.session_id, Some("session-1".to_string()));
    }

    #[test]
    fn test_stream_event_helpers() {
        let start = StreamEvent::request_start();
        assert_eq!(start.event_type, StreamEventType::RequestStart);

        let delta = StreamEvent::delta_text("content");
        assert_eq!(delta.event_type, StreamEventType::DeltaText);
        assert_eq!(delta.content, Some("content".to_string()));

        let end = StreamEvent::stream_end();
        assert_eq!(end.event_type, StreamEventType::StreamEnd);

        let error = StreamEvent::error_event("Something went wrong");
        assert_eq!(error.event_type, StreamEventType::Error);
        assert_eq!(error.error, Some("Something went wrong".to_string()));
    }

    #[test]
    fn test_tool_call_data() {
        let tool_call = ToolCallData::new("search")
            .arguments(r#"{"query": "test"}"#)
            .id("call-123");

        assert_eq!(tool_call.name, "search");
        assert_eq!(tool_call.arguments, r#"{"query": "test"}"#);
        assert_eq!(tool_call.id, Some("call-123".to_string()));
    }

    #[test]
    fn test_stream_metrics() {
        let mut metrics = StreamMetrics::new();

        // Simulate events
        let start = StreamEvent::new(StreamEventType::RequestStart);
        metrics.update_from_event(&start);

        let first = StreamEvent::new(StreamEventType::FirstToken);
        metrics.update_from_event(&first);

        for _ in 0..10 {
            let delta = StreamEvent::new(StreamEventType::DeltaText);
            metrics.update_from_event(&delta);
        }

        let last = StreamEvent::new(StreamEventType::LastToken);
        metrics.update_from_event(&last);

        let end = StreamEvent::new(StreamEventType::StreamEnd);
        metrics.update_from_event(&end);

        assert_eq!(metrics.token_count, 11); // 1 first + 10 deltas
        assert!(metrics.request_start > 0);
        assert!(metrics.stream_end > 0);
    }

    #[test]
    fn test_stream_collector() {
        let mut collector = StreamCollector::new();

        collector.process(StreamEvent::request_start());
        collector.process(StreamEvent::first_token("Hello"));
        collector.process(StreamEvent::delta_text(" "));
        collector.process(StreamEvent::delta_text("World"));
        collector.process(StreamEvent::stream_end());

        assert_eq!(collector.get_content(), "Hello World");
        assert_eq!(collector.event_count(), 5);
        assert!(collector.is_complete());
        assert!(!collector.has_error());
    }

    #[test]
    fn test_stream_collector_with_error() {
        let mut collector = StreamCollector::new();

        collector.process(StreamEvent::request_start());
        collector.process(StreamEvent::error_event("Connection failed"));

        assert!(collector.has_error());
        assert_eq!(collector.get_error(), Some("Connection failed"));
        assert!(!collector.is_complete());
    }

    #[test]
    fn test_stream_handler() {
        struct TestCallback {
            count: std::sync::atomic::AtomicUsize,
        }

        impl StreamCallback for TestCallback {
            fn on_event(&self, _event: &StreamEvent) {
                self.count.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
            }
        }

        let mut handler = StreamHandler::new();
        let callback = TestCallback {
            count: std::sync::atomic::AtomicUsize::new(0),
        };

        // We need to use Arc for shared ownership
        use std::sync::Arc;
        let callback = Arc::new(callback);

        struct ArcCallback(Arc<TestCallback>);
        impl StreamCallback for ArcCallback {
            fn on_event(&self, event: &StreamEvent) {
                self.0.on_event(event);
            }
        }

        handler.add_callback(ArcCallback(callback.clone()));

        handler.emit(&StreamEvent::request_start());
        handler.emit(&StreamEvent::delta_text("test"));
        handler.emit(&StreamEvent::stream_end());

        assert_eq!(callback.count.load(std::sync::atomic::Ordering::SeqCst), 3);
    }

    #[test]
    fn test_metrics_calculations() {
        let mut metrics = StreamMetrics::default();
        metrics.request_start = 1000;
        metrics.first_token = 1100;
        metrics.last_token = 2000;
        metrics.stream_end = 2100;
        metrics.token_count = 100;

        assert_eq!(metrics.ttft_ms(), 100);
        assert_eq!(metrics.stream_duration_ms(), 900);
        assert_eq!(metrics.total_time_ms(), 1100);
        assert!((metrics.tokens_per_second() - 111.11).abs() < 1.0);
    }
}
