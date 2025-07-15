"""
Advanced Graph Memory Integration Example

This example demonstrates comprehensive graph memory capabilities including
knowledge graph construction, multi-agent shared memory, and graph-based reasoning.
"""

from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.memory import GraphMemory
from praisonaiagents.tools import internet_search, read_file

print("=== Advanced Graph Memory Integration Example ===\n")

# Configure graph memory with multiple backends
graph_memory_config = {
    "provider": "graph",
    "graph_store": {
        "provider": "networkx",  # or "neo4j" for production
        "config": {
            "persistent": True,
            "auto_save": True,
            "memory_file": "knowledge_graph.pkl"
        }
    },
    "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
    "enable_reasoning": True,
    "max_hops": 3
}

# Initialize shared graph memory
shared_memory = GraphMemory(config=graph_memory_config)

# Example 1: Knowledge Graph Construction Agent
print("Example 1: Knowledge Graph Construction")
print("-" * 40)

knowledge_builder = Agent(
    name="Knowledge Builder",
    role="Knowledge Graph Constructor", 
    goal="Build and maintain a comprehensive knowledge graph",
    backstory="Expert at extracting entities, relationships, and building knowledge structures",
    instructions="""Extract entities, relationships, and facts from information.
    Store them in the graph memory with proper connections and attributes.
    Focus on creating meaningful relationships between concepts.""",
    tools=[internet_search, read_file],
    memory=shared_memory,
    verbose=True
)

# Build knowledge about AI companies
ai_companies_task = Task(
    description="""Research and build a knowledge graph about major AI companies.
    Include information about: OpenAI, Google DeepMind, Anthropic, Microsoft, Meta.
    Extract entities like: company names, founders, products, funding, partnerships.""",
    expected_output="Knowledge graph with AI company ecosystem relationships",
    agent=knowledge_builder
)

result_1 = knowledge_builder.execute_task(ai_companies_task)
print(f"Knowledge Graph Built: {result_1}")

# Show graph statistics
graph_stats = shared_memory.get_graph_statistics()
print(f"Entities: {graph_stats['num_entities']}")
print(f"Relationships: {graph_stats['num_relationships']}")
print(f"Connected Components: {graph_stats['connected_components']}\n")

# Example 2: Graph-Based Research Agent
print("Example 2: Graph-Based Reasoning")
print("-" * 40)

research_agent = Agent(
    name="Graph Researcher",
    role="Knowledge Graph Researcher",
    goal="Use graph memory to answer complex questions through reasoning",
    backstory="Expert at traversing knowledge graphs and connecting information",
    instructions="""Use the graph memory to find connections and relationships.
    Perform multi-hop reasoning to answer complex questions.
    Combine related information from different parts of the graph.""",
    memory=shared_memory,
    tools=[internet_search],
    verbose=True
)

# Complex reasoning task
reasoning_task = Task(
    description="""Using the knowledge graph, analyze the competitive landscape 
    between AI companies. Find connections, partnerships, and competitive relationships.
    Answer: Which companies are most likely to collaborate vs compete?""",
    expected_output="Analysis based on graph relationships and reasoning",
    agent=research_agent
)

result_2 = research_agent.execute_task(reasoning_task)
print(f"Graph-Based Analysis: {result_2}\n")

# Example 3: Multi-Agent Shared Graph Memory
print("Example 3: Multi-Agent Shared Memory")
print("-" * 40)

# Data Collector Agent
data_collector = Agent(
    name="Data Collector",
    role="Information Gatherer",
    goal="Collect and store structured data in graph memory",
    backstory="Specialist in gathering factual information and storing it systematically",
    memory=shared_memory,
    tools=[internet_search]
)

# Relationship Mapper Agent  
relationship_mapper = Agent(
    name="Relationship Mapper",
    role="Connection Analyzer",
    goal="Identify and map relationships between entities",
    backstory="Expert at finding hidden connections and mapping relationships",
    memory=shared_memory
)

# Insight Generator Agent
insight_generator = Agent(
    name="Insight Generator", 
    role="Strategic Analyst",
    goal="Generate insights from graph patterns and relationships",
    backstory="Strategic thinker who can see the big picture from connected data",
    memory=shared_memory
)

# Create tasks for each agent
data_task = Task(
    description="Collect detailed information about venture capital firms investing in AI",
    expected_output="VC firms and their AI investments stored in graph",
    agent=data_collector
)

relationship_task = Task(
    description="Map relationships between AI companies, VCs, and key individuals",
    expected_output="Comprehensive relationship mapping in graph",
    agent=relationship_mapper,
    context=[data_task]
)

insight_task = Task(
    description="Generate strategic insights about AI investment patterns and trends",
    expected_output="Strategic analysis based on graph patterns",
    agent=insight_generator,
    context=[data_task, relationship_task]
)

# Execute multi-agent workflow
multi_agent_system = PraisonAIAgents(
    agents=[data_collector, relationship_mapper, insight_generator],
    tasks=[data_task, relationship_task, insight_task],
    memory=shared_memory,
    process="sequential"
)

result_3 = multi_agent_system.start()
print(f"Multi-Agent Graph Analysis: {result_3}\n")

# Example 4: Graph Memory Search and Retrieval
print("Example 4: Advanced Graph Queries")
print("-" * 40)

# Semantic search in graph
search_results = shared_memory.semantic_search(
    query="AI companies with significant funding",
    max_results=5,
    include_relationships=True
)

print("Semantic Search Results:")
for result in search_results:
    print(f"  - {result['entity']}: {result['description']}")
    print(f"    Relationships: {result['relationships'][:3]}...")

# Path finding between entities
path_results = shared_memory.find_path(
    start_entity="OpenAI",
    end_entity="Microsoft", 
    max_hops=3
)

print(f"\nPath from OpenAI to Microsoft:")
for step in path_results:
    print(f"  {step['from']} --[{step['relationship']}]--> {step['to']}")

# Complex graph patterns
pattern_results = shared_memory.find_pattern(
    pattern="company -[FUNDED_BY]-> vc_firm -[ALSO_INVESTED_IN]-> other_company",
    limit=5
)

print(f"\nInvestment Pattern Analysis:")
for pattern in pattern_results:
    print(f"  {pattern['entities']} connected via {pattern['relationships']}")

# Example 5: Graph Memory Persistence and Versioning
print("\nExample 5: Graph Memory Management")
print("-" * 40)

# Save current state
version_id = shared_memory.save_version("ai_ecosystem_v1")
print(f"Saved graph version: {version_id}")

# Graph analytics
analytics = shared_memory.analyze_graph()
print(f"Graph Density: {analytics['density']:.3f}")
print(f"Most Connected Entity: {analytics['most_connected_entity']}")
print(f"Cluster Count: {analytics['num_clusters']}")
print(f"Average Path Length: {analytics['avg_path_length']:.2f}")

# Memory optimization
shared_memory.optimize_memory()
print("Graph memory optimized for better performance")

# Final statistics
final_stats = shared_memory.get_comprehensive_stats()
print(f"\n=== Final Graph Memory Statistics ===")
print(f"Total Entities: {final_stats['entities']}")
print(f"Total Relationships: {final_stats['relationships']}")
print(f"Memory Usage: {final_stats['memory_usage_mb']:.1f} MB")
print(f"Query Performance: {final_stats['avg_query_time_ms']:.1f} ms")
print(f"Graph Completeness: {final_stats['completeness_score']:.1%}")

print("\nAdvanced Graph Memory Integration example complete!")