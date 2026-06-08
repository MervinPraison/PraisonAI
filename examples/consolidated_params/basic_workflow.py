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
    variables={"topic": "AI agents"},
)

if __name__ == "__main__":
    import os
    import sys

    if not os.environ.get("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY to run this example.")
        sys.exit(0)
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    result = workflow.run("AI agents")
    print(result)
