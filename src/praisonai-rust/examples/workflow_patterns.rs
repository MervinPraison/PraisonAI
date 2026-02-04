//! Workflow patterns example
//!
//! Run with: cargo run -p praisonai --example workflow_patterns

use praisonai::{Agent, AgentTeam, Process, WorkflowContext, StepResult};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    println!("=== PraisonAI Workflow Patterns ===\n");
    
    // Create reusable agents
    let _analyst = Agent::new()
        .name("analyst")
        .instructions("You analyze data and provide insights.")
        .model("gpt-4o-mini")
        .build()?;
    
    let _summarizer = Agent::new()
        .name("summarizer")
        .instructions("You create concise summaries.")
        .model("gpt-4o-mini")
        .build()?;
    
    let _reviewer = Agent::new()
        .name("reviewer")
        .instructions("You review and improve content quality.")
        .model("gpt-4o-mini")
        .build()?;
    
    // Pattern 1: Sequential Workflow
    println!("1. Sequential Workflow:");
    println!("   analyst -> summarizer -> reviewer");
    let sequential_team = AgentTeam::new()
        .agent(Agent::new().name("analyst").instructions("Analyze").model("gpt-4o-mini").build()?)
        .agent(Agent::new().name("summarizer").instructions("Summarize").model("gpt-4o-mini").build()?)
        .agent(Agent::new().name("reviewer").instructions("Review").model("gpt-4o-mini").build()?)
        .process(Process::Sequential)
        .build();
    println!("   Team size: {} agents", sequential_team.len());
    
    // Pattern 2: Parallel Workflow
    println!("\n2. Parallel Workflow:");
    println!("   [analyst, summarizer, reviewer] run simultaneously");
    let parallel_team = AgentTeam::new()
        .agent(Agent::new().name("analyst").instructions("Analyze").model("gpt-4o-mini").build()?)
        .agent(Agent::new().name("summarizer").instructions("Summarize").model("gpt-4o-mini").build()?)
        .agent(Agent::new().name("reviewer").instructions("Review").model("gpt-4o-mini").build()?)
        .process(Process::Parallel)
        .build();
    println!("   Team size: {} agents", parallel_team.len());
    
    // Pattern 3: Hierarchical Workflow
    println!("\n3. Hierarchical Workflow:");
    println!("   Manager validates each step before proceeding");
    let hierarchical_team = AgentTeam::new()
        .agent(Agent::new().name("researcher").instructions("Research").model("gpt-4o-mini").build()?)
        .agent(Agent::new().name("writer").instructions("Write").model("gpt-4o-mini").build()?)
        .process(Process::Hierarchical)
        .verbose(true)
        .build();
    println!("   Team size: {} agents", hierarchical_team.len());
    
    // Demonstrate workflow context
    println!("\n4. Workflow Context:");
    let mut context = WorkflowContext::new();
    context.set("task", "Analyze market trends");
    context.set("format", "bullet points");
    println!("   Variables set: task, format");
    println!("   Task: {:?}", context.get("task"));
    println!("   Format: {:?}", context.get("format"));
    
    // Demonstrate step results
    println!("\n5. Step Results:");
    let success = StepResult::success("analyst", "Analysis complete with 5 insights");
    let failure = StepResult::failure("reviewer", "Validation failed");
    println!("   Success: agent={}, success={}", success.agent, success.success);
    println!("   Failure: agent={}, success={}, error={:?}", failure.agent, failure.success, failure.error);
    
    println!("\n=== All workflow patterns demonstrated! ===");
    println!("\nTo run with real LLM, set OPENAI_API_KEY and call team.start(task)");
    
    Ok(())
}
