//! Memory configuration example
//!
//! Run with: cargo run -p praisonai --example memory_example

use praisonai::{Agent, MemoryConfig};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Create memory config with custom settings
    let memory_config = MemoryConfig::new()
        .with_long_term() // Enable long-term memory
        .provider("memory") // Use in-memory provider
        .max_messages(50); // Keep last 50 messages

    println!("Memory Config:");
    println!("  - Short-term: {}", memory_config.use_short_term);
    println!("  - Long-term: {}", memory_config.use_long_term);
    println!("  - Provider: {}", memory_config.provider);
    println!("  - Max messages: {}", memory_config.max_messages);

    // Create agent with memory config
    let agent = Agent::new()
        .name("memory-agent")
        .instructions("You are a helpful assistant that remembers our conversation.")
        .model("gpt-4o-mini")
        .memory_config(memory_config)
        .build()?;

    println!("\nAgent created: {}", agent.name());

    // Demonstrate memory operations
    println!("\nMemory operations:");

    // Get initial history (should be empty)
    let history = agent.history().await?;
    println!("  - Initial history count: {}", history.len());

    // Clear memory
    agent.clear_memory().await?;
    println!("  - Memory cleared");

    // Verify cleared
    let history = agent.history().await?;
    println!("  - History after clear: {}", history.len());

    println!("\nTo test with real API, set OPENAI_API_KEY and call agent.chat()");
    println!("The agent will remember previous messages in the conversation.");

    Ok(())
}
