//! Interactive chat command

use anyhow::Result;
use praisonai::Agent;
use std::io::{self, Write};

/// Run interactive chat session
pub async fn run(model: String, instructions: Option<String>) -> Result<()> {
    let instructions = instructions
        .unwrap_or_else(|| "You are a helpful AI assistant. Be concise and helpful.".to_string());

    let agent = Agent::new()
        .name("assistant")
        .instructions(&instructions)
        .model(&model)
        .build()?;

    println!("PraisonAI Chat (model: {})", model);
    println!("Type 'exit' or 'quit' to end the session.");
    println!("Type '/clear' to clear conversation history.");
    println!();

    loop {
        // Print prompt
        print!("You: ");
        io::stdout().flush()?;

        // Read input
        let mut input = String::new();
        io::stdin().read_line(&mut input)?;
        let input = input.trim();

        // Check for exit commands
        if input.is_empty() {
            continue;
        }

        if input == "exit" || input == "quit" || input == "/exit" || input == "/quit" {
            println!("Goodbye!");
            break;
        }

        if input == "/clear" {
            agent.clear_memory().await?;
            println!("Conversation cleared.");
            continue;
        }

        if input == "/help" {
            println!("Commands:");
            println!("  /clear  - Clear conversation history");
            println!("  /help   - Show this help");
            println!("  /exit   - Exit chat");
            continue;
        }

        // Get response from agent
        match agent.chat(input).await {
            Ok(response) => {
                println!("\nAssistant: {}\n", response);
            }
            Err(e) => {
                eprintln!("\nError: {}\n", e);
            }
        }
    }

    Ok(())
}
