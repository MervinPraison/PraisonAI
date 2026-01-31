"""Basic workflow example with consolidated params."""
from praisonaiagents import Agent
from praisonaiagents import AgentFlow, Task

# Create agents
writer = Agent(instructions="You are a content writer.")
editor = Agent(instructions="You are an editor.")

# Create workflow with consolidated params
workflow = AgentFlow(
    name="Content Pipeline",
    steps=[
        Task(name="write", agent=writer, action="Write about {{topic}}"),
        Task(name="edit", agent=editor, action="Edit the content", context=["write"]),
    ],
    output="verbose",
    planning=True,
)

if __name__ == "__main__":
    result = workflow.run(variables={"topic": "AI agents"})
    print(result)
