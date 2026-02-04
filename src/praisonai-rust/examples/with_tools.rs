//! Agent with tools example
//!
//! Run with: cargo run --example with_tools

use praisonai::{Agent, tool, Tool};

// Define a tool using the #[tool] macro
#[tool(description = "Get the current weather for a location")]
async fn get_weather(location: String) -> String {
    // In a real app, this would call a weather API
    format!("The weather in {} is sunny, 72°F", location)
}

// Another tool
#[tool(description = "Calculate the sum of two numbers")]
async fn add_numbers(a: i32, b: i32) -> i32 {
    a + b
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Create tools
    let weather_tool = GetWeatherTool::new();
    let add_tool = AddNumbersTool::new();
    
    println!("Tool: {} - {}", weather_tool.name(), weather_tool.description());
    println!("Tool: {} - {}", add_tool.name(), add_tool.description());
    
    // Create an agent with tools
    let agent = Agent::new()
        .name("tool-agent")
        .instructions("You are a helpful assistant with access to tools.")
        .model("gpt-4o-mini")
        .tool(weather_tool)
        .tool(add_tool)
        .build()?;
    
    println!("\nAgent created with {} tools", agent.tool_count().await);
    
    // Test tool execution directly
    let result = get_weather("San Francisco".to_string()).await;
    println!("Direct tool call: {}", result);
    
    let sum = add_numbers(5, 3).await;
    println!("Direct add call: {}", sum);
    
    println!("\nTo test with LLM, set OPENAI_API_KEY and call agent.chat()");
    
    Ok(())
}
