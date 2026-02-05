# AGENTS.md - PraisonAI Rust SDK Comprehensive Guide

> **For AI Agents and Developers**: Complete context for working with the PraisonAI Rust SDK, including architecture, crate structure, and development guidelines.

---

## 1. What is PraisonAI Rust?

PraisonAI Rust SDK is a **high-performance, agentic AI framework** for Rust. It mirrors the Python SDK's design philosophy while leveraging Rust's performance and safety guarantees.

### Core Philosophy

```
Simpler than competitors • Type-safe • Zero-cost abstractions • Blazing fast
```

| Principle | Description |
|-----------|-------------|
| **Agent-Centric** | Every design decision centers on Agents, workflows, and tools |
| **Trait-Driven** | Core SDK uses Rust traits for all extension points |
| **Minimal API** | Builder patterns, sensible defaults, explicit overrides |
| **Zero-Cost** | No runtime overhead for abstractions |
| **Async-First** | All I/O operations are async with tokio |
| **Multi-Agent Safe** | Thread-safe, concurrent agent execution |
| **TDD Mandatory** | Tests first; failing tests prove gaps; passing tests prove fixes |
| **Production-Ready** | Error handling with `Result`, observability, type safety |

---

## 2. Repository Structure

### 2.1 Canonical Paths

```
/Users/praison/praisonai-package/
├── src/
│   └── praisonai-rust/           # Rust SDK workspace (THIS DIRECTORY)
│       ├── Cargo.toml            # Workspace configuration
│       ├── AGENTS.md             # This file
│       │
│       ├── praisonai/            # Core library crate
│       │   ├── Cargo.toml
│       │   └── src/
│       │       ├── lib.rs        # Public API exports
│       │       ├── agent/        # Agent struct, builder
│       │       ├── tools/        # Tool trait, registry
│       │       ├── llm/          # LLM provider trait
│       │       ├── memory/       # Memory adapters
│       │       ├── workflows/    # AgentTeam, AgentFlow
│       │       ├── config.rs     # Configuration structs
│       │       └── error.rs      # Error types
│       │
│       ├── praisonai-derive/     # Proc-macro crate
│       │   ├── Cargo.toml
│       │   └── src/lib.rs        # #[tool] attribute macro
│       │
│       ├── praisonai-cli/        # CLI binary crate
│       │   ├── Cargo.toml
│       │   └── src/
│       │       ├── main.rs
│       │       └── commands/     # chat, run, prompt commands
│       │
│       └── examples/             # Example code
│
/Users/praison/praisonai-package/examples/rust/    # Main examples directory
/Users/praison/PraisonAIDocs/docs/rust/            # Documentation (Mintlify)
```

### 2.2 Crate Hierarchy

```
┌─────────────────────────────────────────────────────────────────┐
│                   praisonai-cli (Binary)                        │
│           chat • run • prompt • workflow commands               │
├─────────────────────────────────────────────────────────────────┤
│                     praisonai (Core Library)                    │
│      Agent • Tools • Workflows • Memory • LLM • Config          │
├─────────────────────────────────────────────────────────────────┤
│                   praisonai-derive (Proc-Macro)                 │
│                       #[tool] macro                             │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 Crate Responsibilities

| Crate | Type | Purpose | crates.io |
|-------|------|---------|-----------|
| `praisonai` | lib | Core library - Agent, Tools, Workflows | ✅ Published |
| `praisonai-derive` | proc-macro | `#[tool]` attribute macro | ✅ Published |
| `praisonai-cli` | bin | CLI binary for running agents | ✅ Published |

---

## 3. Core Architecture

### 3.1 Key Modules (praisonai crate)

| Module | Lines | Purpose |
|--------|-------|---------|
| `agent/` | ~280 | Agent struct, AgentBuilder, execution loop |
| `tools/` | ~251 | Tool trait, ToolRegistry, ToolResult, FunctionTool |
| `llm/` | ~361 | LlmProvider trait, OpenAiProvider, Message, Role |
| `memory/` | ~150 | Memory trait, InMemoryAdapter, conversation history |
| `workflows/` | ~461 | AgentTeam, AgentFlow, Route, Parallel, Loop, Repeat |
| `config.rs` | ~228 | MemoryConfig, HooksConfig, OutputConfig, ExecutionConfig |
| `error.rs` | ~100 | Error enum with thiserror |

### 3.2 Trait-Driven Design

Core SDK uses Rust traits for all extension points:

```rust
// Pattern: Traits define WHAT, implementations provide HOW

/// Tool trait for agent capabilities
#[async_trait]
pub trait Tool: Send + Sync {
    fn name(&self) -> &str;
    fn description(&self) -> &str;
    fn parameters_schema(&self) -> serde_json::Value;
    async fn execute(&self, args: serde_json::Value) -> Result<Value>;
}

/// LLM provider trait for model abstraction
#[async_trait]
pub trait LlmProvider: Send + Sync {
    fn model(&self) -> &str;
    async fn chat(
        &self,
        messages: &[Message],
        tools: Option<&[ToolDefinition]>,
    ) -> Result<LlmResponse>;
}

/// Memory adapter trait for persistence
pub trait MemoryAdapter: Send + Sync {
    async fn store(&mut self, message: Message) -> Result<()>;
    async fn history(&self) -> Result<Vec<Message>>;
    async fn clear(&mut self) -> Result<()>;
}
```

### 3.3 Core Dependencies

```toml
# Cargo.toml - workspace dependencies
[workspace.dependencies]
tokio = { version = "1", features = ["full"] }    # Async runtime
async-trait = "0.1"                                # Async trait support
serde = { version = "1", features = ["derive"] }  # Serialization
serde_json = "1"                                   # JSON
serde_yaml = "0.9"                                 # YAML config
thiserror = "2"                                    # Error handling
anyhow = "1"                                       # Error context
rig-core = "0.9"                                   # LLM providers
clap = { version = "4", features = ["derive"] }   # CLI parsing
tracing = "0.1"                                    # Logging
uuid = { version = "1", features = ["v4"] }       # Session IDs
reqwest = { version = "0.12", features = ["json"] } # HTTP client
```

---

## 4. Core Types & API

### 4.1 Agent

The primary struct for creating AI agents:

```rust
use praisonai::{Agent, AgentBuilder, AgentConfig};

// Agent fields (internal)
pub struct Agent {
    id: String,              // Unique agent ID (UUID)
    name: String,            // Agent name
    instructions: String,    // System prompt
    llm: Arc<dyn LlmProvider>, // LLM backend
    tools: Arc<RwLock<ToolRegistry>>, // Registered tools
    memory: Arc<RwLock<Memory>>,      // Conversation memory
    config: AgentConfig,     // Configuration
}

impl Agent {
    // Create a builder
    pub fn new() -> AgentBuilder;
    
    // One-liner creation
    pub fn simple(instructions: impl Into<String>) -> Result<Self>;
    
    // Chat (main entry point)
    pub async fn chat(&self, prompt: &str) -> Result<String>;
    
    // Aliases for chat
    pub async fn start(&self, prompt: &str) -> Result<String>;
    pub async fn run(&self, task: &str) -> Result<String>;
    
    // Tool management
    pub async fn add_tool(&self, tool: impl Tool + 'static);
    pub async fn tool_count(&self) -> usize;
    
    // Memory management
    pub async fn clear_memory(&self) -> Result<()>;
    pub async fn history(&self) -> Result<Vec<Message>>;
    
    // Getters
    pub fn id(&self) -> &str;
    pub fn name(&self) -> &str;
    pub fn instructions(&self) -> &str;
    pub fn model(&self) -> &str;
}
```

### 4.2 AgentBuilder

Builder pattern for Agent configuration:

```rust
pub struct AgentBuilder {
    name: String,
    instructions: String,
    model: String,
    tools: ToolRegistry,
    memory_config: MemoryConfig,
    config: AgentConfig,
}

impl AgentBuilder {
    pub fn new() -> Self;
    pub fn name(self, name: impl Into<String>) -> Self;
    pub fn instructions(self, instructions: impl Into<String>) -> Self;
    pub fn model(self, model: impl Into<String>) -> Self;
    pub fn tool(self, tool: impl Tool + 'static) -> Self;
    pub fn memory(self, config: MemoryConfig) -> Self;
    pub fn build(self) -> Result<Agent>;
}
```

### 4.3 AgentTeam

Multi-agent orchestration:

```rust
use praisonai::{AgentTeam, Process};

pub struct AgentTeam {
    agents: Vec<Arc<Agent>>,
    process: Process,
    verbose: bool,
    context: WorkflowContext,
}

#[derive(Default)]
pub enum Process {
    #[default]
    Sequential,  // Execute agents one after another
    Parallel,    // Execute agents concurrently
    Hierarchical, // Manager-based execution
}

impl AgentTeam {
    pub fn new() -> AgentTeamBuilder;
    pub async fn start(&self, task: &str) -> Result<String>;
    pub async fn run(&self, task: &str) -> Result<String>;  // Alias
    pub fn len(&self) -> usize;
    pub fn is_empty(&self) -> bool;
}
```

### 4.4 AgentFlow (Workflow Patterns)

Advanced workflow patterns:

```rust
use praisonai::{AgentFlow, Route, Parallel, Loop, Repeat, FlowStep};

// Route: Conditional branching
pub struct Route {
    pub condition: Box<dyn Fn(&str) -> bool + Send + Sync>,
    pub if_true: Arc<Agent>,
    pub if_false: Option<Arc<Agent>>,
}

// Parallel: Concurrent execution
pub struct Parallel {
    pub agents: Vec<Arc<Agent>>,
}

// Loop: Conditional iteration
pub struct Loop {
    pub condition: Box<dyn Fn(&str) -> bool + Send + Sync>,
    pub agent: Arc<Agent>,
    pub max_iterations: usize,
}

// Repeat: Fixed iteration
pub struct Repeat {
    pub agent: Arc<Agent>,
    pub times: usize,
}

pub enum FlowStep {
    Agent(Arc<Agent>),
    Route(Route),
    Parallel(Parallel),
    Loop(Loop),
    Repeat(Repeat),
}

impl AgentFlow {
    pub fn new() -> Self;
    pub fn step(self, step: FlowStep) -> Self;
    pub fn agent(self, agent: Agent) -> Self;
    pub async fn run(&self, input: &str) -> Result<String>;
}
```

### 4.5 Tool & ToolRegistry

Tool abstraction and management:

```rust
use praisonai::{Tool, ToolRegistry, ToolResult, ToolDefinition};

#[async_trait]
pub trait Tool: Send + Sync {
    fn name(&self) -> &str;
    fn description(&self) -> &str;
    fn parameters_schema(&self) -> Value;
    async fn execute(&self, args: Value) -> Result<Value>;
    fn definition(&self) -> ToolDefinition;  // Has default impl
}

pub struct ToolResult {
    pub name: String,
    pub value: Value,
    pub success: bool,
    pub error: Option<String>,
}

pub struct ToolRegistry {
    tools: HashMap<String, Arc<dyn Tool>>,
}

impl ToolRegistry {
    pub fn new() -> Self;
    pub fn register(&mut self, tool: impl Tool + 'static);
    pub fn get(&self, name: &str) -> Option<Arc<dyn Tool>>;
    pub fn has(&self, name: &str) -> bool;
    pub fn list(&self) -> Vec<&str>;
    pub fn definitions(&self) -> Vec<ToolDefinition>;
    pub async fn execute(&self, name: &str, args: Value) -> Result<ToolResult>;
    pub fn len(&self) -> usize;
    pub fn is_empty(&self) -> bool;
}
```

### 4.6 Message & LlmProvider

LLM abstraction:

```rust
use praisonai::{Message, Role, LlmProvider, LlmResponse, LlmConfig};

#[derive(Clone, Serialize, Deserialize)]
pub enum Role {
    System,
    User,
    Assistant,
    Tool,
}

#[derive(Clone, Serialize, Deserialize)]
pub struct Message {
    pub role: Role,
    pub content: String,
    pub tool_call_id: Option<String>,
    pub tool_calls: Option<Vec<ToolCall>>,
}

impl Message {
    pub fn system(content: impl Into<String>) -> Self;
    pub fn user(content: impl Into<String>) -> Self;
    pub fn assistant(content: impl Into<String>) -> Self;
    pub fn tool(tool_call_id: impl Into<String>, content: impl Into<String>) -> Self;
}

pub struct LlmConfig {
    pub model: String,
    pub api_key: Option<String>,
    pub base_url: Option<String>,
    pub temperature: f32,
    pub max_tokens: Option<u32>,
}
```

---

## 5. Configuration Types

### 5.1 MemoryConfig

```rust
use praisonai::config::MemoryConfig;

pub struct MemoryConfig {
    pub use_short_term: bool,  // Default: true
    pub use_long_term: bool,   // Default: false
    pub provider: String,      // Default: "memory"
    pub max_messages: usize,   // Default: 100
}

impl MemoryConfig {
    pub fn new() -> Self;
    pub fn with_long_term(self) -> Self;
    pub fn provider(self, provider: impl Into<String>) -> Self;
    pub fn max_messages(self, max: usize) -> Self;
}
```

### 5.2 ExecutionConfig

```rust
use praisonai::config::ExecutionConfig;

pub struct ExecutionConfig {
    pub max_iterations: usize, // Default: 10
    pub timeout_secs: u64,     // Default: 300
    pub stream: bool,          // Default: true
}

impl ExecutionConfig {
    pub fn new() -> Self;
    pub fn max_iterations(self, max: usize) -> Self;
    pub fn timeout(self, secs: u64) -> Self;
    pub fn no_stream(self) -> Self;
}
```

### 5.3 OutputConfig

```rust
use praisonai::config::OutputConfig;

pub struct OutputConfig {
    pub mode: String,          // "silent", "verbose", "json"
    pub file: Option<String>,  // Output file path
}

impl OutputConfig {
    pub fn new() -> Self;
    pub fn silent(self) -> Self;
    pub fn verbose(self) -> Self;
    pub fn json(self) -> Self;
    pub fn file(self, path: impl Into<String>) -> Self;
}
```

### 5.4 HooksConfig

```rust
use praisonai::config::HooksConfig;

pub struct HooksConfig {
    pub enabled: bool,
}

impl HooksConfig {
    pub fn new() -> Self;
    pub fn enabled(self) -> Self;
}
```

---

## 6. API Usage Examples

### 6.1 One-Liner (Simplest)

```rust
use praisonai::Agent;

// Equivalent to Python: Agent(instructions="Be helpful")
let agent = Agent::simple("Be helpful")?;
let response = agent.chat("Hello!").await?;
```

### 6.2 Builder Pattern (More Control)

```rust
use praisonai::Agent;

let agent = Agent::new()
    .name("assistant")
    .instructions("You are a helpful AI assistant")
    .model("gpt-4o-mini")
    .build()?;

let response = agent.chat("What is 2+2?").await?;
// Also available: agent.start() and agent.run() as aliases
```

### 6.3 With Tools

```rust
use praisonai::{Agent, tool};

#[tool(description = "Search the web for information")]
async fn search(query: String) -> String {
    format!("Results for: {}", query)
}

let agent = Agent::new()
    .instructions("Use search to help users find information")
    .tool(search)
    .build()?;

let response = agent.chat("Find info about Rust").await?;
```

### 6.4 Multi-Agent Team

```rust
use praisonai::{Agent, AgentTeam, Process};

// Build team with builder pattern
let team = AgentTeam::new()
    .agent(Agent::simple("Research topics thoroughly")?)
    .agent(Agent::simple("Write engaging content")?)
    .agent(Agent::simple("Edit for clarity")?)
    .process(Process::Sequential)  // or Parallel, Hierarchical
    .build();

let result = team.start("Write about AI safety").await?;
```

### 6.5 Workflow Patterns (AgentFlow)

```rust
use praisonai::{Agent, AgentFlow, FlowStep, Route, Parallel, Repeat};
use std::sync::Arc;

let agent = Arc::new(Agent::simple("Be helpful")?);

// Simple agent step
let result = AgentFlow::new()
    .agent(Agent::simple("Process the input")?)
    .run("Hello").await?;

// Route based on condition
let flow = AgentFlow::new()
    .step(FlowStep::Route(Route {
        condition: Box::new(|input| input.contains("urgent")),
        if_true: Arc::clone(&agent),
        if_false: None,
    }));

// Parallel execution
let flow = AgentFlow::new()
    .step(FlowStep::Parallel(Parallel {
        agents: vec![agent1, agent2, agent3],
    }));

// Repeat N times
let flow = AgentFlow::new()
    .step(FlowStep::Repeat(Repeat {
        agent: Arc::clone(&agent),
        times: 3,
    }));

let result = flow.run("Input prompt").await?;
```

### 6.6 Progressive Disclosure Summary

| Level | Code | Use Case |
|-------|------|----------|
| **Simplest** | `Agent::simple("instructions")?` | Quick prototyping |
| **Basic** | `Agent::new().instructions(...).build()?` | Most apps |
| **With Tools** | `Agent::new()...tool(fn).build()?` | Tool-using agents |
| **Team** | `AgentTeam::new().agent(...).build()` | Multi-agent |
| **Flows** | `AgentFlow::new().step(...)` | Complex patterns |

---

## 7. CLI Usage

### 7.1 Commands

```bash
# Install CLI
cargo install praisonai-cli

# Interactive chat
praisonai-rust chat

# Run from YAML workflow
praisonai-rust run workflow.yaml

# Single prompt
praisonai-rust "What is 2+2?"

# With specific model
praisonai-rust --model gpt-4o "Explain quantum computing"
```

### 7.2 CLI Commands Structure

| Command | File | Purpose |
|---------|------|---------|
| `chat` | `commands/chat.rs` | Interactive chat session |
| `run` | `commands/run.rs` | Run workflow from YAML |
| `prompt` | `commands/prompt.rs` | Single prompt execution |

### 7.3 YAML Workflow Format

```yaml
# agents.yaml
agents:
  - name: researcher
    role: Research Assistant
    instructions: Find accurate information
    tools:
      - web_search
  - name: writer
    role: Content Writer
    instructions: Write clear, engaging content

workflow:
  - step: research
    agent: researcher
    task: Research the topic
  - step: write
    agent: writer
    task: Write article based on research
```

---

## 8. Extension Points

### 8.1 Custom Tools

```rust
// Using #[tool] macro (recommended)
use praisonai::tool;

#[tool(description = "Calculate mathematical expressions")]
async fn calculate(expression: String) -> String {
    // Implementation
    format!("Result: {}", expression)
}

// Manual implementation
use praisonai::tools::{Tool, ToolResult};
use async_trait::async_trait;

struct MyTool;

#[async_trait]
impl Tool for MyTool {
    fn name(&self) -> &str { "my_tool" }
    fn description(&self) -> &str { "Does something useful" }
    fn parameters_schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "input": { "type": "string" }
            }
        })
    }
    async fn execute(&self, args: serde_json::Value) -> Result<Value> {
        Ok(serde_json::json!("Result"))
    }
}
```

### 8.2 Custom LLM Providers

```rust
use praisonai::llm::{LlmProvider, Message, LlmResponse, ToolDefinition};
use async_trait::async_trait;

struct MyProvider {
    api_key: String,
    model: String,
}

#[async_trait]
impl LlmProvider for MyProvider {
    fn model(&self) -> &str {
        &self.model
    }
    
    async fn chat(
        &self,
        messages: &[Message],
        tools: Option<&[ToolDefinition]>,
    ) -> Result<LlmResponse> {
        // Call your LLM API
        todo!()
    }
}
```

### 8.3 Custom Memory Adapters

```rust
use praisonai::memory::{MemoryAdapter, Message};
use async_trait::async_trait;

struct RedisMemory {
    client: redis::Client,
}

#[async_trait]
impl MemoryAdapter for RedisMemory {
    async fn store(&mut self, message: Message) -> Result<()> {
        // Store in Redis
        todo!()
    }
    async fn history(&self) -> Result<Vec<Message>> {
        // Retrieve from Redis
        todo!()
    }
    async fn clear(&mut self) -> Result<()> {
        // Clear Redis keys
        todo!()
    }
}
```

---

## 9. Development Guidelines

### 9.1 Core Principles (MUST)

| Principle | Description |
|-----------|-------------|
| **Trait-driven** | Use traits for all extension points |
| **Result everywhere** | All fallible operations return `Result<T, Error>` |
| **Async-first** | All I/O is async with tokio |
| **Builder pattern** | Complex structs use builders |
| **Zero unsafe** | No unsafe code without explicit justification |
| **Send + Sync** | All shared types must be thread-safe |

### 9.2 Error Handling

```rust
// Use thiserror for library error types
#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("Agent error: {0}")]
    Agent(String),
    
    #[error("LLM error: {0}")]
    Llm(String),
    
    #[error("Tool error: {0}")]
    Tool(String),
    
    #[error("Configuration error: {0}")]
    Config(String),
    
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
    
    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),
}

// Use anyhow for application code
use anyhow::{Context, Result};

fn load_config() -> Result<Config> {
    let content = fs::read_to_string("config.yaml")
        .context("Failed to read config file")?;
    Ok(serde_yaml::from_str(&content)?)
}
```

### 9.3 Naming Conventions

```rust
// Structs: PascalCase
pub struct AgentBuilder { }
pub struct ToolRegistry { }

// Traits: PascalCase, often suffixed
pub trait LlmProvider { }
pub trait MemoryAdapter { }

// Methods: snake_case
impl Agent {
    pub fn new() -> AgentBuilder { }
    pub async fn chat(&self, prompt: &str) -> Result<String> { }
    pub async fn start(&self, task: &str) -> Result<String> { }
}

// Builder methods: snake_case, consume self, return Self
impl AgentBuilder {
    pub fn name(mut self, name: &str) -> Self { }
    pub fn instructions(mut self, inst: &str) -> Self { }
    pub fn build(self) -> Result<Agent> { }
}

// Config structs: Suffix with Config
pub struct MemoryConfig { }
pub struct ExecutionConfig { }
pub struct OutputConfig { }
```

---

## 10. Testing

### 10.1 Run Tests

```bash
# All tests
cargo test

# Specific crate
cargo test -p praisonai
cargo test -p praisonai-derive
cargo test -p praisonai-cli

# With output
cargo test -- --nocapture

# Specific test
cargo test test_agent_builder
```

### 10.2 Test Structure

```
praisonai/src/
├── agent/
│   ├── mod.rs
│   └── builder.rs
├── config.rs       # Inline tests with #[cfg(test)]
└── tools/
    └── mod.rs      # Inline tests
```

### 10.3 Example Test

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_agent_builder_defaults() {
        let agent = Agent::new().build().unwrap();
        assert_eq!(agent.name(), "Agent");
        assert_eq!(agent.model(), "gpt-4o-mini");
    }

    #[tokio::test]
    async fn test_agent_chat() {
        let agent = Agent::new()
            .instructions("Be helpful")
            .build()
            .unwrap();
        // Mock the LLM provider for testing
    }
    
    #[test]
    fn test_memory_config_builder() {
        let config = MemoryConfig::new()
            .with_long_term()
            .provider("chroma")
            .max_messages(50);
        
        assert!(config.use_long_term);
        assert_eq!(config.provider, "chroma");
        assert_eq!(config.max_messages, 50);
    }
}
```

---

## 11. Building & Publishing

### 11.1 Build Commands

```bash
# Development build
cargo build

# Release build (optimized)
cargo build --release

# Check without building
cargo check

# Format code
cargo fmt

# Lint
cargo clippy
```

### 11.2 Publishing to crates.io

```bash
# Login (one-time)
cargo login <API_TOKEN>

# Publish in dependency order
cargo publish -p praisonai-derive
# wait ~1 min
cargo publish -p praisonai
# wait ~1 min
cargo publish -p praisonai-cli
```

### 11.3 Version Bumping

When releasing, update version in ALL crate Cargo.toml files and their cross-references:
- `Cargo.toml` (workspace)
- `praisonai/Cargo.toml`
- `praisonai-derive/Cargo.toml`
- `praisonai-cli/Cargo.toml`

---

## 12. CLI Parity Requirement

Every feature implemented must have a corresponding CLI representation:

```rust
// Pattern: If you add an API, add a CLI command
// Feature: Agent memory
// API: agent.clear_memory().await?
// CLI: praisonai-rust memory clear --session <id>
```

| Feature | API | CLI Equivalent |
|---------|-----|----------------|
| Chat | `agent.chat(prompt)` | `praisonai-rust chat` |
| Run workflow | `team.start(task)` | `praisonai-rust run workflow.yaml` |
| Single prompt | `agent.run(task)` | `praisonai-rust "prompt"` |

---

## 13. Verification Checklist

For every feature/change, verify:

- [ ] **Tests pass**: `cargo test`
- [ ] **Clippy clean**: `cargo clippy -- -D warnings`
- [ ] **Formatted**: `cargo fmt --check`
- [ ] **No heavy imports in core**: Check `praisonai/src/lib.rs`
- [ ] **Async-safe**: No blocking operations in async code
- [ ] **Multi-agent safe**: Thread-safe with `Send + Sync` bounds
- [ ] **CLI works**: `praisonai-rust --help` shows command
- [ ] **Docs updated**: Doc comments with examples

---

## 14. Documentation Standards

### 14.1 Doc Comments

All public APIs must have doc comments with:
- Description
- Example (runnable with `cargo test --doc`)
- Errors section if fallible

```rust
/// Creates an agent with the given instructions.
///
/// # Example
///
/// ```rust,ignore
/// use praisonai::Agent;
///
/// let agent = Agent::simple("Be helpful")?;
/// let response = agent.chat("Hello").await?;
/// ```
///
/// # Errors
///
/// Returns error if LLM provider is unavailable.
pub fn simple(instructions: impl Into<String>) -> Result<Self>
```

### 14.2 Mermaid Diagrams

Use two-color scheme for architecture diagrams:
- **Dark Red (#8B0000)**: Agents, inputs, outputs
- **Teal (#189AB4)**: Tools, utilities

```mermaid
graph LR
    A[Agent]:::agent --> B[Tool]:::tool
    B --> C[Result]:::agent
    classDef agent fill:#8B0000,color:#fff
    classDef tool fill:#189AB4,color:#fff
```

### 14.3 Beginner-Friendly

Documentation should make users feel: *"With just a few lines of code, I can do this!"*

```rust
// 3 lines to chat with AI
let agent = Agent::simple("Be helpful")?;
let response = agent.chat("Hello").await?;
println!("{}", response);
```

---

## 15. Free Core / Paid Upgrade Path

Design features so that:

| Aspect | Guideline |
|--------|------------|
| **Core remains free** | Essential agent functionality always open source |
| **Clear upgrade path** | Support, cloud, managed services as paid options |
| **Reduces friction** | Features reduce production risk, not just add functionality |
| **Safe by default** | Simple to adopt, hard to misuse |

---

## 16. Quick Reference

### 12.1 Core Imports

```rust
// Most common
use praisonai::{Agent, AgentTeam, tool};

// Configuration
use praisonai::config::{MemoryConfig, OutputConfig, ExecutionConfig, HooksConfig};

// Workflows
use praisonai::workflows::{AgentFlow, Route, Parallel, Loop, Repeat, Process, StepResult, WorkflowContext};

// Tools
use praisonai::tools::{Tool, ToolRegistry, ToolResult, ToolDefinition};

// LLM
use praisonai::llm::{LlmProvider, LlmConfig, Message, Role, LlmResponse};

// Memory
use praisonai::memory::{Memory, MemoryAdapter, ConversationHistory};

// Errors
use praisonai::error::{Error, Result};

// Prelude (all common types)
use praisonai::prelude::*;
```

### 12.2 File Locations

| What | Where |
|------|-------|
| Agent struct | `praisonai/src/agent/mod.rs` |
| AgentBuilder | `praisonai/src/agent/builder.rs` |
| Tool trait | `praisonai/src/tools/mod.rs` |
| ToolRegistry | `praisonai/src/tools/mod.rs` |
| #[tool] macro | `praisonai-derive/src/lib.rs` |
| LlmProvider | `praisonai/src/llm/mod.rs` |
| OpenAiProvider | `praisonai/src/llm/mod.rs` |
| AgentTeam | `praisonai/src/workflows/mod.rs` |
| AgentFlow | `praisonai/src/workflows/mod.rs` |
| MemoryConfig | `praisonai/src/config.rs` |
| Error types | `praisonai/src/error.rs` |
| CLI main | `praisonai-cli/src/main.rs` |
| CLI commands | `praisonai-cli/src/commands/` |

---

## 17. Feature Parity with Python SDK

Current implementation status tracked in `FEATURE_PARITY_TRACKER.json`.

| Feature | Status | Notes |
|---------|--------|-------|
| Agent (basic) | ✅ Complete | `Agent::new()`, `Agent::simple()` |
| Agent.chat() | ✅ Complete | With tool call loop |
| Agent.start() | ✅ Complete | Alias for chat |
| Agent.run() | ✅ Complete | Alias for chat |
| #[tool] macro | ✅ Complete | Proc-macro in derive crate |
| ToolRegistry | ✅ Complete | Register, execute, list |
| AgentTeam | ✅ Complete | Sequential, Parallel, Hierarchical |
| AgentFlow | ✅ Complete | Route, Parallel, Loop, Repeat |
| WorkflowContext | ✅ Complete | Variables, results |
| Memory | ✅ Basic | In-memory adapter |
| MemoryConfig | ✅ Complete | Short-term, long-term, provider |
| ExecutionConfig | ✅ Complete | Max iterations, timeout, stream |
| OutputConfig | ✅ Complete | Silent, verbose, json, file |
| CLI | ✅ Complete | chat, run, prompt commands |
| MCP Support | 🔲 Planned | |
| RAG/Knowledge | 🔲 Planned | |
| Specialized Agents | 🔲 Planned | Audio, Video, Vision |

---

## 18. Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `OPENAI_API_KEY` | OpenAI API authentication | Required |
| `PRAISONAI_MODEL` | Default model | `gpt-4o-mini` |
| `PRAISONAI_LOG` | Log level | `info` |
| `RUST_LOG` | Tracing log filter | - |

---

## 19. Performance Optimizations

The Rust SDK includes several performance optimizations:

```toml
# Cargo.toml release profile
[profile.release]
lto = true           # Link-time optimization
codegen-units = 1    # Single codegen unit for better optimization
strip = true         # Strip debug symbols
panic = "abort"      # Abort on panic (smaller binary)
```

---

*This document is the source of truth for the PraisonAI Rust SDK architecture and development guidelines.*
