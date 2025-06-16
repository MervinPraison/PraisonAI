from praisonaiagents import Agent, Task, TaskOutput, PraisonAIAgents
from typing import Tuple, Any

def validate_content(task_output: TaskOutput) -> Tuple[bool, Any]:
    if len(task_output.raw) < 50:
        return False, "Content too short"
    return True, task_output

agent = Agent(
    instructions="You are a writer",
)

task = Task(
    description="Write a welcome message",
    guardrail=validate_content,
    agent=agent
)

praison_agents = PraisonAIAgents(agents=[agent], tasks=[task])

praison_agents.start()
