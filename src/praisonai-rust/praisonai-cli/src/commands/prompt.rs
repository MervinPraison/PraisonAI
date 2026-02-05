//! Single-shot prompt command

use anyhow::Result;
use praisonai::Agent;

/// Run a single prompt
pub async fn run(text: String, model: String) -> Result<()> {
    let agent = Agent::new()
        .name("assistant")
        .instructions("You are a helpful AI assistant. Be concise and direct.")
        .model(&model)
        .memory(false) // No memory needed for single-shot
        .build()?;

    match agent.chat(&text).await {
        Ok(response) => {
            println!("{}", response);
            Ok(())
        }
        Err(e) => {
            eprintln!("Error: {}", e);
            std::process::exit(1);
        }
    }
}
