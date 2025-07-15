"""
Advanced Callback Systems Example

This example demonstrates callback systems using PraisonAI's built-in
callback functionality for monitoring agent interactions and tool usage.
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.display_callback import register_display_callback
from praisonaiagents.tools import internet_search

print("=== Advanced Callback Systems Example ===\n")

# Simple callback function to monitor interactions
def interaction_callback(data):
    """Monitor agent interactions"""
    print(f"📋 Interaction: {data.get('agent_name', 'Unknown')} - {data.get('type', 'unknown')}")

# Simple callback function to monitor tool usage
def tool_callback(data):
    """Monitor tool usage"""
    print(f"🔧 Tool Used: {data.get('agent_name', 'Unknown')} used {data.get('tool_name', 'unknown')}")

# Simple callback function to monitor generation
def generation_callback(data):
    """Monitor content generation"""
    print(f"✍️  Generation: {data.get('agent_name', 'Unknown')} generating content")

# Register callbacks with PraisonAI's callback system
print("Registering callbacks...")
register_display_callback('interaction', interaction_callback)
register_display_callback('tool_call', tool_callback)
register_display_callback('generating', generation_callback)
print("✅ Callbacks registered\n")

# Create a research agent with callback monitoring
research_agent = Agent(
    name="Research Agent",
    role="Information Researcher",
    goal="Research topics and demonstrate callback monitoring",
    backstory="Expert researcher that demonstrates callback functionality",
    tools=[internet_search],
    verbose=True
)

# Create a simple task
research_task = Task(
    description="Research the latest developments in renewable energy technology",
    expected_output="Brief summary of renewable energy developments",
    agent=research_agent
)

# Execute with callback monitoring
print("Starting research with callback monitoring...")
result = research_agent.execute_task(research_task)

print(f"\nResearch Result: {result[:200]}...")
print("\n✅ Callback monitoring demonstration complete!")
print("Callbacks successfully tracked agent interactions, tool usage, and content generation.")