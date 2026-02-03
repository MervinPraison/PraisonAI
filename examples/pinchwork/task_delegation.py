"""
Task Delegation Example

Shows how a PraisonAI agent can delegate tasks to the Pinchwork marketplace.
"""

from praisonaiagents import Agent
from pinchwork_tools import PinchworkPostTask, PinchworkCheckStatus
import os

# Configure API key
api_key = os.getenv("PINCHWORK_API_KEY")

# Create an agent with Pinchwork tools
delegator = Agent(
    name="Project Manager",
    role="Task Delegator",
    goal="Break down complex projects and delegate to specialists",
    instructions="""
    You are a project manager who delegates tasks to the Pinchwork marketplace.
    When given a complex task, break it into smaller pieces and post them to Pinchwork.
    Use the PinchworkPostTask tool to post tasks with appropriate skills and credits.
    """,
    tools=[
        PinchworkPostTask(api_key=api_key),
        PinchworkCheckStatus(api_key=api_key)
    ]
)

# Agent autonomously delegates a coding task
result = delegator.start("""
We need to build a REST API endpoint. Please post this as a task on Pinchwork:
- Title: Build REST API endpoint
- Description: Create a POST /api/tasks endpoint with JSON validation using FastAPI and Pydantic
- Required skills: python, fastapi, pydantic
- Offer: 100 credits

After posting, check the status of the task.
""")

print(result)
