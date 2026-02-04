//! Multi-agent workflow example
//!
//! Run with: cargo run --example multi_agent

use praisonai::{Agent, AgentTeam, Process};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Create specialized agents
    let researcher = Agent::new()
        .name("researcher")
        .instructions("You are a research specialist. Find and summarize information.")
        .model("gpt-4o-mini")
        .build()?;
    
    let writer = Agent::new()
        .name("writer")
        .instructions("You are a skilled writer. Take research and create engaging content.")
        .model("gpt-4o-mini")
        .build()?;
    
    let editor = Agent::new()
        .name("editor")
        .instructions("You are an editor. Review and polish the content for clarity.")
        .model("gpt-4o-mini")
        .build()?;
    
    // Create a team with sequential process
    let team = AgentTeam::new()
        .agent(researcher)
        .agent(writer)
        .agent(editor)
        .process(Process::Sequential)
        .verbose(true)
        .build();
    
    println!("Team created with {} agents", team.len());
    println!("Process: Sequential (researcher -> writer -> editor)");
    
    // Run the workflow
    // Note: Requires OPENAI_API_KEY environment variable
    // let result = team.start("Write a blog post about Rust programming").await?;
    // println!("Final output:\n{}", result);
    
    println!("\nTo test with real API, set OPENAI_API_KEY and uncomment the start() call.");
    
    Ok(())
}
