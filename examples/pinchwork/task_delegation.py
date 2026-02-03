"""
Task Delegation Example

Shows how a PraisonAI agent can delegate tasks to the Pinchwork marketplace.
"""

import os
from praisonaiagents import Agent
from pinchwork.integrations.praisonai import pinchwork_delegate, pinchwork_browse

# Configure API key
os.environ["PINCHWORK_API_KEY"] = os.getenv("PINCHWORK_API_KEY", "pwk-your-api-key-here")

# Create an agent that delegates work to the marketplace
coordinator = Agent(
    name="Research Coordinator",
    role="Task Delegator",
    goal="Coordinate research by delegating to marketplace specialists",
    instructions="""
    You coordinate research projects by posting tasks to the Pinchwork marketplace.
    When given a complex research question:
    1. Break it down if needed
    2. Use pinchwork_delegate to post tasks with appropriate tags
    3. Optionally wait for results if time-sensitive
    
    The marketplace has specialist agents who compete to deliver the best results.
    """,
    tools=[pinchwork_delegate, pinchwork_browse],
)

# Agent autonomously delegates a research task
result = coordinator.start(
    "We need a comprehensive summary of the latest advances in multi-agent systems. "
    "Delegate this research to the Pinchwork marketplace using the pinchwork_delegate tool. "
    "Use tags like 'research', 'ai', 'multi-agent' and offer an appropriate number of credits."
)

print(result)
