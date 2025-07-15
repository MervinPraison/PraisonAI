"""
Advanced Graph Memory Integration Example

This example demonstrates graph memory capabilities with PraisonAI agents
for knowledge graph construction and relationship-aware memory retrieval.
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import internet_search

print("=== Advanced Graph Memory Integration Example ===\n")

# Configure simple graph memory
memory_config = {
    "provider": "mem0",
    "config": {
        "vector_store": {
            "provider": "chroma",
            "config": {
                "path": ".praison/graph_memory"
            }
        }
    }
}

# Create knowledge builder agent with graph memory
knowledge_agent = Agent(
    name="Knowledge Agent",
    role="Knowledge Graph Builder", 
    goal="Build and retrieve from knowledge graphs",
    backstory="Expert at creating structured knowledge and finding relationships",
    tools=[internet_search],
    memory=True,
    verbose=True
)

# Task to build knowledge graph about AI companies
build_task = Task(
    description="""Research and store information about major AI companies and their relationships:
    1. OpenAI - products like GPT-4, ChatGPT, leadership, partnerships
    2. Anthropic - Claude AI, safety focus, team
    3. Relationships between these companies and their technologies
    
    Focus on capturing connections and relationships between entities.""",
    expected_output="Knowledge graph with AI company ecosystem relationships",
    agent=knowledge_agent
)

# Task to query the knowledge graph
query_task = Task(
    description="""Using the stored knowledge graph, answer:
    1. What are the main products of each company?
    2. Who are the key leaders in these companies?
    3. How do these companies relate to each other?
    
    Use relationship-aware memory retrieval.""",
    expected_output="Analysis using graph memory relationships",
    agent=knowledge_agent
)

# Run with graph memory integration
agents_system = PraisonAIAgents(
    agents=[knowledge_agent],
    tasks=[build_task, query_task],
    memory=True,
    memory_config=memory_config,
    verbose=True
)

print("Starting graph memory demonstration...")
result = agents_system.start()

print(f"\nGraph Memory Result: {result[:200]}...")
print("\n✅ Graph memory integration complete!")
print("Agent built knowledge graph and performed relationship-aware queries.")