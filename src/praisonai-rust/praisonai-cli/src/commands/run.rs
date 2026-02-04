//! Run workflow from YAML file

use anyhow::{Context, Result};
use praisonai::{Agent, AgentTeam, Process};
use serde::Deserialize;
use std::fs;
use std::path::Path;

/// Workflow definition from YAML
#[derive(Debug, Deserialize)]
struct WorkflowYaml {
    /// Workflow name
    #[serde(default)]
    name: Option<String>,
    
    /// Process type
    #[serde(default)]
    process: Option<String>,
    
    /// Agents in the workflow
    agents: Vec<AgentYaml>,
    
    /// Steps (optional, for explicit ordering)
    #[serde(default)]
    steps: Vec<StepYaml>,
}

/// Agent definition from YAML
#[derive(Debug, Deserialize)]
struct AgentYaml {
    /// Agent name
    name: String,
    
    /// Agent role/description
    #[serde(default)]
    role: Option<String>,
    
    /// Agent instructions
    #[serde(default)]
    instructions: Option<String>,
    
    /// Model to use
    #[serde(default)]
    model: Option<String>,
    
    /// Tools (names) - reserved for future tool integration
    #[serde(default)]
    #[allow(dead_code)]
    tools: Vec<String>,
}

/// Step definition from YAML
#[derive(Debug, Deserialize)]
struct StepYaml {
    /// Agent name for this step - reserved for explicit step ordering
    #[allow(dead_code)]
    agent: String,
    
    /// Action/task for this step
    #[serde(default)]
    action: Option<String>,
}

/// Run a workflow from a YAML file
pub async fn run(file: String, verbose: bool) -> Result<()> {
    let path = Path::new(&file);
    
    if !path.exists() {
        anyhow::bail!("File not found: {}", file);
    }
    
    let content = fs::read_to_string(path)
        .with_context(|| format!("Failed to read file: {}", file))?;
    
    let workflow: WorkflowYaml = serde_yaml::from_str(&content)
        .with_context(|| format!("Failed to parse YAML: {}", file))?;
    
    if verbose {
        println!("Loaded workflow: {}", workflow.name.as_deref().unwrap_or("unnamed"));
        println!("Agents: {}", workflow.agents.len());
    }
    
    // Build agents
    let mut team_builder = AgentTeam::new();
    
    for agent_yaml in &workflow.agents {
        let instructions = agent_yaml.instructions.clone()
            .or_else(|| agent_yaml.role.clone())
            .unwrap_or_else(|| format!("You are {}.", agent_yaml.name));
        
        let model = agent_yaml.model.clone()
            .unwrap_or_else(|| "gpt-4o-mini".to_string());
        
        let agent = Agent::new()
            .name(&agent_yaml.name)
            .instructions(&instructions)
            .model(&model)
            .build()?;
        
        if verbose {
            println!("  - {} ({})", agent_yaml.name, model);
        }
        
        team_builder = team_builder.agent(agent);
    }
    
    // Set process type
    let process = match workflow.process.as_deref() {
        Some("parallel") => Process::Parallel,
        Some("hierarchical") => Process::Hierarchical,
        _ => Process::Sequential,
    };
    
    let team = team_builder.process(process).verbose(verbose).build();
    
    if verbose {
        println!("Process: {:?}", process);
        println!("Running workflow...\n");
    }
    
    // Get the task from the first step or use a default
    let task = workflow.steps.first()
        .and_then(|s| s.action.clone())
        .unwrap_or_else(|| "Execute the workflow".to_string());
    
    // Run the workflow
    match team.start(&task).await {
        Ok(result) => {
            if verbose {
                println!("\n--- Result ---\n");
            }
            println!("{}", result);
            Ok(())
        }
        Err(e) => {
            eprintln!("Workflow failed: {}", e);
            std::process::exit(1);
        }
    }
}
