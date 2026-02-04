# AGENTS.md - PraisonAI Rust SDK Guide

> **For AI Agents and Developers**: Complete context for working with the PraisonAI Rust SDK, including architecture, crate structure, and development guidelines.

---

## 1. Overview

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
| **Production-Ready** | Async-first, error handling with `Result`, observability |

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
│       └── target/               # Build output (gitignored)

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

| Module | Purpose |
|--------|---------|
| `agent/` | Agent struct, AgentBuilder, execution |
| `tools/` | Tool trait, ToolRegistry, ToolResult |
| `llm/` | LlmProvider trait, OpenAI implementation |
| `memory/` | Memory trait, InMemoryAdapter, conversation history |
| `workflows/` | AgentTeam, AgentFlow, Step patterns |
| `config.rs` | MemoryConfig, OutputConfig, LlmConfig |
| `error.rs` | Error enum with thiserror |

### 3.2 Trait-Driven Design

Core SDK uses Rust traits for all extension points:

```rust
// Pattern: Traits define WHAT, implementations provide HOW
pub trait Tool: Send + Sync {
    fn name(&self) -> &str;
    fn description(&self) -> &str;
    fn parameters(&self) -> serde_json::Value;
    async fn execute(&self, args: serde_json::Value) -> Result<String>;
}

pub trait LlmProvider: Send + Sync {
    async fn complete(&self, messages: &[Message]) -> Result<String>;
    async fn complete_with_tools(&self, messages: &[Message], tools: &[&dyn Tool]) -> Result<LlmResponse>;
}

pub trait MemoryAdapter: Send + Sync {
    fn store(&mut self, message: Message);
    fn retrieve(&self, limit: usize) -> Vec<Message>;
    fn clear(&mut self);
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
thiserror = "2"                                    # Error handling
anyhow = "1"                                       # Error context
rig-core = "0.9"                                   # LLM providers
clap = { version = "4", features = ["derive"] }   # CLI parsing
tracing = "0.1"                                    # Logging
uuid = { version = "1", features = ["v4"] }       # Session IDs
```

---

## 4. API Design

> **Philosophy**: Match Python SDK's simplicity — the simplest use case should be the shortest code.

### 4.1 One-Liner (Simplest)

```rust
use praisonai::Agent;

// Equivalent to Python: Agent(instructions="Be helpful")
let agent = Agent::simple("Be helpful")?;
let response = agent.chat("Hello!").await?;
```

### 4.2 Builder Pattern (More Control)

```rust
use praisonai::Agent;

let agent = Agent::new()
    .name("assistant")
    .instructions("You are a helpful AI assistant")
    .build()?;

let response = agent.chat("What is 2+2?").await?;
// Also available: agent.start() and agent.run() as aliases
```

### 4.3 With Tools

```rust
use praisonai::{Agent, tool};

#[tool(description = "Search the web")]
async fn search(query: String) -> String {
    format!("Results for: {}", query)
}

let agent = Agent::new()
    .instructions("Use search to help users")
    .tool(search)
    .build()?;

let response = agent.chat("Find info about Rust").await?;
```

### 4.4 Multi-Agent Team

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

### 4.5 Workflow Patterns (AgentFlow)

```rust
use praisonai::{Agent, AgentFlow, FlowStep, Route, Parallel, Repeat};
use std::sync::Arc;

let agent = Arc::new(Agent::simple("Be helpful")?);

// Simple agent step
let flow = AgentFlow::new()
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

### 4.6 Progressive Disclosure Summary

| Level | Code | Use Case |
|-------|------|----------|
| **Simplest** | `Agent::simple("instructions")?` | Quick prototyping |
| **Basic** | `Agent::new().instructions(...).build()?` | Most apps |
| **With Tools** | `Agent::new()...tool(fn).build()?` | Tool-using agents |
| **Team** | `AgentTeam::new().agent(...).build()` | Multi-agent |
| **Flows** | `AgentFlow::new().step(...)` | Complex patterns |

---

## 5. CLI Usage

### 5.1 Commands

```bash
# Interactive chat
praisonai-rust chat

# Run from YAML workflow
praisonai-rust run workflow.yaml

# Single prompt
praisonai-rust "What is 2+2?"

# With specific model
praisonai-rust --model gpt-4o "Explain quantum computing"
```

### 5.2 YAML Workflow Format

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

## 6. Extension Points

### 6.1 Custom Tools

```rust
// Using #[tool] macro (recommended)
#[tool(description = "Calculate mathematical expressions")]
async fn calculate(expression: String) -> String {
    // Implementation
}

// Manual implementation
struct MyTool;

impl Tool for MyTool {
    fn name(&self) -> &str { "my_tool" }
    fn description(&self) -> &str { "Does something useful" }
    fn parameters(&self) -> serde_json::Value {
        json!({
            "type": "object",
            "properties": {
                "input": { "type": "string" }
            }
        })
    }
    async fn execute(&self, args: serde_json::Value) -> Result<String> {
        Ok("Result".to_string())
    }
}
```

### 6.2 Custom LLM Providers

```rust
use praisonai::llm::{LlmProvider, Message, LlmResponse};

struct MyProvider {
    api_key: String,
}

#[async_trait]
impl LlmProvider for MyProvider {
    async fn complete(&self, messages: &[Message]) -> Result<String> {
        // Call your LLM API
    }
    
    async fn complete_with_tools(
        &self,
        messages: &[Message],
        tools: &[&dyn Tool],
    ) -> Result<LlmResponse> {
        // Handle tool calls
    }
}
```

### 6.3 Custom Memory Adapters

```rust
use praisonai::memory::{MemoryAdapter, Message};

struct RedisMemory {
    client: redis::Client,
}

impl MemoryAdapter for RedisMemory {
    fn store(&mut self, message: Message) {
        // Store in Redis
    }
    fn retrieve(&self, limit: usize) -> Vec<Message> {
        // Retrieve from Redis
    }
    fn clear(&mut self) {
        // Clear Redis keys
    }
}
```

---

## 7. Development Guidelines

### 7.1 Core Principles (MUST)

| Principle | Description |
|-----------|-------------|
| **Trait-driven** | Use traits for all extension points |
| **Result everywhere** | All fallible operations return `Result<T, Error>` |
| **Async-first** | All I/O is async with tokio |
| **Builder pattern** | Complex structs use builders |
| **Zero unsafe** | No unsafe code without explicit justification |

### 7.2 Error Handling

```rust
// Use thiserror for error types
#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("LLM error: {0}")]
    Llm(String),
    
    #[error("Tool execution failed: {0}")]
    Tool(String),
    
    #[error("Configuration error: {0}")]
    Config(String),
}

// Use anyhow for application code
use anyhow::{Context, Result};

fn load_config() -> Result<Config> {
    let content = fs::read_to_string("config.yaml")
        .context("Failed to read config file")?;
    Ok(serde_yaml::from_str(&content)?)
}
```

### 7.3 Naming Conventions

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

// Builder methods: snake_case, return Self
impl AgentBuilder {
    pub fn name(mut self, name: &str) -> Self { }
    pub fn instructions(mut self, inst: &str) -> Self { }
    pub fn build(self) -> Result<Agent> { }
}
```

---

## 8. Testing

### 8.1 Run Tests

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

### 8.2 Test Structure

```
praisonai/src/
├── agent/
│   ├── mod.rs
│   ├── builder.rs
│   └── tests.rs      # Unit tests in separate file
│                     # OR #[cfg(test)] mod tests { } inline
```

### 8.3 Example Test

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
}
```

---

## 9. Building & Publishing

### 9.1 Build Commands

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

### 9.2 Publishing to crates.io

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

### 9.3 Version Bumping

When releasing, update version in ALL crate Cargo.toml files and their cross-references:
- `Cargo.toml` (workspace)
- `praisonai/Cargo.toml`
- `praisonai-derive/Cargo.toml`
- `praisonai-cli/Cargo.toml`

---

## 10. Documentation

### 10.1 Locations

| Type | Location |
|------|----------|
| **API Docs** | `cargo doc --open` (generated) |
| **User Docs** | `/Users/praison/PraisonAIDocs/docs/rust/` (Mintlify) |
| **Examples** | `/Users/praison/praisonai-package/examples/rust/` |
| **This Guide** | `src/praisonai-rust/AGENTS.md` |

### 10.2 Doc Comments

```rust
/// Creates a new Agent with the given configuration.
///
/// # Examples
///
/// ```rust
/// use praisonai::Agent;
///
/// let agent = Agent::new()
///     .name("assistant")
///     .instructions("Be helpful")
///     .build()?;
/// ```
///
/// # Errors
///
/// Returns an error if the configuration is invalid.
pub fn build(self) -> Result<Agent> {
    // ...
}
```

---

## 11. Quick Reference

### 11.1 Core Imports

```rust
// Most common
use praisonai::{Agent, AgentTeam, tool};

// Configuration
use praisonai::config::{MemoryConfig, OutputConfig, LlmConfig};

// Workflows
use praisonai::workflows::{AgentFlow, Pattern, Process, Step};

// Tools
use praisonai::tools::{Tool, ToolRegistry, ToolResult};

// LLM
use praisonai::llm::{LlmProvider, Message, OpenAiProvider};

// Memory
use praisonai::memory::{MemoryAdapter, InMemoryAdapter};

// Errors
use praisonai::error::{Error, Result};
```

### 11.2 File Locations

| What | Where |
|------|-------|
| Agent struct | `praisonai/src/agent/mod.rs` |
| AgentBuilder | `praisonai/src/agent/builder.rs` |
| Tool trait | `praisonai/src/tools/mod.rs` |
| #[tool] macro | `praisonai-derive/src/lib.rs` |
| LlmProvider | `praisonai/src/llm/mod.rs` |
| AgentTeam | `praisonai/src/workflows/mod.rs` |
| CLI main | `praisonai-cli/src/main.rs` |
| CLI commands | `praisonai-cli/src/commands/` |

---

## 12. Feature Parity with Python SDK

Current implementation status tracked in `FEATURE_PARITY_TRACKER.json`.

| Feature | Status |
|---------|--------|
| Agent (basic) | ✅ Complete |
| Agent.chat() | ✅ Complete |
| Agent.start() | ✅ Complete |
| #[tool] macro | ✅ Complete |
| AgentTeam | ✅ Complete |
| AgentFlow | ✅ Complete |
| Memory | ✅ Basic |
| CLI | ✅ Complete |
| MCP Support | 🔲 Planned |
| RAG/Knowledge | 🔲 Planned |
| Specialized Agents | 🔲 Planned |

---

## 13. Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `OPENAI_API_KEY` | OpenAI API authentication | Required |
| `PRAISONAI_MODEL` | Default model | `gpt-4o-mini` |
| `PRAISONAI_LOG` | Log level | `info` |
| `RUST_LOG` | Tracing log filter | - |

---

*This document is the source of truth for the PraisonAI Rust SDK architecture and development guidelines.*
