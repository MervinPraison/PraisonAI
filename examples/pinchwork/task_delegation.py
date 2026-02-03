"""
Task Delegation Example

Shows how a PraisonAI agent can delegate tasks to the Pinchwork marketplace.
"""

from praisonaiagents import Agent
import os

# Configure API key
api_key = os.getenv("PINCHWORK_API_KEY")

# Create an agent that delegates work
delegator = Agent(
    name="Project Manager",
    role="Task Delegator",
    goal="Break down complex projects and delegate to specialists",
    instructions="""
    You are a project manager who delegates tasks to the marketplace.
    For complex tasks, break them into smaller pieces and post to Pinchwork.
    """
)

# Import Pinchwork tools
from praisonai.integrations.pinchwork import post_task, check_task_status

# Delegate a coding task
task_result = post_task(
    api_key=api_key,
    title="Build REST API endpoint",
    description="Create a POST /api/tasks endpoint with JSON validation",
    skills=["python", "fastapi", "pydantic"],
    credits_offered=100
)

print(f"✅ Task posted: {task_result['task_id']}")
print(f"🔗 View at: https://pinchwork.dev/tasks/{task_result['task_id']}")

# Monitor task status
status = check_task_status(api_key=api_key, task_id=task_result['task_id'])
print(f"📊 Status: {status['status']}")
