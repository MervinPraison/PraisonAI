//! Trace Module for PraisonAI Rust SDK.
//!
//! Provides tracing and observability for agent execution.
//!
//! # Example
//!
//! ```ignore
//! use praisonai::trace::{TraceContext, Span, SpanKind};
//!
//! let mut ctx = TraceContext::new("my-trace");
//! let span = ctx.start_span("agent-execution", SpanKind::Internal);
//! // ... do work ...
//! ctx.end_span(span);
//! ```

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::{Arc, RwLock};
use std::time::{Duration, Instant};

// =============================================================================
// SPAN KIND
// =============================================================================

/// Kind of span.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SpanKind {
    /// Internal operation
    Internal,
    /// LLM call
    Llm,
    /// Tool call
    Tool,
    /// Agent execution
    Agent,
    /// Workflow execution
    Workflow,
    /// Memory operation
    Memory,
    /// Network/API call
    Network,
    /// Custom
    Custom,
}

impl Default for SpanKind {
    fn default() -> Self {
        SpanKind::Internal
    }
}

// =============================================================================
// SPAN STATUS
// =============================================================================

/// Status of a span.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SpanStatus {
    /// Unset (default)
    Unset,
    /// Success
    Ok,
    /// Error
    Error,
}

impl Default for SpanStatus {
    fn default() -> Self {
        SpanStatus::Unset
    }
}

// =============================================================================
// SPAN
// =============================================================================

/// A span representing a unit of work.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Span {
    /// Span ID
    pub id: String,
    /// Parent span ID
    pub parent_id: Option<String>,
    /// Trace ID
    pub trace_id: String,
    /// Span name
    pub name: String,
    /// Span kind
    pub kind: SpanKind,
    /// Span status
    pub status: SpanStatus,
    /// Start time (as duration since trace start)
    pub start_offset: Duration,
    /// End time (as duration since trace start)
    pub end_offset: Option<Duration>,
    /// Duration
    pub duration: Option<Duration>,
    /// Attributes
    pub attributes: HashMap<String, serde_json::Value>,
    /// Events
    pub events: Vec<SpanEvent>,
    /// Error message (if status is Error)
    pub error_message: Option<String>,
}

impl Span {
    /// Create a new span.
    pub fn new(
        trace_id: impl Into<String>,
        name: impl Into<String>,
        kind: SpanKind,
        start_offset: Duration,
    ) -> Self {
        Self {
            id: uuid::Uuid::new_v4().to_string(),
            parent_id: None,
            trace_id: trace_id.into(),
            name: name.into(),
            kind,
            status: SpanStatus::Unset,
            start_offset,
            end_offset: None,
            duration: None,
            attributes: HashMap::new(),
            events: Vec::new(),
            error_message: None,
        }
    }

    /// Set parent span.
    pub fn with_parent(mut self, parent_id: impl Into<String>) -> Self {
        self.parent_id = Some(parent_id.into());
        self
    }

    /// Add an attribute.
    pub fn set_attribute(&mut self, key: impl Into<String>, value: impl Serialize) {
        self.attributes.insert(key.into(), serde_json::to_value(value).unwrap_or_default());
    }

    /// Add an event.
    pub fn add_event(&mut self, event: SpanEvent) {
        self.events.push(event);
    }

    /// End the span.
    pub fn end(&mut self, end_offset: Duration) {
        self.end_offset = Some(end_offset);
        self.duration = Some(end_offset.saturating_sub(self.start_offset));
        if self.status == SpanStatus::Unset {
            self.status = SpanStatus::Ok;
        }
    }

    /// Mark as error.
    pub fn set_error(&mut self, message: impl Into<String>) {
        self.status = SpanStatus::Error;
        self.error_message = Some(message.into());
    }

    /// Check if span is ended.
    pub fn is_ended(&self) -> bool {
        self.end_offset.is_some()
    }
}

// =============================================================================
// SPAN EVENT
// =============================================================================

/// An event within a span.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SpanEvent {
    /// Event name
    pub name: String,
    /// Timestamp (as duration since trace start)
    pub timestamp: Duration,
    /// Attributes
    pub attributes: HashMap<String, serde_json::Value>,
}

impl SpanEvent {
    /// Create a new event.
    pub fn new(name: impl Into<String>, timestamp: Duration) -> Self {
        Self {
            name: name.into(),
            timestamp,
            attributes: HashMap::new(),
        }
    }

    /// Add an attribute.
    pub fn with_attribute(mut self, key: impl Into<String>, value: impl Serialize) -> Self {
        self.attributes.insert(key.into(), serde_json::to_value(value).unwrap_or_default());
        self
    }
}

// =============================================================================
// TRACE CONTEXT
// =============================================================================

/// Context for a trace.
#[derive(Debug)]
pub struct TraceContext {
    /// Trace ID
    pub id: String,
    /// Trace name
    pub name: String,
    /// Start time
    start_time: Instant,
    /// All spans
    spans: Vec<Span>,
    /// Current span stack
    span_stack: Vec<String>,
    /// Attributes
    pub attributes: HashMap<String, serde_json::Value>,
}

impl TraceContext {
    /// Create a new trace context.
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            id: uuid::Uuid::new_v4().to_string(),
            name: name.into(),
            start_time: Instant::now(),
            spans: Vec::new(),
            span_stack: Vec::new(),
            attributes: HashMap::new(),
        }
    }

    /// Get elapsed time since trace start.
    pub fn elapsed(&self) -> Duration {
        self.start_time.elapsed()
    }

    /// Start a new span.
    pub fn start_span(&mut self, name: impl Into<String>, kind: SpanKind) -> String {
        let mut span = Span::new(&self.id, name, kind, self.elapsed());
        
        // Set parent if there's a current span
        if let Some(parent_id) = self.span_stack.last() {
            span = span.with_parent(parent_id);
        }

        let span_id = span.id.clone();
        self.spans.push(span);
        self.span_stack.push(span_id.clone());
        span_id
    }

    /// End a span.
    pub fn end_span(&mut self, span_id: &str) {
        let end_offset = self.elapsed();
        
        if let Some(span) = self.spans.iter_mut().find(|s| s.id == span_id) {
            span.end(end_offset);
        }

        // Remove from stack
        if let Some(pos) = self.span_stack.iter().position(|id| id == span_id) {
            self.span_stack.remove(pos);
        }
    }

    /// Get current span ID.
    pub fn current_span_id(&self) -> Option<&str> {
        self.span_stack.last().map(|s| s.as_str())
    }

    /// Get a span by ID.
    pub fn get_span(&self, span_id: &str) -> Option<&Span> {
        self.spans.iter().find(|s| s.id == span_id)
    }

    /// Get mutable span by ID.
    pub fn get_span_mut(&mut self, span_id: &str) -> Option<&mut Span> {
        self.spans.iter_mut().find(|s| s.id == span_id)
    }

    /// Add event to current span.
    pub fn add_event(&mut self, name: impl Into<String>) {
        if let Some(span_id) = self.current_span_id().map(|s| s.to_string()) {
            let event = SpanEvent::new(name, self.elapsed());
            if let Some(span) = self.get_span_mut(&span_id) {
                span.add_event(event);
            }
        }
    }

    /// Set attribute on current span.
    pub fn set_attribute(&mut self, key: impl Into<String>, value: impl Serialize) {
        if let Some(span_id) = self.current_span_id().map(|s| s.to_string()) {
            if let Some(span) = self.get_span_mut(&span_id) {
                span.set_attribute(key, value);
            }
        }
    }

    /// Get all spans.
    pub fn spans(&self) -> &[Span] {
        &self.spans
    }

    /// Get span count.
    pub fn span_count(&self) -> usize {
        self.spans.len()
    }

    /// Export to JSON.
    pub fn to_json(&self) -> serde_json::Value {
        serde_json::json!({
            "trace_id": self.id,
            "name": self.name,
            "spans": self.spans,
            "attributes": self.attributes
        })
    }
}

// =============================================================================
// TRACE EXPORTER
// =============================================================================

/// Trait for trace exporters.
pub trait TraceExporter: Send + Sync {
    /// Export a trace.
    fn export(&self, trace: &TraceContext) -> Result<(), Box<dyn std::error::Error>>;
}

/// Console exporter (prints to stdout).
#[derive(Debug, Default)]
pub struct ConsoleExporter;

impl TraceExporter for ConsoleExporter {
    fn export(&self, trace: &TraceContext) -> Result<(), Box<dyn std::error::Error>> {
        println!("=== Trace: {} ({}) ===", trace.name, trace.id);
        for span in &trace.spans {
            let status = match span.status {
                SpanStatus::Ok => "✓",
                SpanStatus::Error => "✗",
                SpanStatus::Unset => "?",
            };
            let duration = span.duration.map(|d| format!("{:.2}ms", d.as_secs_f64() * 1000.0))
                .unwrap_or_else(|| "ongoing".to_string());
            println!("  {} [{:?}] {} ({})", status, span.kind, span.name, duration);
        }
        Ok(())
    }
}

/// JSON file exporter.
#[derive(Debug)]
pub struct JsonFileExporter {
    path: std::path::PathBuf,
}

impl JsonFileExporter {
    /// Create a new JSON file exporter.
    pub fn new(path: impl Into<std::path::PathBuf>) -> Self {
        Self { path: path.into() }
    }
}

impl TraceExporter for JsonFileExporter {
    fn export(&self, trace: &TraceContext) -> Result<(), Box<dyn std::error::Error>> {
        let json = serde_json::to_string_pretty(&trace.to_json())?;
        std::fs::write(&self.path, json)?;
        Ok(())
    }
}

// =============================================================================
// GLOBAL TRACER
// =============================================================================

/// Global tracer for convenience.
#[derive(Default)]
pub struct Tracer {
    /// Active traces
    traces: Arc<RwLock<HashMap<String, TraceContext>>>,
    /// Exporters
    exporters: Arc<RwLock<Vec<Box<dyn TraceExporter>>>>,
}

impl std::fmt::Debug for Tracer {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Tracer")
            .field("traces", &self.traces)
            .field("exporters", &format!("<{} exporters>", self.exporters.read().unwrap().len()))
            .finish()
    }
}

impl Tracer {
    /// Create a new tracer.
    pub fn new() -> Self {
        Self::default()
    }

    /// Add an exporter.
    pub fn add_exporter(&self, exporter: impl TraceExporter + 'static) {
        self.exporters.write().unwrap().push(Box::new(exporter));
    }

    /// Start a new trace.
    pub fn start_trace(&self, name: impl Into<String>) -> String {
        let trace = TraceContext::new(name);
        let id = trace.id.clone();
        self.traces.write().unwrap().insert(id.clone(), trace);
        id
    }

    /// End a trace and export.
    pub fn end_trace(&self, trace_id: &str) {
        if let Some(trace) = self.traces.write().unwrap().remove(trace_id) {
            for exporter in self.exporters.read().unwrap().iter() {
                let _ = exporter.export(&trace);
            }
        }
    }

    /// Start a span in a trace.
    pub fn start_span(&self, trace_id: &str, name: impl Into<String>, kind: SpanKind) -> Option<String> {
        self.traces.write().unwrap().get_mut(trace_id).map(|t| t.start_span(name, kind))
    }

    /// End a span in a trace.
    pub fn end_span(&self, trace_id: &str, span_id: &str) {
        if let Some(trace) = self.traces.write().unwrap().get_mut(trace_id) {
            trace.end_span(span_id);
        }
    }

    /// Get trace count.
    pub fn trace_count(&self) -> usize {
        self.traces.read().unwrap().len()
    }
}

// =============================================================================
// TESTS
// =============================================================================

// =============================================================================
// CONTEXT EVENT TYPES (for replay)
// =============================================================================

/// Type of context event.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ContextEventType {
    /// Agent started
    AgentStart,
    /// Agent completed
    AgentEnd,
    /// Tool call started
    ToolStart,
    /// Tool call completed
    ToolEnd,
    /// LLM request started
    LlmStart,
    /// LLM response received
    LlmEnd,
    /// Memory operation
    MemoryOp,
    /// Workflow step
    WorkflowStep,
    /// Error occurred
    Error,
    /// Custom event
    Custom,
}

impl Default for ContextEventType {
    fn default() -> Self {
        Self::Custom
    }
}

/// A context event for replay/debugging.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContextEvent {
    /// Event type
    pub event_type: ContextEventType,
    /// Event name
    pub name: String,
    /// Timestamp (milliseconds since epoch)
    pub timestamp_ms: u64,
    /// Agent ID (if applicable)
    pub agent_id: Option<String>,
    /// Agent name (if applicable)
    pub agent_name: Option<String>,
    /// Tool name (if applicable)
    pub tool_name: Option<String>,
    /// Input data
    pub input: Option<serde_json::Value>,
    /// Output data
    pub output: Option<serde_json::Value>,
    /// Error message (if applicable)
    pub error: Option<String>,
    /// Duration in milliseconds (if applicable)
    pub duration_ms: Option<u64>,
    /// Additional metadata
    pub metadata: HashMap<String, serde_json::Value>,
}

impl ContextEvent {
    /// Create a new context event.
    pub fn new(event_type: ContextEventType, name: impl Into<String>) -> Self {
        use std::time::{SystemTime, UNIX_EPOCH};
        let timestamp_ms = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0);

        Self {
            event_type,
            name: name.into(),
            timestamp_ms,
            agent_id: None,
            agent_name: None,
            tool_name: None,
            input: None,
            output: None,
            error: None,
            duration_ms: None,
            metadata: HashMap::new(),
        }
    }

    /// Set agent info.
    pub fn agent(mut self, id: impl Into<String>, name: impl Into<String>) -> Self {
        self.agent_id = Some(id.into());
        self.agent_name = Some(name.into());
        self
    }

    /// Set tool name.
    pub fn tool(mut self, name: impl Into<String>) -> Self {
        self.tool_name = Some(name.into());
        self
    }

    /// Set input.
    pub fn input(mut self, input: serde_json::Value) -> Self {
        self.input = Some(input);
        self
    }

    /// Set output.
    pub fn output(mut self, output: serde_json::Value) -> Self {
        self.output = Some(output);
        self
    }

    /// Set error.
    pub fn error(mut self, error: impl Into<String>) -> Self {
        self.error = Some(error.into());
        self
    }

    /// Set duration.
    pub fn duration_ms(mut self, ms: u64) -> Self {
        self.duration_ms = Some(ms);
        self
    }

    /// Add metadata.
    pub fn metadata(mut self, key: impl Into<String>, value: serde_json::Value) -> Self {
        self.metadata.insert(key.into(), value);
        self
    }
}

/// Protocol trait for context trace sinks.
pub trait ContextTraceSinkProtocol: Send + Sync {
    /// Record a context event.
    fn record(&mut self, event: ContextEvent);
    
    /// Get all recorded events.
    fn events(&self) -> &[ContextEvent];
    
    /// Clear all events.
    fn clear(&mut self);
}

/// No-op sink (does nothing, zero overhead).
#[derive(Debug, Default)]
pub struct ContextNoOpSink;

impl ContextTraceSinkProtocol for ContextNoOpSink {
    fn record(&mut self, _event: ContextEvent) {}
    fn events(&self) -> &[ContextEvent] { &[] }
    fn clear(&mut self) {}
}

/// List sink (stores events in memory).
#[derive(Debug, Default)]
pub struct ContextListSink {
    events: Vec<ContextEvent>,
}

impl ContextListSink {
    /// Create a new list sink.
    pub fn new() -> Self {
        Self::default()
    }
}

impl ContextTraceSinkProtocol for ContextListSink {
    fn record(&mut self, event: ContextEvent) {
        self.events.push(event);
    }
    
    fn events(&self) -> &[ContextEvent] {
        &self.events
    }
    
    fn clear(&mut self) {
        self.events.clear();
    }
}

/// Context trace emitter.
pub struct ContextTraceEmitter {
    sink: Box<dyn ContextTraceSinkProtocol>,
}

impl std::fmt::Debug for ContextTraceEmitter {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("ContextTraceEmitter")
            .field("events_count", &self.sink.events().len())
            .finish()
    }
}

impl Default for ContextTraceEmitter {
    fn default() -> Self {
        Self {
            sink: Box::new(ContextNoOpSink),
        }
    }
}

impl ContextTraceEmitter {
    /// Create with a specific sink.
    pub fn new(sink: impl ContextTraceSinkProtocol + 'static) -> Self {
        Self {
            sink: Box::new(sink),
        }
    }

    /// Create with no-op sink (zero overhead).
    pub fn noop() -> Self {
        Self::default()
    }

    /// Create with list sink.
    pub fn with_list_sink() -> Self {
        Self::new(ContextListSink::new())
    }

    /// Emit an event.
    pub fn emit(&mut self, event: ContextEvent) {
        self.sink.record(event);
    }

    /// Get events.
    pub fn events(&self) -> &[ContextEvent] {
        self.sink.events()
    }

    /// Clear events.
    pub fn clear(&mut self) {
        self.sink.clear();
    }

    /// Emit agent start event.
    pub fn agent_start(&mut self, agent_id: &str, agent_name: &str, input: &str) {
        self.emit(
            ContextEvent::new(ContextEventType::AgentStart, "agent_start")
                .agent(agent_id, agent_name)
                .input(serde_json::json!(input))
        );
    }

    /// Emit agent end event.
    pub fn agent_end(&mut self, agent_id: &str, agent_name: &str, output: &str, duration_ms: u64) {
        self.emit(
            ContextEvent::new(ContextEventType::AgentEnd, "agent_end")
                .agent(agent_id, agent_name)
                .output(serde_json::json!(output))
                .duration_ms(duration_ms)
        );
    }

    /// Emit tool start event.
    pub fn tool_start(&mut self, tool_name: &str, args: serde_json::Value) {
        self.emit(
            ContextEvent::new(ContextEventType::ToolStart, "tool_start")
                .tool(tool_name)
                .input(args)
        );
    }

    /// Emit tool end event.
    pub fn tool_end(&mut self, tool_name: &str, result: serde_json::Value, duration_ms: u64) {
        self.emit(
            ContextEvent::new(ContextEventType::ToolEnd, "tool_end")
                .tool(tool_name)
                .output(result)
                .duration_ms(duration_ms)
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_span_new() {
        let span = Span::new("trace-1", "test-span", SpanKind::Internal, Duration::ZERO);
        assert_eq!(span.name, "test-span");
        assert_eq!(span.kind, SpanKind::Internal);
        assert!(!span.is_ended());
    }

    #[test]
    fn test_span_end() {
        let mut span = Span::new("trace-1", "test-span", SpanKind::Internal, Duration::ZERO);
        span.end(Duration::from_millis(100));
        
        assert!(span.is_ended());
        assert_eq!(span.status, SpanStatus::Ok);
        assert_eq!(span.duration, Some(Duration::from_millis(100)));
    }

    #[test]
    fn test_span_error() {
        let mut span = Span::new("trace-1", "test-span", SpanKind::Internal, Duration::ZERO);
        span.set_error("Something went wrong");
        
        assert_eq!(span.status, SpanStatus::Error);
        assert_eq!(span.error_message, Some("Something went wrong".to_string()));
    }

    #[test]
    fn test_span_attributes() {
        let mut span = Span::new("trace-1", "test-span", SpanKind::Internal, Duration::ZERO);
        span.set_attribute("key", "value");
        
        assert!(span.attributes.contains_key("key"));
    }

    #[test]
    fn test_trace_context() {
        let mut ctx = TraceContext::new("test-trace");
        
        let span_id = ctx.start_span("span-1", SpanKind::Agent);
        assert_eq!(ctx.span_count(), 1);
        assert_eq!(ctx.current_span_id(), Some(span_id.as_str()));
        
        ctx.end_span(&span_id);
        assert!(ctx.current_span_id().is_none());
    }

    #[test]
    fn test_trace_context_nested_spans() {
        let mut ctx = TraceContext::new("test-trace");
        
        let parent_id = ctx.start_span("parent", SpanKind::Workflow);
        let child_id = ctx.start_span("child", SpanKind::Agent);
        
        // Child should have parent
        let child = ctx.get_span(&child_id).unwrap();
        assert_eq!(child.parent_id, Some(parent_id.clone()));
        
        ctx.end_span(&child_id);
        ctx.end_span(&parent_id);
        
        assert_eq!(ctx.span_count(), 2);
    }

    #[test]
    fn test_span_event() {
        let event = SpanEvent::new("test-event", Duration::from_millis(50))
            .with_attribute("key", "value");
        
        assert_eq!(event.name, "test-event");
        assert!(event.attributes.contains_key("key"));
    }

    #[test]
    fn test_tracer() {
        let tracer = Tracer::new();
        
        let trace_id = tracer.start_trace("test");
        assert_eq!(tracer.trace_count(), 1);
        
        let span_id = tracer.start_span(&trace_id, "span-1", SpanKind::Internal);
        assert!(span_id.is_some());
        
        tracer.end_span(&trace_id, &span_id.unwrap());
        tracer.end_trace(&trace_id);
        
        assert_eq!(tracer.trace_count(), 0);
    }

    #[test]
    fn test_console_exporter() {
        let mut ctx = TraceContext::new("test-trace");
        let span_id = ctx.start_span("test-span", SpanKind::Internal);
        ctx.end_span(&span_id);
        
        let exporter = ConsoleExporter;
        assert!(exporter.export(&ctx).is_ok());
    }

    #[test]
    fn test_trace_to_json() {
        let mut ctx = TraceContext::new("test-trace");
        let span_id = ctx.start_span("test-span", SpanKind::Internal);
        ctx.end_span(&span_id);
        
        let json = ctx.to_json();
        assert!(json.get("trace_id").is_some());
        assert!(json.get("spans").is_some());
    }
}
