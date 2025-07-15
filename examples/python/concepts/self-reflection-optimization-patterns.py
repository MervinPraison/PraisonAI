"""
Self-Reflection Optimization Patterns Example

This example demonstrates self-reflection capabilities using PraisonAI's
built-in reflection features for iterative improvement and quality optimization.
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import internet_search

print("=== Self-Reflection Optimization Patterns Example ===\n")

# Create self-reflecting agent with built-in reflection capabilities
reflection_agent = Agent(
    name="Self-Reflecting Agent",
    role="Self-Improving Researcher",
    goal="Demonstrate self-reflection and iterative improvement patterns",
    backstory="Expert researcher with strong self-reflection and continuous improvement capabilities",
    tools=[internet_search],
    self_reflect=True,
    min_reflect=2,
    max_reflect=4,
    reflect_llm="gpt-4o-mini",
    verbose=True
)

# Create task that benefits from self-reflection
reflection_task = Task(
    description="""Research and analyze the future of artificial intelligence:
    1. Investigate current AI trends and breakthrough technologies
    2. Analyze potential impacts on society and industry
    3. Provide well-reasoned predictions for the next 5 years
    4. Ensure analysis is comprehensive, accurate, and well-structured
    
    Use self-reflection to improve the quality and completeness of your analysis.""",
    expected_output="Comprehensive AI future analysis with high quality through self-reflection",
    agent=reflection_agent
)

# Run with self-reflection optimization
print("Starting self-reflection optimization demonstration...")
result = reflection_agent.execute_task(reflection_task)

print(f"\nSelf-Reflection Result: {result[:200]}...")
print("\n✅ Self-reflection optimization complete!")
print("Agent demonstrated iterative improvement through built-in self-reflection capabilities.")