//! Event Bus Module for PraisonAI Agents.
//!
//! Provides a publish-subscribe event system for agent communication.
//!
//! # Features
//!
//! - Type-safe event publishing and subscription
//! - Async event handlers
//! - Multi-agent event isolation
//! - Event filtering and routing
//!
//! # Example
//!
//! ```ignore
//! use praisonai::{EventBus, Event, EventType};
//!
//! let bus = EventBus::new();
//! bus.subscribe(EventType::AgentStart, |event| {
//!     println!("Agent started: {:?}", event);
//! });
//! bus.publish(Event::agent_start("my_agent"));
//! ```

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::{Arc, RwLock};

// =============================================================================
// EVENT TYPE
// =============================================================================

/// Types of events that can be published.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EventType {
    /// Agent lifecycle events
    AgentStart,
    AgentEnd,
    AgentError,
    /// Tool events
    ToolStart,
    ToolEnd,
    ToolError,
    /// LLM events
    LlmRequest,
    LlmResponse,
    LlmError,
    /// Memory events
    MemoryStore,
    MemoryRetrieve,
    MemoryClear,
    /// Workflow events
    WorkflowStart,
    WorkflowEnd,
    WorkflowStep,
    /// Handoff events
    HandoffStart,
    HandoffEnd,
    /// Session events
    SessionCreate,
    SessionLoad,
    SessionSave,
    /// Custom event
    Custom,
}

// =============================================================================
// EVENT
// =============================================================================

/// An event in the event bus.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Event {
    /// Event type
    pub event_type: EventType,
    /// Source of the event (agent name, tool name, etc.)
    pub source: String,
    /// Event data
    pub data: serde_json::Value,
    /// Timestamp (Unix millis)
    pub timestamp: u64,
    /// Correlation ID for tracing
    pub correlation_id: Option<String>,
}

impl Event {
    /// Create a new event
    pub fn new(event_type: EventType, source: impl Into<String>) -> Self {
        Self {
            event_type,
            source: source.into(),
            data: serde_json::Value::Null,
            timestamp: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_millis() as u64)
                .unwrap_or(0),
            correlation_id: None,
        }
    }

    /// Set event data
    pub fn data(mut self, data: serde_json::Value) -> Self {
        self.data = data;
        self
    }

    /// Set correlation ID
    pub fn correlation_id(mut self, id: impl Into<String>) -> Self {
        self.correlation_id = Some(id.into());
        self
    }

    /// Create agent start event
    pub fn agent_start(agent_name: impl Into<String>) -> Self {
        Self::new(EventType::AgentStart, agent_name)
    }

    /// Create agent end event
    pub fn agent_end(agent_name: impl Into<String>) -> Self {
        Self::new(EventType::AgentEnd, agent_name)
    }

    /// Create agent error event
    pub fn agent_error(agent_name: impl Into<String>, error: impl Into<String>) -> Self {
        Self::new(EventType::AgentError, agent_name)
            .data(serde_json::json!({"error": error.into()}))
    }

    /// Create tool start event
    pub fn tool_start(tool_name: impl Into<String>) -> Self {
        Self::new(EventType::ToolStart, tool_name)
    }

    /// Create tool end event
    pub fn tool_end(tool_name: impl Into<String>) -> Self {
        Self::new(EventType::ToolEnd, tool_name)
    }

    /// Create tool error event
    pub fn tool_error(tool_name: impl Into<String>, error: impl Into<String>) -> Self {
        Self::new(EventType::ToolError, tool_name)
            .data(serde_json::json!({"error": error.into()}))
    }

    /// Create LLM request event
    pub fn llm_request(model: impl Into<String>) -> Self {
        Self::new(EventType::LlmRequest, model)
    }

    /// Create LLM response event
    pub fn llm_response(model: impl Into<String>) -> Self {
        Self::new(EventType::LlmResponse, model)
    }

    /// Create workflow start event
    pub fn workflow_start(workflow_name: impl Into<String>) -> Self {
        Self::new(EventType::WorkflowStart, workflow_name)
    }

    /// Create workflow end event
    pub fn workflow_end(workflow_name: impl Into<String>) -> Self {
        Self::new(EventType::WorkflowEnd, workflow_name)
    }

    /// Create handoff start event
    pub fn handoff_start(source: impl Into<String>, target: impl Into<String>) -> Self {
        Self::new(EventType::HandoffStart, source)
            .data(serde_json::json!({"target": target.into()}))
    }

    /// Create handoff end event
    pub fn handoff_end(source: impl Into<String>, target: impl Into<String>) -> Self {
        Self::new(EventType::HandoffEnd, source)
            .data(serde_json::json!({"target": target.into()}))
    }

    /// Create custom event
    pub fn custom(source: impl Into<String>, data: serde_json::Value) -> Self {
        Self::new(EventType::Custom, source).data(data)
    }
}

// =============================================================================
// EVENT HANDLER
// =============================================================================

/// Type alias for event handler function
pub type EventHandler = Arc<dyn Fn(&Event) + Send + Sync>;

/// Subscription to an event type
struct Subscription {
    id: usize,
    handler: EventHandler,
}

// =============================================================================
// EVENT BUS
// =============================================================================

/// Event bus for publish-subscribe messaging.
pub struct EventBus {
    /// Subscriptions by event type
    subscriptions: RwLock<HashMap<EventType, Vec<Subscription>>>,
    /// Global subscriptions (receive all events)
    global_subscriptions: RwLock<Vec<Subscription>>,
    /// Next subscription ID
    next_id: RwLock<usize>,
    /// Event history (optional)
    history: RwLock<Vec<Event>>,
    /// Max history size
    max_history: usize,
}

impl Default for EventBus {
    fn default() -> Self {
        Self::new()
    }
}

impl EventBus {
    /// Create a new event bus
    pub fn new() -> Self {
        Self {
            subscriptions: RwLock::new(HashMap::new()),
            global_subscriptions: RwLock::new(Vec::new()),
            next_id: RwLock::new(0),
            history: RwLock::new(Vec::new()),
            max_history: 1000,
        }
    }

    /// Create with custom history size
    pub fn with_history(max_history: usize) -> Self {
        Self {
            max_history,
            ..Self::new()
        }
    }

    /// Subscribe to a specific event type
    pub fn subscribe<F>(&self, event_type: EventType, handler: F) -> usize
    where
        F: Fn(&Event) + Send + Sync + 'static,
    {
        let id = {
            let mut next_id = self.next_id.write().unwrap();
            let id = *next_id;
            *next_id += 1;
            id
        };

        let subscription = Subscription {
            id,
            handler: Arc::new(handler),
        };

        self.subscriptions
            .write()
            .unwrap()
            .entry(event_type)
            .or_default()
            .push(subscription);

        id
    }

    /// Subscribe to all events
    pub fn subscribe_all<F>(&self, handler: F) -> usize
    where
        F: Fn(&Event) + Send + Sync + 'static,
    {
        let id = {
            let mut next_id = self.next_id.write().unwrap();
            let id = *next_id;
            *next_id += 1;
            id
        };

        let subscription = Subscription {
            id,
            handler: Arc::new(handler),
        };

        self.global_subscriptions.write().unwrap().push(subscription);

        id
    }

    /// Unsubscribe by ID
    pub fn unsubscribe(&self, subscription_id: usize) -> bool {
        // Check type-specific subscriptions
        let mut subs = self.subscriptions.write().unwrap();
        for handlers in subs.values_mut() {
            if let Some(pos) = handlers.iter().position(|s| s.id == subscription_id) {
                handlers.remove(pos);
                return true;
            }
        }

        // Check global subscriptions
        let mut global = self.global_subscriptions.write().unwrap();
        if let Some(pos) = global.iter().position(|s| s.id == subscription_id) {
            global.remove(pos);
            return true;
        }

        false
    }

    /// Publish an event
    pub fn publish(&self, event: Event) {
        // Store in history
        {
            let mut history = self.history.write().unwrap();
            history.push(event.clone());
            if history.len() > self.max_history {
                history.remove(0);
            }
        }

        // Notify type-specific subscribers
        if let Some(handlers) = self.subscriptions.read().unwrap().get(&event.event_type) {
            for subscription in handlers {
                (subscription.handler)(&event);
            }
        }

        // Notify global subscribers
        for subscription in self.global_subscriptions.read().unwrap().iter() {
            (subscription.handler)(&event);
        }
    }

    /// Get event history
    pub fn history(&self) -> Vec<Event> {
        self.history.read().unwrap().clone()
    }

    /// Get events by type
    pub fn events_by_type(&self, event_type: EventType) -> Vec<Event> {
        self.history
            .read()
            .unwrap()
            .iter()
            .filter(|e| e.event_type == event_type)
            .cloned()
            .collect()
    }

    /// Get events by source
    pub fn events_by_source(&self, source: &str) -> Vec<Event> {
        self.history
            .read()
            .unwrap()
            .iter()
            .filter(|e| e.source == source)
            .cloned()
            .collect()
    }

    /// Clear history
    pub fn clear_history(&self) {
        self.history.write().unwrap().clear();
    }

    /// Get subscription count for an event type
    pub fn subscription_count(&self, event_type: EventType) -> usize {
        self.subscriptions
            .read()
            .unwrap()
            .get(&event_type)
            .map(|v| v.len())
            .unwrap_or(0)
    }

    /// Get total subscription count
    pub fn total_subscriptions(&self) -> usize {
        let type_subs: usize = self
            .subscriptions
            .read()
            .unwrap()
            .values()
            .map(|v| v.len())
            .sum();
        let global_subs = self.global_subscriptions.read().unwrap().len();
        type_subs + global_subs
    }
}

// =============================================================================
// GLOBAL EVENT BUS
// =============================================================================

use std::sync::OnceLock;

static GLOBAL_EVENT_BUS: OnceLock<EventBus> = OnceLock::new();

/// Get the global event bus
pub fn get_event_bus() -> &'static EventBus {
    GLOBAL_EVENT_BUS.get_or_init(EventBus::new)
}

/// Publish an event to the global bus
pub fn publish(event: Event) {
    get_event_bus().publish(event);
}

/// Subscribe to events on the global bus
pub fn subscribe<F>(event_type: EventType, handler: F) -> usize
where
    F: Fn(&Event) + Send + Sync + 'static,
{
    get_event_bus().subscribe(event_type, handler)
}

/// Subscribe to all events on the global bus
pub fn subscribe_all<F>(handler: F) -> usize
where
    F: Fn(&Event) + Send + Sync + 'static,
{
    get_event_bus().subscribe_all(handler)
}

// =============================================================================
// TESTS
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    #[test]
    fn test_event_creation() {
        let event = Event::new(EventType::AgentStart, "test_agent");
        assert_eq!(event.event_type, EventType::AgentStart);
        assert_eq!(event.source, "test_agent");
        assert!(event.timestamp > 0);
    }

    #[test]
    fn test_event_with_data() {
        let event = Event::agent_start("test_agent")
            .data(serde_json::json!({"key": "value"}))
            .correlation_id("corr-123");

        assert_eq!(event.data.get("key").unwrap(), "value");
        assert_eq!(event.correlation_id, Some("corr-123".to_string()));
    }

    #[test]
    fn test_event_helpers() {
        let start = Event::agent_start("agent");
        assert_eq!(start.event_type, EventType::AgentStart);

        let error = Event::agent_error("agent", "Something went wrong");
        assert_eq!(error.event_type, EventType::AgentError);
        assert!(error.data.get("error").is_some());

        let handoff = Event::handoff_start("source", "target");
        assert_eq!(handoff.event_type, EventType::HandoffStart);
        assert_eq!(handoff.data.get("target").unwrap(), "target");
    }

    #[test]
    fn test_event_bus_subscribe_publish() {
        let bus = EventBus::new();
        let counter = Arc::new(AtomicUsize::new(0));
        let counter_clone = counter.clone();

        bus.subscribe(EventType::AgentStart, move |_event| {
            counter_clone.fetch_add(1, Ordering::SeqCst);
        });

        bus.publish(Event::agent_start("test"));
        bus.publish(Event::agent_start("test2"));

        assert_eq!(counter.load(Ordering::SeqCst), 2);
    }

    #[test]
    fn test_event_bus_subscribe_all() {
        let bus = EventBus::new();
        let counter = Arc::new(AtomicUsize::new(0));
        let counter_clone = counter.clone();

        bus.subscribe_all(move |_event| {
            counter_clone.fetch_add(1, Ordering::SeqCst);
        });

        bus.publish(Event::agent_start("test"));
        bus.publish(Event::tool_start("tool"));
        bus.publish(Event::llm_request("gpt-4"));

        assert_eq!(counter.load(Ordering::SeqCst), 3);
    }

    #[test]
    fn test_event_bus_unsubscribe() {
        let bus = EventBus::new();
        let counter = Arc::new(AtomicUsize::new(0));
        let counter_clone = counter.clone();

        let sub_id = bus.subscribe(EventType::AgentStart, move |_event| {
            counter_clone.fetch_add(1, Ordering::SeqCst);
        });

        bus.publish(Event::agent_start("test"));
        assert_eq!(counter.load(Ordering::SeqCst), 1);

        bus.unsubscribe(sub_id);
        bus.publish(Event::agent_start("test2"));
        assert_eq!(counter.load(Ordering::SeqCst), 1); // Still 1, handler removed
    }

    #[test]
    fn test_event_bus_history() {
        let bus = EventBus::with_history(10);

        bus.publish(Event::agent_start("agent1"));
        bus.publish(Event::agent_end("agent1"));
        bus.publish(Event::tool_start("tool1"));

        let history = bus.history();
        assert_eq!(history.len(), 3);

        let agent_events = bus.events_by_type(EventType::AgentStart);
        assert_eq!(agent_events.len(), 1);

        let agent1_events = bus.events_by_source("agent1");
        assert_eq!(agent1_events.len(), 2);
    }

    #[test]
    fn test_event_bus_history_limit() {
        let bus = EventBus::with_history(3);

        for i in 0..5 {
            bus.publish(Event::agent_start(format!("agent{}", i)));
        }

        let history = bus.history();
        assert_eq!(history.len(), 3);
        assert_eq!(history[0].source, "agent2");
        assert_eq!(history[2].source, "agent4");
    }

    #[test]
    fn test_event_bus_subscription_count() {
        let bus = EventBus::new();

        bus.subscribe(EventType::AgentStart, |_| {});
        bus.subscribe(EventType::AgentStart, |_| {});
        bus.subscribe(EventType::ToolStart, |_| {});
        bus.subscribe_all(|_| {});

        assert_eq!(bus.subscription_count(EventType::AgentStart), 2);
        assert_eq!(bus.subscription_count(EventType::ToolStart), 1);
        assert_eq!(bus.total_subscriptions(), 4);
    }

    #[test]
    fn test_event_type_filtering() {
        let bus = EventBus::new();
        let agent_counter = Arc::new(AtomicUsize::new(0));
        let tool_counter = Arc::new(AtomicUsize::new(0));

        let agent_counter_clone = agent_counter.clone();
        let tool_counter_clone = tool_counter.clone();

        bus.subscribe(EventType::AgentStart, move |_| {
            agent_counter_clone.fetch_add(1, Ordering::SeqCst);
        });

        bus.subscribe(EventType::ToolStart, move |_| {
            tool_counter_clone.fetch_add(1, Ordering::SeqCst);
        });

        bus.publish(Event::agent_start("agent"));
        bus.publish(Event::agent_start("agent2"));
        bus.publish(Event::tool_start("tool"));

        assert_eq!(agent_counter.load(Ordering::SeqCst), 2);
        assert_eq!(tool_counter.load(Ordering::SeqCst), 1);
    }
}
