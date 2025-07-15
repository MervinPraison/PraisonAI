"""
Advanced State Management Patterns Example

This example demonstrates state management using PraisonAI agents
with session-based state tracking and persistence.
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import internet_search

print("=== Advanced State Management Patterns Example ===\n")

# Configure session state for persistence
session_config = {
    "session_id": "state_demo_001",
    "persist": True
}

# Create agent with state management
state_agent = Agent(
    name="State Manager Agent",
    role="State-Aware Task Manager",
    goal="Demonstrate advanced state management patterns",
    backstory="Expert at managing task state and workflow progression with memory",
    tools=[internet_search],
    memory=True,
    verbose=True
)

# Task 1: Initialize state and perform research
init_task = Task(
    description="""Initialize project state and research electric vehicle market:
    1. Set project phase to 'research'
    2. Store initial findings about EV market size and growth
    3. Track research progress and key insights
    
    Remember the state for subsequent tasks.""",
    expected_output="Research results with initialized state tracking",
    agent=state_agent
)

# Task 2: Continue with state awareness
continue_task = Task(
    description="""Continue from previous state and expand analysis:
    1. Review stored research state from previous task
    2. Analyze competitive landscape based on stored information
    3. Update project phase to 'analysis'
    4. Store competitive insights for next phase
    
    Build upon previously stored state.""",
    expected_output="Competitive analysis building on stored state",
    agent=state_agent
)

# Task 3: Finalize using accumulated state
finalize_task = Task(
    description="""Complete project using all accumulated state:
    1. Review all stored research and analysis
    2. Create final recommendations based on complete state
    3. Set project phase to 'completed'
    
    Use all accumulated state from previous tasks.""",
    expected_output="Final recommendations using complete project state",
    agent=state_agent
)

# Run with state management
agents_system = PraisonAIAgents(
    agents=[state_agent],
    tasks=[init_task, continue_task, finalize_task],
    memory=True,
    verbose=True
)

print("Starting state management demonstration...")
result = agents_system.start()

print(f"\nState Management Result: {result[:200]}...")
print("\n✅ State management patterns complete!")
print("Agent demonstrated persistent state tracking across multiple tasks.")