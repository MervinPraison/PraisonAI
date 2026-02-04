//! PraisonAI Core - High-performance, agentic AI framework for Rust
//!
//! This crate provides the core functionality for building AI agents and multi-agent workflows.
//!
//! # Quick Start
//!
//! ```rust,ignore
//! use praisonai::{Agent, tool};
//!
//! #[tool(description = "Search the web")]
//! async fn search(query: String) -> String {
//!     format!("Results for: {}", query)
//! }
//!
//! #[tokio::main]
//! async fn main() -> anyhow::Result<()> {
//!     let agent = Agent::new()
//!         .instructions("You are a helpful assistant")
//!         .build();
//!     
//!     let response = agent.chat("Hello!").await?;
//!     println!("{}", response);
//!     Ok(())
//! }
//! ```
//!
//! # Architecture
//!
//! PraisonAI follows an agent-centric design with these core components:
//!
//! - **Agent**: The core execution unit that processes prompts and uses tools
//! - **Tool**: Functions that agents can call to perform actions
//! - **AgentTeam**: Coordinates multiple agents for complex workflows
//! - **AgentFlow**: Defines workflow patterns (sequential, parallel, etc.)
//! - **Memory**: Persists conversation history and context
//!
//! # Design Principles
//!
//! - **Agent-Centric**: Every design decision centers on Agents
//! - **Protocol-Driven**: Traits define contracts, implementations are pluggable
//! - **Minimal API**: Fewer parameters, sensible defaults
//! - **Performance-First**: Lazy loading, optional dependencies
//! - **Async-Safe**: All I/O operations are async

pub mod agent;
pub mod config;
pub mod error;
pub mod llm;
pub mod memory;
pub mod tools;
pub mod workflows;

// Re-export core types for simple API
pub use agent::{Agent, AgentBuilder, AgentConfig};
pub use config::{MemoryConfig, HooksConfig, OutputConfig, ExecutionConfig};
pub use error::{Error, Result};
pub use llm::{LlmProvider, LlmConfig, Message, Role};
pub use memory::{Memory, MemoryAdapter, ConversationHistory};
pub use tools::{Tool, ToolResult, ToolRegistry};
pub use workflows::{AgentTeam, AgentFlow, Route, Parallel, Loop, Repeat, Process, StepResult, WorkflowContext};

// Re-export the tool macro from praisonai-derive
pub use praisonai_derive::tool;

/// Prelude module for convenient imports
pub mod prelude {
    pub use crate::{
        Agent, AgentBuilder, AgentConfig,
        Tool, ToolResult, ToolRegistry,
        AgentTeam, AgentFlow, Route, Parallel, Loop, Repeat, Process,
        Memory, MemoryConfig,
        LlmProvider, LlmConfig, Message, Role,
        Error, Result,
        tool,
    };
}
