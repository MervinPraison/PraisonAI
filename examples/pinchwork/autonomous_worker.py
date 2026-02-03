"""
Autonomous Worker Example

Shows how a PraisonAI agent can autonomously pick up and complete marketplace tasks.
"""

import os
from praisonaiagents import Agent
from integrations.praisonai import (
    pinchwork_browse,
    pinchwork_deliver,
    pinchwork_pickup,
)

# Configure API key
os.environ["PINCHWORK_API_KEY"] = os.getenv("PINCHWORK_API_KEY", "pwk-your-api-key-here")

# Create a worker agent
worker = Agent(
    name="Marketplace Worker",
    role="Task Completer",
    goal="Earn credits by completing high-quality work from the marketplace",
    instructions="""
    You are a skilled agent that earns credits by completing tasks on Pinchwork.
    
    Your workflow:
    1. Use pinchwork_browse to see what tasks are available
    2. Use pinchwork_pickup to claim a task that matches your skills
    3. Complete the work described in the task with high quality
    4. Use pinchwork_deliver to submit your completed work and earn credits
    
    Always deliver thorough, well-researched results.
    """,
    tools=[pinchwork_browse, pinchwork_pickup, pinchwork_deliver],
)

# Agent autonomously finds, claims, and completes a task
result = worker.start(
    "Browse available tasks on the Pinchwork marketplace, "
    "pick up a task that matches your skills, "
    "complete the work, "
    "and deliver your result."
)

print(result)
