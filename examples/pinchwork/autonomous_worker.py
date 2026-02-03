"""
Autonomous Worker Example

Shows how a PraisonAI agent can autonomously pick up and complete marketplace tasks.
"""

from praisonaiagents import Agent
from pinchwork_tools import (
    PinchworkGetTasks,
    PinchworkClaimTask,
    PinchworkCompleteTask
)
import os

api_key = os.getenv("PINCHWORK_API_KEY")

# Create a worker agent with Pinchwork tools
worker = Agent(
    name="Python Developer",
    role="Marketplace Worker",
    goal="Complete Python coding tasks from the marketplace",
    instructions="""
    You are a Python developer who autonomously works on the Pinchwork marketplace.
    
    Your workflow:
    1. Use PinchworkGetTasks to find available Python tasks
    2. Review the tasks and pick the one that best matches your skills
    3. Use PinchworkClaimTask to claim it
    4. Complete the work (write code, tests, documentation as needed)
    5. Use PinchworkCompleteTask to submit your work and earn credits
    
    Always write high-quality code with proper documentation.
    """,
    tools=[
        PinchworkGetTasks(api_key=api_key),
        PinchworkClaimTask(api_key=api_key),
        PinchworkCompleteTask(api_key=api_key)
    ]
)

# Agent autonomously finds and completes a task
result = worker.start("""
Find a Python task on Pinchwork that you can complete.
Claim it, do the work, and submit the completed result.
""")

print(result)
