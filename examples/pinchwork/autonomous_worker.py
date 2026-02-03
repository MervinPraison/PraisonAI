"""
Autonomous Worker Example

Shows how a PraisonAI agent can autonomously pick up and complete marketplace tasks.
"""

from praisonaiagents import Agent
import os

api_key = os.getenv("PINCHWORK_API_KEY")

# Create a worker agent
worker = Agent(
    name="Python Developer",
    role="Marketplace Worker",
    goal="Complete Python coding tasks from the marketplace",
    instructions="""
    You are a Python developer who picks up coding tasks from Pinchwork.
    Choose tasks that match your skills and complete them with quality code.
    """
)

from praisonai.integrations.pinchwork import (
    get_available_tasks,
    claim_task,
    complete_task
)

# Find available tasks
print("🔍 Searching for tasks...")
tasks = get_available_tasks(
    api_key=api_key,
    skills=["python"],
    limit=5
)

if not tasks:
    print("❌ No tasks available")
    exit()

# Pick the highest-paying task
task = max(tasks, key=lambda t: t['credits_offered'])
print(f"✅ Found task: {task['title']} ({task['credits_offered']} credits)")

# Claim the task
claim_result = claim_task(api_key=api_key, task_id=task['id'])
print(f"🎯 Task claimed!")

# Complete the task (using the worker agent)
result = worker.start(f"Complete this task: {task['description']}")

# Submit completion
complete_result = complete_task(
    api_key=api_key,
    task_id=task['id'],
    result=result
)

print(f"🎉 Task completed! Earned {complete_result['credits_earned']} credits")
