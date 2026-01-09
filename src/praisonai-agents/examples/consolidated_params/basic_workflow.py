"""Basic workflow example with consolidated params."""
from praisonaiagents import Agent
from praisonaiagents.workflows import Workflow, WorkflowStep

# Create agents
writer = Agent(instructions="You are a content writer.")
editor = Agent(instructions="You are an editor.")

# Create workflow with consolidated params
workflow = Workflow(
    name="Content Pipeline",
    steps=[
        WorkflowStep(name="write", agent=writer, action="Write about {{topic}}"),
        WorkflowStep(name="edit", agent=editor, action="Edit the content", context=["write"]),
    ],
    output="verbose",
    planning=True,
)

if __name__ == "__main__":
    result = workflow.run(variables={"topic": "AI agents"})
    print(result)
