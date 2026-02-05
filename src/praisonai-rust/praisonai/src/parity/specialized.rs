//! Specialized Agent Types
//!
//! Provides specialized agent types matching Python SDK:
//! - ContextAgent, create_context_agent
//! - PlanningAgent
//! - FastContext
//! - AutoAgents, AutoRagAgent, AutoRagConfig
//! - TraceSink, TraceSinkProtocol, ContextTraceSink

use std::collections::HashMap;
use std::sync::Arc;

// =============================================================================
// Context Agent
// =============================================================================

/// Context agent configuration
#[derive(Debug, Clone, Default)]
pub struct ContextAgentConfig {
    /// Maximum context tokens
    pub max_tokens: Option<usize>,
    /// Context strategy
    pub strategy: ContextStrategy,
    /// Include system messages
    pub include_system: bool,
    /// Include tool results
    pub include_tools: bool,
}

/// Context strategy
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub enum ContextStrategy {
    /// Keep most recent messages
    #[default]
    Recent,
    /// Summarize older messages
    Summarize,
    /// Use semantic similarity
    Semantic,
    /// Custom strategy
    Custom,
}

/// Context agent for managing conversation context
#[derive(Debug, Clone)]
pub struct ContextAgent {
    /// Configuration
    pub config: ContextAgentConfig,
    /// Context window
    context: Vec<ContextEntry>,
    /// Maximum entries
    max_entries: usize,
}

/// Context entry
#[derive(Debug, Clone)]
pub struct ContextEntry {
    /// Entry role
    pub role: String,
    /// Entry content
    pub content: String,
    /// Entry timestamp
    pub timestamp: std::time::SystemTime,
    /// Entry metadata
    pub metadata: HashMap<String, serde_json::Value>,
}

impl Default for ContextAgent {
    fn default() -> Self {
        Self::new(ContextAgentConfig::default())
    }
}

impl ContextAgent {
    /// Create a new context agent
    pub fn new(config: ContextAgentConfig) -> Self {
        Self {
            config,
            context: Vec::new(),
            max_entries: 100,
        }
    }

    /// Add an entry to context
    pub fn add(&mut self, role: impl Into<String>, content: impl Into<String>) {
        let entry = ContextEntry {
            role: role.into(),
            content: content.into(),
            timestamp: std::time::SystemTime::now(),
            metadata: HashMap::new(),
        };
        self.context.push(entry);

        // Trim if exceeds max
        if self.context.len() > self.max_entries {
            self.context.remove(0);
        }
    }

    /// Get context as messages
    pub fn get_context(&self) -> Vec<&ContextEntry> {
        match self.config.strategy {
            ContextStrategy::Recent => {
                let max = self.config.max_tokens.unwrap_or(self.max_entries);
                self.context.iter().rev().take(max).collect()
            }
            _ => self.context.iter().collect(),
        }
    }

    /// Clear context
    pub fn clear(&mut self) {
        self.context.clear();
    }

    /// Get context length
    pub fn len(&self) -> usize {
        self.context.len()
    }

    /// Check if context is empty
    pub fn is_empty(&self) -> bool {
        self.context.is_empty()
    }
}

/// Create a context agent with default configuration
pub fn create_context_agent() -> ContextAgent {
    ContextAgent::default()
}

/// Create a context agent with custom configuration
pub fn create_context_agent_with_config(config: ContextAgentConfig) -> ContextAgent {
    ContextAgent::new(config)
}

// =============================================================================
// Planning Agent
// =============================================================================

/// Planning agent configuration
#[derive(Debug, Clone, Default)]
pub struct PlanningAgentConfig {
    /// Maximum planning steps
    pub max_steps: usize,
    /// Enable reasoning
    pub reasoning: bool,
    /// Planning LLM model
    pub llm: Option<String>,
}

/// Planning step
#[derive(Debug, Clone)]
pub struct PlanningStep {
    /// Step number
    pub step: usize,
    /// Step description
    pub description: String,
    /// Step status
    pub status: PlanningStepStatus,
    /// Step result
    pub result: Option<String>,
}

/// Planning step status
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum PlanningStepStatus {
    #[default]
    Pending,
    InProgress,
    Completed,
    Failed,
    Skipped,
}

/// Planning agent for multi-step task planning
#[derive(Debug, Clone)]
pub struct PlanningAgent {
    /// Configuration
    pub config: PlanningAgentConfig,
    /// Current plan
    plan: Vec<PlanningStep>,
    /// Current step index
    current_step: usize,
}

impl Default for PlanningAgent {
    fn default() -> Self {
        Self::new(PlanningAgentConfig {
            max_steps: 10,
            reasoning: true,
            llm: None,
        })
    }
}

impl PlanningAgent {
    /// Create a new planning agent
    pub fn new(config: PlanningAgentConfig) -> Self {
        Self {
            config,
            plan: Vec::new(),
            current_step: 0,
        }
    }

    /// Create a plan from a task
    pub fn create_plan(&mut self, task: &str) -> Vec<PlanningStep> {
        // In a real implementation, this would use an LLM to generate steps
        // For now, create a simple single-step plan
        self.plan = vec![PlanningStep {
            step: 1,
            description: format!("Execute task: {}", task),
            status: PlanningStepStatus::Pending,
            result: None,
        }];
        self.current_step = 0;
        self.plan.clone()
    }

    /// Add a step to the plan
    pub fn add_step(&mut self, description: impl Into<String>) {
        let step_num = self.plan.len() + 1;
        self.plan.push(PlanningStep {
            step: step_num,
            description: description.into(),
            status: PlanningStepStatus::Pending,
            result: None,
        });
    }

    /// Get current step
    pub fn current(&self) -> Option<&PlanningStep> {
        self.plan.get(self.current_step)
    }

    /// Mark current step as complete
    pub fn complete_step(&mut self, result: Option<String>) {
        if let Some(step) = self.plan.get_mut(self.current_step) {
            step.status = PlanningStepStatus::Completed;
            step.result = result;
        }
        self.current_step += 1;
    }

    /// Mark current step as failed
    pub fn fail_step(&mut self, error: impl Into<String>) {
        if let Some(step) = self.plan.get_mut(self.current_step) {
            step.status = PlanningStepStatus::Failed;
            step.result = Some(error.into());
        }
    }

    /// Get all steps
    pub fn steps(&self) -> &[PlanningStep] {
        &self.plan
    }

    /// Check if plan is complete
    pub fn is_complete(&self) -> bool {
        self.current_step >= self.plan.len()
    }

    /// Get progress percentage
    pub fn progress(&self) -> f32 {
        if self.plan.is_empty() {
            return 100.0;
        }
        (self.current_step as f32 / self.plan.len() as f32) * 100.0
    }
}

// =============================================================================
// Fast Context
// =============================================================================

/// Fast context for efficient context management
#[derive(Debug, Clone, Default)]
pub struct FastContext {
    /// Context entries
    entries: Vec<String>,
    /// Maximum size in characters
    max_size: usize,
    /// Current size
    current_size: usize,
}

impl FastContext {
    /// Create a new fast context
    pub fn new(max_size: usize) -> Self {
        Self {
            entries: Vec::new(),
            max_size,
            current_size: 0,
        }
    }

    /// Add content to context
    pub fn add(&mut self, content: impl Into<String>) {
        let content = content.into();
        let content_len = content.len();

        // Remove old entries if needed
        while self.current_size + content_len > self.max_size && !self.entries.is_empty() {
            if let Some(removed) = self.entries.first() {
                self.current_size -= removed.len();
            }
            self.entries.remove(0);
        }

        self.entries.push(content);
        self.current_size += content_len;
    }

    /// Get all context
    pub fn get(&self) -> &[String] {
        &self.entries
    }

    /// Get context as single string
    pub fn as_string(&self) -> String {
        self.entries.join("\n")
    }

    /// Clear context
    pub fn clear(&mut self) {
        self.entries.clear();
        self.current_size = 0;
    }

    /// Get current size
    pub fn size(&self) -> usize {
        self.current_size
    }

    /// Check if empty
    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }
}

// =============================================================================
// Auto Agents
// =============================================================================

/// Auto agents configuration
#[derive(Debug, Clone, Default)]
pub struct AutoAgentsConfig {
    /// Task description
    pub task: String,
    /// Number of agents to create
    pub num_agents: Option<usize>,
    /// LLM model for generation
    pub llm: Option<String>,
    /// Verbose output
    pub verbose: bool,
}

/// Auto agents for automatic agent generation
#[derive(Debug, Clone)]
pub struct AutoAgents {
    /// Configuration
    pub config: AutoAgentsConfig,
    /// Generated agent configs
    agents: Vec<AutoAgentSpec>,
}

/// Auto-generated agent specification
#[derive(Debug, Clone)]
pub struct AutoAgentSpec {
    /// Agent name
    pub name: String,
    /// Agent role
    pub role: String,
    /// Agent goal
    pub goal: String,
    /// Agent backstory
    pub backstory: Option<String>,
    /// Agent tools
    pub tools: Vec<String>,
}

impl AutoAgents {
    /// Create new auto agents
    pub fn new(config: AutoAgentsConfig) -> Self {
        Self {
            config,
            agents: Vec::new(),
        }
    }

    /// Generate agents for a task
    pub fn generate(&mut self, task: &str) -> &[AutoAgentSpec] {
        // In a real implementation, this would use an LLM to generate agent specs
        // For now, create a simple single agent
        self.agents = vec![AutoAgentSpec {
            name: "Assistant".to_string(),
            role: "General Assistant".to_string(),
            goal: format!("Complete the task: {}", task),
            backstory: None,
            tools: Vec::new(),
        }];
        &self.agents
    }

    /// Get generated agents
    pub fn agents(&self) -> &[AutoAgentSpec] {
        &self.agents
    }
}

// =============================================================================
// Auto RAG Agent
// =============================================================================

/// Auto RAG configuration
#[derive(Debug, Clone, Default, serde::Serialize, serde::Deserialize)]
pub struct AutoRagConfig {
    /// Enable AutoRAG
    #[serde(default)]
    pub enabled: bool,
    /// Chunk size for documents
    pub chunk_size: Option<usize>,
    /// Chunk overlap
    pub chunk_overlap: Option<usize>,
    /// Embedding model
    pub embedding_model: Option<String>,
    /// Vector store backend
    pub vector_store: Option<String>,
    /// Number of results to retrieve
    pub top_k: Option<usize>,
}

/// Auto RAG agent for automatic RAG setup
#[derive(Debug, Clone)]
pub struct AutoRagAgent {
    /// Configuration
    pub config: AutoRagConfig,
    /// Document sources
    sources: Vec<String>,
    /// Indexed
    indexed: bool,
}

impl AutoRagAgent {
    /// Create a new AutoRAG agent
    pub fn new(config: AutoRagConfig) -> Self {
        Self {
            config,
            sources: Vec::new(),
            indexed: false,
        }
    }

    /// Add a document source
    pub fn add_source(&mut self, source: impl Into<String>) {
        self.sources.push(source.into());
        self.indexed = false;
    }

    /// Add multiple sources
    pub fn add_sources(&mut self, sources: impl IntoIterator<Item = impl Into<String>>) {
        for source in sources {
            self.sources.push(source.into());
        }
        self.indexed = false;
    }

    /// Index documents
    pub fn index(&mut self) -> Result<(), String> {
        // In a real implementation, this would process and index documents
        self.indexed = true;
        Ok(())
    }

    /// Query the RAG system
    pub fn query(&self, query: &str) -> Result<Vec<String>, String> {
        if !self.indexed {
            return Err("Documents not indexed. Call index() first.".to_string());
        }
        // In a real implementation, this would perform semantic search
        Ok(vec![format!("Result for query: {}", query)])
    }

    /// Check if indexed
    pub fn is_indexed(&self) -> bool {
        self.indexed
    }

    /// Get sources
    pub fn sources(&self) -> &[String] {
        &self.sources
    }
}

// =============================================================================
// Trace Sink
// =============================================================================

/// Trace sink protocol trait
pub trait TraceSinkProtocol: Send + Sync {
    /// Write a trace event
    fn write(&self, event: &TraceEvent);
    
    /// Flush pending events
    fn flush(&self);
    
    /// Close the sink
    fn close(&self);
}

/// Trace event
#[derive(Debug, Clone)]
pub struct TraceEvent {
    /// Event type
    pub event_type: String,
    /// Event timestamp
    pub timestamp: std::time::SystemTime,
    /// Event data
    pub data: HashMap<String, serde_json::Value>,
    /// Trace ID
    pub trace_id: Option<String>,
    /// Span ID
    pub span_id: Option<String>,
    /// Parent span ID
    pub parent_span_id: Option<String>,
}

impl TraceEvent {
    /// Create a new trace event
    pub fn new(event_type: impl Into<String>) -> Self {
        Self {
            event_type: event_type.into(),
            timestamp: std::time::SystemTime::now(),
            data: HashMap::new(),
            trace_id: None,
            span_id: None,
            parent_span_id: None,
        }
    }

    /// Set trace ID
    pub fn trace_id(mut self, id: impl Into<String>) -> Self {
        self.trace_id = Some(id.into());
        self
    }

    /// Set span ID
    pub fn span_id(mut self, id: impl Into<String>) -> Self {
        self.span_id = Some(id.into());
        self
    }

    /// Add data
    pub fn data(mut self, key: impl Into<String>, value: serde_json::Value) -> Self {
        self.data.insert(key.into(), value);
        self
    }
}

/// Context trace sink for collecting traces
#[derive(Debug, Default)]
pub struct ContextTraceSink {
    /// Collected events
    events: std::sync::RwLock<Vec<TraceEvent>>,
    /// Maximum events to keep
    max_events: usize,
}

impl ContextTraceSink {
    /// Create a new context trace sink
    pub fn new(max_events: usize) -> Self {
        Self {
            events: std::sync::RwLock::new(Vec::new()),
            max_events,
        }
    }

    /// Get all events
    pub fn events(&self) -> Vec<TraceEvent> {
        self.events.read().unwrap().clone()
    }

    /// Clear events
    pub fn clear(&self) {
        self.events.write().unwrap().clear();
    }
}

impl TraceSinkProtocol for ContextTraceSink {
    fn write(&self, event: &TraceEvent) {
        let mut events = self.events.write().unwrap();
        events.push(event.clone());
        
        // Trim if exceeds max
        while events.len() > self.max_events {
            events.remove(0);
        }
    }

    fn flush(&self) {
        // No-op for in-memory sink
    }

    fn close(&self) {
        // No-op for in-memory sink
    }
}

/// Type alias for TraceSink
pub type TraceSink = Arc<dyn TraceSinkProtocol>;

// =============================================================================
// Memory Backend
// =============================================================================

/// Memory backend types
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum MemoryBackend {
    /// In-memory storage
    #[default]
    InMemory,
    /// SQLite storage
    Sqlite,
    /// PostgreSQL storage
    Postgres,
    /// Redis storage
    Redis,
    /// ChromaDB storage
    Chroma,
    /// Custom backend
    Custom,
}

impl std::fmt::Display for MemoryBackend {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InMemory => write!(f, "in_memory"),
            Self::Sqlite => write!(f, "sqlite"),
            Self::Postgres => write!(f, "postgres"),
            Self::Redis => write!(f, "redis"),
            Self::Chroma => write!(f, "chroma"),
            Self::Custom => write!(f, "custom"),
        }
    }
}

impl std::str::FromStr for MemoryBackend {
    type Err = String;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s.to_lowercase().as_str() {
            "in_memory" | "inmemory" | "memory" => Ok(Self::InMemory),
            "sqlite" => Ok(Self::Sqlite),
            "postgres" | "postgresql" => Ok(Self::Postgres),
            "redis" => Ok(Self::Redis),
            "chroma" | "chromadb" => Ok(Self::Chroma),
            "custom" => Ok(Self::Custom),
            _ => Err(format!("Unknown memory backend: {}", s)),
        }
    }
}

// =============================================================================
// Tools Type Alias
// =============================================================================

/// Tools type alias (for compatibility with Python SDK naming)
pub type Tools = crate::tools::ToolRegistry;

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_context_agent() {
        let mut agent = create_context_agent();
        assert!(agent.is_empty());

        agent.add("user", "Hello");
        agent.add("assistant", "Hi there!");

        assert_eq!(agent.len(), 2);
        assert!(!agent.is_empty());

        let context = agent.get_context();
        assert_eq!(context.len(), 2);
    }

    #[test]
    fn test_planning_agent() {
        let mut agent = PlanningAgent::default();
        
        agent.create_plan("Test task");
        assert!(!agent.is_complete());
        assert_eq!(agent.progress(), 0.0);

        agent.complete_step(Some("Done".to_string()));
        assert!(agent.is_complete());
        assert_eq!(agent.progress(), 100.0);
    }

    #[test]
    fn test_fast_context() {
        let mut ctx = FastContext::new(100);
        assert!(ctx.is_empty());

        ctx.add("Hello");
        ctx.add("World");

        assert!(!ctx.is_empty());
        assert_eq!(ctx.get().len(), 2);
        assert_eq!(ctx.as_string(), "Hello\nWorld");
    }

    #[test]
    fn test_auto_rag_agent() {
        let config = AutoRagConfig {
            enabled: true,
            chunk_size: Some(500),
            ..Default::default()
        };

        let mut agent = AutoRagAgent::new(config);
        agent.add_source("doc1.pdf");
        agent.add_source("doc2.txt");

        assert_eq!(agent.sources().len(), 2);
        assert!(!agent.is_indexed());

        agent.index().unwrap();
        assert!(agent.is_indexed());
    }

    #[test]
    fn test_trace_event() {
        let event = TraceEvent::new("test_event")
            .trace_id("trace-123")
            .span_id("span-456")
            .data("key", serde_json::json!("value"));

        assert_eq!(event.event_type, "test_event");
        assert_eq!(event.trace_id, Some("trace-123".to_string()));
        assert_eq!(event.span_id, Some("span-456".to_string()));
    }

    #[test]
    fn test_context_trace_sink() {
        let sink = ContextTraceSink::new(10);
        
        let event = TraceEvent::new("test");
        sink.write(&event);

        let events = sink.events();
        assert_eq!(events.len(), 1);

        sink.clear();
        assert!(sink.events().is_empty());
    }

    #[test]
    fn test_memory_backend_parse() {
        assert_eq!("sqlite".parse::<MemoryBackend>().unwrap(), MemoryBackend::Sqlite);
        assert_eq!("postgres".parse::<MemoryBackend>().unwrap(), MemoryBackend::Postgres);
        assert_eq!("redis".parse::<MemoryBackend>().unwrap(), MemoryBackend::Redis);
    }
}
