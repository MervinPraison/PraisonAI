"""
Advanced Memory Search and Optimization Example

This example demonstrates memory search optimization using PraisonAI's
built-in memory capabilities with semantic search and quality filtering.
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import internet_search

print("=== Advanced Memory Search and Optimization Example ===\n")

# Configure optimized memory settings
memory_config = {
    "provider": "mem0",
    "config": {
        "vector_store": {
            "provider": "chroma",
            "config": {
                "path": ".praison/optimized_memory"
            }
        }
    }
}

# Create research agent with optimized memory
research_agent = Agent(
    name="Memory Research Agent",
    role="Information Researcher with Memory Optimization",
    goal="Research and demonstrate optimized memory search patterns",
    backstory="Expert at storing and retrieving information efficiently with memory optimization",
    tools=[internet_search],
    memory=True,
    verbose=True
)

# Task to build searchable memory
build_memory_task = Task(
    description="""Research and store information about these topics for later search:
    1. Artificial intelligence market trends and growth data
    2. Machine learning technologies and applications
    3. Tech industry partnerships and investments
    4. Cloud computing adoption statistics
    
    Store detailed information that can be searched later.""",
    expected_output="Comprehensive research stored in optimized memory",
    agent=research_agent
)

# Task to demonstrate memory search optimization
search_task = Task(
    description="""Using the stored memory, perform optimized searches for:
    1. "AI market growth trends" - find relevant stored information
    2. "technology partnerships" - retrieve partnership data
    3. "cloud adoption statistics" - search for cloud computing info
    
    Demonstrate efficient memory retrieval and search optimization.""",
    expected_output="Results from optimized memory searches",
    agent=research_agent
)

# Run with memory optimization
agents_system = PraisonAIAgents(
    agents=[research_agent],
    tasks=[build_memory_task, search_task],
    memory=True,
    memory_config=memory_config,
    verbose=True
)

print("Starting memory search optimization demonstration...")
result = agents_system.start()

print(f"\nMemory Search Result: {result[:200]}...")
print("\n✅ Memory search optimization complete!")
print("Agent demonstrated efficient memory storage and optimized search retrieval.")