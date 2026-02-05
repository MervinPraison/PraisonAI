//! Telemetry Module for PraisonAI Rust SDK.
//!
//! Provides performance monitoring and telemetry capabilities.
//!
//! # Example
//!
//! ```ignore
//! use praisonai::telemetry::{PerformanceMonitor, FunctionStats};
//!
//! let monitor = PerformanceMonitor::new();
//! monitor.track_function("my_function", Duration::from_millis(100));
//! let stats = monitor.get_stats("my_function");
//! ```

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::{Arc, RwLock};
use std::time::{Duration, Instant};

// =============================================================================
// FUNCTION STATS
// =============================================================================

/// Statistics for a tracked function.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FunctionStats {
    /// Function name
    pub name: String,
    /// Number of calls
    pub call_count: usize,
    /// Total duration
    pub total_duration: Duration,
    /// Minimum duration
    pub min_duration: Duration,
    /// Maximum duration
    pub max_duration: Duration,
    /// Last call duration
    pub last_duration: Duration,
}

impl FunctionStats {
    /// Create new stats for a function.
    pub fn new(name: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            call_count: 0,
            total_duration: Duration::ZERO,
            min_duration: Duration::MAX,
            max_duration: Duration::ZERO,
            last_duration: Duration::ZERO,
        }
    }

    /// Record a call.
    pub fn record(&mut self, duration: Duration) {
        self.call_count += 1;
        self.total_duration += duration;
        self.last_duration = duration;
        
        if duration < self.min_duration {
            self.min_duration = duration;
        }
        if duration > self.max_duration {
            self.max_duration = duration;
        }
    }

    /// Get average duration.
    pub fn average_duration(&self) -> Duration {
        if self.call_count == 0 {
            Duration::ZERO
        } else {
            self.total_duration / self.call_count as u32
        }
    }

    /// Get calls per second.
    pub fn calls_per_second(&self, elapsed: Duration) -> f64 {
        if elapsed.as_secs_f64() == 0.0 {
            0.0
        } else {
            self.call_count as f64 / elapsed.as_secs_f64()
        }
    }
}

// =============================================================================
// API STATS
// =============================================================================

/// Statistics for API calls.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApiStats {
    /// Endpoint
    pub endpoint: String,
    /// Number of calls
    pub call_count: usize,
    /// Successful calls
    pub success_count: usize,
    /// Failed calls
    pub error_count: usize,
    /// Total duration
    pub total_duration: Duration,
    /// Status code counts
    pub status_codes: HashMap<u16, usize>,
}

impl ApiStats {
    /// Create new API stats.
    pub fn new(endpoint: impl Into<String>) -> Self {
        Self {
            endpoint: endpoint.into(),
            call_count: 0,
            success_count: 0,
            error_count: 0,
            total_duration: Duration::ZERO,
            status_codes: HashMap::new(),
        }
    }

    /// Record a successful call.
    pub fn record_success(&mut self, duration: Duration, status_code: u16) {
        self.call_count += 1;
        self.success_count += 1;
        self.total_duration += duration;
        *self.status_codes.entry(status_code).or_insert(0) += 1;
    }

    /// Record a failed call.
    pub fn record_error(&mut self, duration: Duration, status_code: Option<u16>) {
        self.call_count += 1;
        self.error_count += 1;
        self.total_duration += duration;
        if let Some(code) = status_code {
            *self.status_codes.entry(code).or_insert(0) += 1;
        }
    }

    /// Get success rate.
    pub fn success_rate(&self) -> f64 {
        if self.call_count == 0 {
            1.0
        } else {
            self.success_count as f64 / self.call_count as f64
        }
    }

    /// Get average duration.
    pub fn average_duration(&self) -> Duration {
        if self.call_count == 0 {
            Duration::ZERO
        } else {
            self.total_duration / self.call_count as u32
        }
    }
}

// =============================================================================
// PERFORMANCE MONITOR
// =============================================================================

/// Performance monitor for tracking function and API performance.
#[derive(Debug)]
pub struct PerformanceMonitor {
    /// Function statistics
    functions: Arc<RwLock<HashMap<String, FunctionStats>>>,
    /// API statistics
    apis: Arc<RwLock<HashMap<String, ApiStats>>>,
    /// Start time
    start_time: Instant,
    /// Whether monitoring is enabled
    enabled: bool,
}

impl Default for PerformanceMonitor {
    fn default() -> Self {
        Self::new()
    }
}

impl PerformanceMonitor {
    /// Create a new monitor.
    pub fn new() -> Self {
        Self {
            functions: Arc::new(RwLock::new(HashMap::new())),
            apis: Arc::new(RwLock::new(HashMap::new())),
            start_time: Instant::now(),
            enabled: true,
        }
    }

    /// Enable monitoring.
    pub fn enable(&mut self) {
        self.enabled = true;
    }

    /// Disable monitoring.
    pub fn disable(&mut self) {
        self.enabled = false;
    }

    /// Check if enabled.
    pub fn is_enabled(&self) -> bool {
        self.enabled
    }

    /// Track a function call.
    pub fn track_function(&self, name: &str, duration: Duration) {
        if !self.enabled {
            return;
        }

        let mut functions = self.functions.write().unwrap();
        functions
            .entry(name.to_string())
            .or_insert_with(|| FunctionStats::new(name))
            .record(duration);
    }

    /// Track an API call.
    pub fn track_api(&self, endpoint: &str, duration: Duration, success: bool, status_code: Option<u16>) {
        if !self.enabled {
            return;
        }

        let mut apis = self.apis.write().unwrap();
        let stats = apis
            .entry(endpoint.to_string())
            .or_insert_with(|| ApiStats::new(endpoint));

        if success {
            stats.record_success(duration, status_code.unwrap_or(200));
        } else {
            stats.record_error(duration, status_code);
        }
    }

    /// Get function stats.
    pub fn get_function_stats(&self, name: &str) -> Option<FunctionStats> {
        self.functions.read().unwrap().get(name).cloned()
    }

    /// Get API stats.
    pub fn get_api_stats(&self, endpoint: &str) -> Option<ApiStats> {
        self.apis.read().unwrap().get(endpoint).cloned()
    }

    /// Get all function stats.
    pub fn all_function_stats(&self) -> Vec<FunctionStats> {
        self.functions.read().unwrap().values().cloned().collect()
    }

    /// Get all API stats.
    pub fn all_api_stats(&self) -> Vec<ApiStats> {
        self.apis.read().unwrap().values().cloned().collect()
    }

    /// Get slowest functions.
    pub fn slowest_functions(&self, limit: usize) -> Vec<FunctionStats> {
        let mut stats: Vec<_> = self.all_function_stats();
        stats.sort_by(|a, b| b.average_duration().cmp(&a.average_duration()));
        stats.truncate(limit);
        stats
    }

    /// Get slowest APIs.
    pub fn slowest_apis(&self, limit: usize) -> Vec<ApiStats> {
        let mut stats: Vec<_> = self.all_api_stats();
        stats.sort_by(|a, b| b.average_duration().cmp(&a.average_duration()));
        stats.truncate(limit);
        stats
    }

    /// Get elapsed time since start.
    pub fn elapsed(&self) -> Duration {
        self.start_time.elapsed()
    }

    /// Clear all data.
    pub fn clear(&self) {
        self.functions.write().unwrap().clear();
        self.apis.write().unwrap().clear();
    }

    /// Get performance report.
    pub fn get_report(&self) -> PerformanceReport {
        PerformanceReport {
            elapsed: self.elapsed(),
            function_count: self.functions.read().unwrap().len(),
            api_count: self.apis.read().unwrap().len(),
            total_function_calls: self.functions.read().unwrap().values().map(|s| s.call_count).sum(),
            total_api_calls: self.apis.read().unwrap().values().map(|s| s.call_count).sum(),
            slowest_functions: self.slowest_functions(5),
            slowest_apis: self.slowest_apis(5),
        }
    }
}

/// Performance report.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PerformanceReport {
    /// Elapsed time
    pub elapsed: Duration,
    /// Number of tracked functions
    pub function_count: usize,
    /// Number of tracked APIs
    pub api_count: usize,
    /// Total function calls
    pub total_function_calls: usize,
    /// Total API calls
    pub total_api_calls: usize,
    /// Slowest functions
    pub slowest_functions: Vec<FunctionStats>,
    /// Slowest APIs
    pub slowest_apis: Vec<ApiStats>,
}

// =============================================================================
// TELEMETRY COLLECTOR
// =============================================================================

/// Event types for telemetry.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TelemetryEventType {
    AgentStart,
    AgentEnd,
    ToolCall,
    LlmRequest,
    LlmResponse,
    Error,
    Custom(String),
}

/// A telemetry event.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TelemetryEvent {
    /// Event type
    pub event_type: TelemetryEventType,
    /// Timestamp
    pub timestamp: chrono::DateTime<chrono::Utc>,
    /// Event data
    pub data: HashMap<String, serde_json::Value>,
    /// Duration (if applicable)
    pub duration: Option<Duration>,
}

impl TelemetryEvent {
    /// Create a new event.
    pub fn new(event_type: TelemetryEventType) -> Self {
        Self {
            event_type,
            timestamp: chrono::Utc::now(),
            data: HashMap::new(),
            duration: None,
        }
    }

    /// Add data.
    pub fn with_data(mut self, key: impl Into<String>, value: impl Serialize) -> Self {
        self.data.insert(key.into(), serde_json::to_value(value).unwrap_or_default());
        self
    }

    /// Set duration.
    pub fn with_duration(mut self, duration: Duration) -> Self {
        self.duration = Some(duration);
        self
    }
}

/// Telemetry collector.
#[derive(Debug, Default)]
pub struct TelemetryCollector {
    /// Collected events
    events: Arc<RwLock<Vec<TelemetryEvent>>>,
    /// Whether collection is enabled
    enabled: bool,
    /// Maximum events to keep
    max_events: usize,
}

impl TelemetryCollector {
    /// Create a new collector.
    pub fn new() -> Self {
        Self {
            events: Arc::new(RwLock::new(Vec::new())),
            enabled: true,
            max_events: 10000,
        }
    }

    /// Set max events.
    pub fn with_max_events(mut self, max: usize) -> Self {
        self.max_events = max;
        self
    }

    /// Enable collection.
    pub fn enable(&mut self) {
        self.enabled = true;
    }

    /// Disable collection.
    pub fn disable(&mut self) {
        self.enabled = false;
    }

    /// Record an event.
    pub fn record(&self, event: TelemetryEvent) {
        if !self.enabled {
            return;
        }

        let mut events = self.events.write().unwrap();
        events.push(event);

        // Trim if over limit
        if events.len() > self.max_events {
            let excess = events.len() - self.max_events;
            events.drain(0..excess);
        }
    }

    /// Get all events.
    pub fn events(&self) -> Vec<TelemetryEvent> {
        self.events.read().unwrap().clone()
    }

    /// Get events by type.
    pub fn events_by_type(&self, event_type: &TelemetryEventType) -> Vec<TelemetryEvent> {
        self.events
            .read()
            .unwrap()
            .iter()
            .filter(|e| std::mem::discriminant(&e.event_type) == std::mem::discriminant(event_type))
            .cloned()
            .collect()
    }

    /// Get event count.
    pub fn event_count(&self) -> usize {
        self.events.read().unwrap().len()
    }

    /// Clear all events.
    pub fn clear(&self) {
        self.events.write().unwrap().clear();
    }
}

// =============================================================================
// GLOBAL INSTANCES
// =============================================================================

use std::sync::OnceLock;

static GLOBAL_MONITOR: OnceLock<PerformanceMonitor> = OnceLock::new();
static GLOBAL_COLLECTOR: OnceLock<TelemetryCollector> = OnceLock::new();

/// Get the global performance monitor.
pub fn get_monitor() -> &'static PerformanceMonitor {
    GLOBAL_MONITOR.get_or_init(PerformanceMonitor::new)
}

/// Get the global telemetry collector.
pub fn get_collector() -> &'static TelemetryCollector {
    GLOBAL_COLLECTOR.get_or_init(TelemetryCollector::new)
}

/// Track a function call on the global monitor.
pub fn track_function(name: &str, duration: Duration) {
    get_monitor().track_function(name, duration);
}

/// Track an API call on the global monitor.
pub fn track_api(endpoint: &str, duration: Duration, success: bool, status_code: Option<u16>) {
    get_monitor().track_api(endpoint, duration, success, status_code);
}

/// Record a telemetry event.
pub fn record_event(event: TelemetryEvent) {
    get_collector().record(event);
}

/// Get the global performance report.
pub fn get_performance_report() -> PerformanceReport {
    get_monitor().get_report()
}

// =============================================================================
// TESTS
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_function_stats() {
        let mut stats = FunctionStats::new("test");
        stats.record(Duration::from_millis(100));
        stats.record(Duration::from_millis(200));

        assert_eq!(stats.call_count, 2);
        assert_eq!(stats.min_duration, Duration::from_millis(100));
        assert_eq!(stats.max_duration, Duration::from_millis(200));
        assert_eq!(stats.average_duration(), Duration::from_millis(150));
    }

    #[test]
    fn test_api_stats() {
        let mut stats = ApiStats::new("/api/test");
        stats.record_success(Duration::from_millis(100), 200);
        stats.record_success(Duration::from_millis(150), 200);
        stats.record_error(Duration::from_millis(50), Some(500));

        assert_eq!(stats.call_count, 3);
        assert_eq!(stats.success_count, 2);
        assert_eq!(stats.error_count, 1);
        assert!((stats.success_rate() - 0.666).abs() < 0.01);
    }

    #[test]
    fn test_performance_monitor() {
        let monitor = PerformanceMonitor::new();
        
        monitor.track_function("func1", Duration::from_millis(100));
        monitor.track_function("func1", Duration::from_millis(200));
        monitor.track_function("func2", Duration::from_millis(50));

        let stats = monitor.get_function_stats("func1").unwrap();
        assert_eq!(stats.call_count, 2);

        let slowest = monitor.slowest_functions(1);
        assert_eq!(slowest.len(), 1);
        assert_eq!(slowest[0].name, "func1");
    }

    #[test]
    fn test_performance_monitor_disabled() {
        let mut monitor = PerformanceMonitor::new();
        monitor.disable();
        
        monitor.track_function("func1", Duration::from_millis(100));
        
        assert!(monitor.get_function_stats("func1").is_none());
    }

    #[test]
    fn test_telemetry_event() {
        let event = TelemetryEvent::new(TelemetryEventType::AgentStart)
            .with_data("agent_name", "test-agent")
            .with_duration(Duration::from_secs(1));

        assert!(event.data.contains_key("agent_name"));
        assert_eq!(event.duration, Some(Duration::from_secs(1)));
    }

    #[test]
    fn test_telemetry_collector() {
        let collector = TelemetryCollector::new();
        
        collector.record(TelemetryEvent::new(TelemetryEventType::AgentStart));
        collector.record(TelemetryEvent::new(TelemetryEventType::ToolCall));
        
        assert_eq!(collector.event_count(), 2);
        
        let agent_events = collector.events_by_type(&TelemetryEventType::AgentStart);
        assert_eq!(agent_events.len(), 1);
    }

    #[test]
    fn test_telemetry_collector_max_events() {
        let collector = TelemetryCollector::new().with_max_events(5);
        
        for _ in 0..10 {
            collector.record(TelemetryEvent::new(TelemetryEventType::ToolCall));
        }
        
        assert_eq!(collector.event_count(), 5);
    }

    #[test]
    fn test_performance_report() {
        let monitor = PerformanceMonitor::new();
        monitor.track_function("func1", Duration::from_millis(100));
        monitor.track_api("/api/test", Duration::from_millis(200), true, Some(200));
        
        let report = monitor.get_report();
        assert_eq!(report.function_count, 1);
        assert_eq!(report.api_count, 1);
        assert_eq!(report.total_function_calls, 1);
        assert_eq!(report.total_api_calls, 1);
    }
}
