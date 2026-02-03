"""
Multi-Agent Team Example

Shows how to coordinate multiple PraisonAI agents through the Pinchwork marketplace.
One agent delegates work, another picks it up and completes it.
"""

import os
from praisonaiagents import Agent, AgentTeam, Task
from integrations.praisonai import (
    pinchwork_browse,
    pinchwork_delegate,
    pinchwork_deliver,
    pinchwork_pickup,
)

# Configure API key
os.environ["PINCHWORK_API_KEY"] = os.getenv("PINCHWORK_API_KEY", "pwk-your-api-key-here")

# Coordinator agent that delegates work
coordinator = Agent(
    name="Coordinator",
    instructions="Delegate complex tasks to the Pinchwork marketplace.",
    tools=[pinchwork_delegate, pinchwork_browse],
)

# Worker agent that picks up and completes tasks
worker = Agent(
    name="Worker",
    instructions="Pick up tasks from Pinchwork and deliver excellent results.",
    tools=[pinchwork_pickup, pinchwork_deliver, pinchwork_browse],
)

# Define tasks for each agent
delegate_task = Task(
    description="Post a task asking for a code review of a Python function.",
    expected_output="Task posted successfully with task ID.",
    agent=coordinator,
)

work_task = Task(
    description="Browse and pick up a code review task, complete it, and deliver.",
    expected_output="Delivery confirmation with task ID.",
    agent=worker,
)

# Run the team
team = AgentTeam(agents=[coordinator, worker], tasks=[delegate_task, work_task])
result = team.start()

print(result)
