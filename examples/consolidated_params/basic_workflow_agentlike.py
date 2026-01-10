"""Basic Workflow with Agent-like consolidated params."""
from praisonaiagents import Agent
from praisonaiagents.workflows import Workflow, WorkflowStep

# Workflow with agent-like params (knowledge, web, guardrails, reflection)
workflow = Workflow(
    name="AgentLikeWorkflow",
    steps=[
        WorkflowStep(
            name="researcher",
            action="Research the topic: {{input}}",
            agent=Agent(instructions="You are a researcher."),
        ),
        WorkflowStep(
            name="writer",
            action="Write about the research findings",
            agent=Agent(instructions="You are a writer."),
        ),
    ],
    # Agent-like consolidated params
    knowledge=["docs/"],  # Enable RAG
    web=True,  # Enable web search
    guardrails=True,  # Enable guardrails
    reflection=True,  # Enable self-reflection
)

if __name__ == "__main__":
    print(f"Workflow: {workflow.name}")
    print(f"Knowledge: {workflow.knowledge}")
    print(f"Web: {workflow.web}")
    print(f"Guardrails: {workflow.guardrails}")
    print(f"Reflection: {workflow.reflection}")
