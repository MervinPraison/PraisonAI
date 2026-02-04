//! Configuration options example
//!
//! Run with: cargo run -p praisonai --example config_example

use praisonai::{Agent, OutputConfig, ExecutionConfig, MemoryConfig};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    println!("=== PraisonAI Configuration Examples ===\n");
    
    // 1. Output Configuration
    println!("1. Output Configuration:");
    let output_silent = OutputConfig::new().silent();
    let output_verbose = OutputConfig::new().verbose();
    let output_json = OutputConfig::new().json().file("output.json");
    
    println!("   - Silent mode: {}", output_silent.mode);
    println!("   - Verbose mode: {}", output_verbose.mode);
    println!("   - JSON mode: {}, file: {:?}", output_json.mode, output_json.file);
    
    // 2. Execution Configuration
    println!("\n2. Execution Configuration:");
    let exec_config = ExecutionConfig::new()
        .max_iterations(5)
        .timeout(60)
        .no_stream();
    
    println!("   - Max iterations: {}", exec_config.max_iterations);
    println!("   - Timeout: {} seconds", exec_config.timeout_secs);
    println!("   - Streaming: {}", exec_config.stream);
    
    // 3. Memory Configuration
    println!("\n3. Memory Configuration:");
    let mem_config = MemoryConfig::new()
        .with_long_term()
        .provider("sqlite")
        .max_messages(100);
    
    println!("   - Short-term: {}", mem_config.use_short_term);
    println!("   - Long-term: {}", mem_config.use_long_term);
    println!("   - Provider: {}", mem_config.provider);
    println!("   - Max messages: {}", mem_config.max_messages);
    
    // 4. Agent with all configurations
    println!("\n4. Creating Agent with Custom Config:");
    let agent = Agent::new()
        .name("configured-agent")
        .instructions("You are a configured assistant.")
        .model("gpt-4o-mini")
        .temperature(0.5)
        .max_tokens(1000)
        .max_iterations(3)
        .verbose(true)
        .stream(false)
        .memory_config(MemoryConfig::new().max_messages(20))
        .build()?;
    
    println!("   - Name: {}", agent.name());
    println!("   - Model: {}", agent.model());
    println!("   - Agent ID: {}", agent.id());
    
    println!("\n=== All configurations demonstrated successfully! ===");
    
    Ok(())
}
