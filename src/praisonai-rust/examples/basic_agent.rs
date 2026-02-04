//! Basic agent example
//!
//! Run with: cargo run --example basic_agent

use praisonai::Agent;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Create a simple agent
    let agent = Agent::new()
        .name("assistant")
        .instructions("You are a helpful AI assistant. Be concise and friendly.")
        .model("gpt-4o-mini")
        .build()?;
    
    println!("Agent created: {}", agent.name());
    println!("Model: {}", agent.model());
    
    let response = agent.chat("What is 2 + 2?").await?;
    println!("Response: {}", response);
    
    Ok(())
}
