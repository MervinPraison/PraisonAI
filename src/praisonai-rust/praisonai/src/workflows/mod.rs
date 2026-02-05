//! Workflow system for PraisonAI
//!
//! This module provides multi-agent workflow patterns:
//! - AgentTeam: Coordinates multiple agents
//! - AgentFlow: Defines workflow execution patterns
//! - Route, Parallel, Loop, Repeat: Workflow patterns

use serde::{Deserialize, Serialize};
use std::sync::Arc;

use crate::agent::Agent;
use crate::error::{Error, Result};

/// Process type for workflow execution
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Process {
    /// Execute agents sequentially
    #[default]
    Sequential,
    /// Execute agents in parallel
    Parallel,
    /// Use hierarchical manager-based execution
    Hierarchical,
}

/// Step result from workflow execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StepResult {
    /// Agent name that produced this result
    pub agent: String,
    /// The output content
    pub output: String,
    /// Whether the step succeeded
    pub success: bool,
    /// Error message if failed
    pub error: Option<String>,
}

impl StepResult {
    /// Create a successful step result
    pub fn success(agent: impl Into<String>, output: impl Into<String>) -> Self {
        Self {
            agent: agent.into(),
            output: output.into(),
            success: true,
            error: None,
        }
    }

    /// Create a failed step result
    pub fn failure(agent: impl Into<String>, error: impl Into<String>) -> Self {
        Self {
            agent: agent.into(),
            output: String::new(),
            success: false,
            error: Some(error.into()),
        }
    }
}

/// Workflow context passed between agents
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct WorkflowContext {
    /// Variables available to all agents
    pub variables: std::collections::HashMap<String, String>,
    /// Results from previous steps
    pub results: Vec<StepResult>,
}

impl WorkflowContext {
    /// Create a new empty context
    pub fn new() -> Self {
        Self::default()
    }

    /// Set a variable
    pub fn set(&mut self, key: impl Into<String>, value: impl Into<String>) {
        self.variables.insert(key.into(), value.into());
    }

    /// Get a variable
    pub fn get(&self, key: &str) -> Option<&String> {
        self.variables.get(key)
    }

    /// Add a step result
    pub fn add_result(&mut self, result: StepResult) {
        // Also store as variable for next agent
        let var_name = format!("{}_output", result.agent);
        self.variables.insert(var_name, result.output.clone());
        self.results.push(result);
    }

    /// Get the last result
    pub fn last_result(&self) -> Option<&StepResult> {
        self.results.last()
    }
}

/// Agent team for multi-agent workflows
///
/// Coordinates multiple agents to work together on tasks.
///
/// # Example
///
/// ```rust,ignore
/// let team = AgentTeam::new()
///     .agent(researcher)
///     .agent(writer)
///     .process(Process::Sequential)
///     .build();
///
/// let result = team.start("Research and write about AI").await?;
/// ```
pub struct AgentTeam {
    agents: Vec<Arc<Agent>>,
    process: Process,
    verbose: bool,
}

impl AgentTeam {
    /// Check if verbose mode is enabled
    pub fn is_verbose(&self) -> bool {
        self.verbose
    }
}

impl AgentTeam {
    /// Create a new agent team builder
    #[allow(clippy::new_ret_no_self)]
    pub fn new() -> AgentTeamBuilder {
        AgentTeamBuilder::new()
    }

    /// Run the team with a task
    pub async fn start(&self, task: &str) -> Result<String> {
        match self.process {
            Process::Sequential => self.run_sequential(task).await,
            Process::Parallel => self.run_parallel(task).await,
            Process::Hierarchical => self.run_hierarchical(task).await,
        }
    }

    /// Alias for start
    pub async fn run(&self, task: &str) -> Result<String> {
        self.start(task).await
    }

    async fn run_sequential(&self, task: &str) -> Result<String> {
        let mut context = WorkflowContext::new();
        context.set("task", task);

        let mut current_input = task.to_string();

        for agent in &self.agents {
            // Build prompt with context
            let prompt = if context.results.is_empty() {
                current_input.clone()
            } else {
                let prev_output = context
                    .last_result()
                    .map(|r| r.output.as_str())
                    .unwrap_or("");
                format!("{}\n\nPrevious output:\n{}", current_input, prev_output)
            };

            match agent.chat(&prompt).await {
                Ok(output) => {
                    context.add_result(StepResult::success(agent.name(), &output));
                    current_input = output;
                }
                Err(e) => {
                    context.add_result(StepResult::failure(agent.name(), e.to_string()));
                    return Err(Error::workflow(format!(
                        "Agent {} failed: {}",
                        agent.name(),
                        e
                    )));
                }
            }
        }

        // Return the last output
        context
            .last_result()
            .map(|r| r.output.clone())
            .ok_or_else(|| Error::workflow("No results from workflow"))
    }

    async fn run_parallel(&self, task: &str) -> Result<String> {
        use futures::future::join_all;

        let futures: Vec<_> = self
            .agents
            .iter()
            .map(|agent| {
                let agent = Arc::clone(agent);
                let task = task.to_string();
                async move {
                    agent
                        .chat(&task)
                        .await
                        .map(|output| StepResult::success(agent.name(), output))
                        .unwrap_or_else(|e| StepResult::failure(agent.name(), e.to_string()))
                }
            })
            .collect();

        let results = join_all(futures).await;

        // Combine results
        let combined: Vec<String> = results
            .iter()
            .filter(|r| r.success)
            .map(|r| format!("## {}\n{}", r.agent, r.output))
            .collect();

        if combined.is_empty() {
            Err(Error::workflow("All agents failed"))
        } else {
            Ok(combined.join("\n\n"))
        }
    }

    async fn run_hierarchical(&self, task: &str) -> Result<String> {
        // For now, hierarchical is similar to sequential with validation
        // A manager agent would validate each step
        self.run_sequential(task).await
    }

    /// Get the number of agents
    pub fn len(&self) -> usize {
        self.agents.len()
    }

    /// Check if empty
    pub fn is_empty(&self) -> bool {
        self.agents.is_empty()
    }
}

impl Default for AgentTeam {
    fn default() -> Self {
        Self {
            agents: Vec::new(),
            process: Process::Sequential,
            verbose: false,
        }
    }
}

/// Builder for AgentTeam
pub struct AgentTeamBuilder {
    agents: Vec<Arc<Agent>>,
    process: Process,
    verbose: bool,
}

impl AgentTeamBuilder {
    /// Create a new builder
    pub fn new() -> Self {
        Self {
            agents: Vec::new(),
            process: Process::Sequential,
            verbose: false,
        }
    }

    /// Add an agent
    pub fn agent(mut self, agent: Agent) -> Self {
        self.agents.push(Arc::new(agent));
        self
    }

    /// Add an agent (Arc version)
    pub fn agent_arc(mut self, agent: Arc<Agent>) -> Self {
        self.agents.push(agent);
        self
    }

    /// Set the process type
    pub fn process(mut self, process: Process) -> Self {
        self.process = process;
        self
    }

    /// Enable verbose output
    pub fn verbose(mut self, enabled: bool) -> Self {
        self.verbose = enabled;
        self
    }

    /// Build the team
    pub fn build(self) -> AgentTeam {
        AgentTeam {
            agents: self.agents,
            process: self.process,
            verbose: self.verbose,
        }
    }
}

impl Default for AgentTeamBuilder {
    fn default() -> Self {
        Self::new()
    }
}

/// AgentFlow - Workflow definition with patterns
///
/// Defines complex workflow patterns like Route, Parallel, Loop.
pub struct AgentFlow {
    steps: Vec<FlowStep>,
}

/// A step in a workflow
pub enum FlowStep {
    /// Execute a single agent
    Agent(Arc<Agent>),
    /// Route to different agents based on condition
    Route(Route),
    /// Execute agents in parallel
    Parallel(Parallel),
    /// Loop over items
    Loop(Loop),
    /// Repeat a step
    Repeat(Repeat),
}

/// Route pattern - conditional branching
pub struct Route {
    /// Condition function
    pub condition: Box<dyn Fn(&str) -> bool + Send + Sync>,
    /// Agent to use if condition is true
    pub if_true: Arc<Agent>,
    /// Agent to use if condition is false
    pub if_false: Option<Arc<Agent>>,
}

/// Parallel pattern - concurrent execution
pub struct Parallel {
    /// Agents to run in parallel
    pub agents: Vec<Arc<Agent>>,
}

/// Loop pattern - iterate over items
pub struct Loop {
    /// Agent to execute for each item
    pub agent: Arc<Agent>,
    /// Items to iterate over
    pub items: Vec<String>,
}

/// Repeat pattern - repeat execution
pub struct Repeat {
    /// Agent to repeat
    pub agent: Arc<Agent>,
    /// Number of times to repeat
    pub times: usize,
}

impl AgentFlow {
    /// Create a new workflow
    pub fn new() -> Self {
        Self { steps: Vec::new() }
    }

    /// Add a step
    pub fn step(mut self, step: FlowStep) -> Self {
        self.steps.push(step);
        self
    }

    /// Add an agent step
    pub fn agent(self, agent: Agent) -> Self {
        self.step(FlowStep::Agent(Arc::new(agent)))
    }

    /// Execute the workflow
    pub async fn run(&self, input: &str) -> Result<String> {
        let mut current = input.to_string();

        for step in &self.steps {
            current = match step {
                FlowStep::Agent(agent) => agent.chat(&current).await?,
                FlowStep::Route(route) => {
                    if (route.condition)(&current) {
                        route.if_true.chat(&current).await?
                    } else if let Some(agent) = &route.if_false {
                        agent.chat(&current).await?
                    } else {
                        current
                    }
                }
                FlowStep::Parallel(parallel) => {
                    use futures::future::join_all;

                    let futures: Vec<_> =
                        parallel.agents.iter().map(|a| a.chat(&current)).collect();

                    let results = join_all(futures).await;
                    let outputs: Vec<String> = results.into_iter().filter_map(|r| r.ok()).collect();

                    outputs.join("\n\n")
                }
                FlowStep::Loop(loop_step) => {
                    let mut outputs = Vec::new();
                    for item in &loop_step.items {
                        let prompt = format!("{}\n\nItem: {}", current, item);
                        outputs.push(loop_step.agent.chat(&prompt).await?);
                    }
                    outputs.join("\n\n")
                }
                FlowStep::Repeat(repeat) => {
                    let mut output = current.clone();
                    for _ in 0..repeat.times {
                        output = repeat.agent.chat(&output).await?;
                    }
                    output
                }
            };
        }

        Ok(current)
    }
}

impl Default for AgentFlow {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_workflow_context() {
        let mut ctx = WorkflowContext::new();
        ctx.set("key", "value");
        assert_eq!(ctx.get("key"), Some(&"value".to_string()));
    }

    #[test]
    fn test_step_result() {
        let success = StepResult::success("agent1", "output");
        assert!(success.success);

        let failure = StepResult::failure("agent1", "error");
        assert!(!failure.success);
    }

    #[test]
    fn test_agent_team_builder() {
        let team = AgentTeam::new()
            .process(Process::Parallel)
            .verbose(true)
            .build();

        assert!(team.is_empty());
    }
}
