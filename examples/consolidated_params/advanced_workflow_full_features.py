"""Advanced Workflow with all consolidated params configured."""
from praisonaiagents import Agent
from praisonaiagents.workflows import Workflow, WorkflowStep
from praisonaiagents.workflows.workflow_configs import (
    WorkflowOutputConfig, WorkflowPlanningConfig, WorkflowMemoryConfig,
)

# Full-featured workflow with all consolidated params
workflow = Workflow(
    name="FullFeaturedWorkflow",
    description="Demonstrates all agent-like consolidated params",
    steps=[
        WorkflowStep(
            name="researcher",
            action="Research: {{input}}",
            agent=Agent(instructions="You are a researcher."),
            knowledge=["research_docs/"],  # Step-specific knowledge
            web="duckduckgo",  # Use DuckDuckGo for this step
        ),
        WorkflowStep(
            name="analyzer",
            action="Analyze the research",
            agent=Agent(instructions="You are an analyst."),
            reflection="thorough",  # Thorough reflection for analysis
            guardrails="strict",  # Strict validation
        ),
        WorkflowStep(
            name="writer",
            action="Write the final report",
            agent=Agent(instructions="You are a writer."),
            autonomy=True,  # Enable autonomy for writing
        ),
    ],
    # Workflow-level consolidated params
    output=WorkflowOutputConfig(output="verbose", stream=True),
    planning=WorkflowPlanningConfig(enabled=True, reasoning=True),
    memory=WorkflowMemoryConfig(backend="file"),
    # Agent-like params
    autonomy=True,
    knowledge=["shared_docs/"],
    guardrails=True,
    web=True,
    reflection=True,
)

if __name__ == "__main__":
    print(f"Workflow: {workflow.name}")
    print(f"Output verbose: {workflow._verbose}")
    print(f"Planning enabled: {workflow._planning_enabled}")
    print(f"Memory config: {workflow._memory_config}")
    print(f"Autonomy: {workflow.autonomy}")
    print(f"Knowledge: {workflow.knowledge}")
    print(f"Guardrails: {workflow.guardrails}")
    print(f"Web: {workflow.web}")
    print(f"Reflection: {workflow.reflection}")
