#!/usr/bin/env python3
"""
Graph Memory Agent Example

This example demonstrates how to use Mem0's graph memory capabilities 
with PraisonAI agents to create and utilize complex relationships 
between pieces of information.

Requirements:
    pip install "praisonaiagents[graph]"

Setup:
    - For Neo4j: Set up a Neo4j instance (local or AuraDB)
    - For Memgraph: Run with Docker: 
      docker run -p 7687:7687 memgraph/memgraph-mage:latest --schema-info-enabled=True
"""

import os
from praisonaiagents import Agent, Task, PraisonAIAgents

def main():
    # Example with Neo4j (uncomment and configure as needed)
    neo4j_config = {
        "provider": "mem0",
        "config": {
            "graph_store": {
                "provider": "neo4j",
                "config": {
                    "url": "neo4j+s://your-instance.databases.neo4j.io",
                    "username": "neo4j",
                    "password": "your-password"
                }
            },
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "host": "localhost",
                    "port": 6333
                }
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "model": "gpt-4o-mini"
                }
            }
        }
    }
    
    # Example with Memgraph (local setup)
    memgraph_config = {
        "provider": "mem0",
        "config": {
            "graph_store": {
                "provider": "memgraph",
                "config": {
                    "url": "bolt://localhost:7687",
                    "username": "memgraph",
                    "password": ""
                }
            },
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "host": "localhost", 
                    "port": 6333
                }
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "model": "gpt-4o-mini"
                }
            }
        }
    }
    
    # Simple local configuration (fallback to vector-only memory)
    local_config = {
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
    
    # Use local config by default (can be switched to neo4j_config or memgraph_config)
    memory_config = local_config
    
    print("🧠 Graph Memory Agent Example")
    print("=" * 50)
    
    # Define research agent
    researcher = Agent(
        name="Knowledge Researcher", 
        role="AI Research Specialist",
        goal="Research and build knowledge graphs about AI and technology relationships",
        backstory="""You are an expert at identifying relationships between concepts, 
        people, technologies, and ideas. You excel at creating structured knowledge 
        that captures complex interconnections.""",
        verbose=True,
        memory=True
    )
    
    # Task 1: Build initial knowledge graph
    build_knowledge_task = Task(
        description="""Research and store information about the relationships between:
        1. OpenAI and its key products (GPT-4, ChatGPT, DALL-E)
        2. Key people: Sam Altman (CEO), Greg Brockman (Co-founder)
        3. Partnerships: Microsoft partnership and investment
        4. Competitors: Anthropic, Google, Meta
        5. Technologies: Transformer architecture, reinforcement learning
        
        Focus on capturing the relationships and connections between these entities.
        Store comprehensive information about how these elements relate to each other.""",
        expected_output="Detailed knowledge graph with entities and relationships about OpenAI ecosystem",
        agent=researcher
    )
    
    # Task 2: Query and expand knowledge
    query_knowledge_task = Task(
        description="""Based on the previously stored knowledge, answer these questions:
        1. Who are the key leaders at OpenAI and what are their roles?
        2. What are the main products and how do they relate to each other?
        3. Who are OpenAI's main competitors and how do they compare?
        4. What is the relationship between OpenAI and Microsoft?
        
        Use the stored memory to provide comprehensive answers that leverage 
        the relationship information.""",
        expected_output="Comprehensive answers utilizing relationship-aware memory retrieval",
        agent=researcher
    )
    
    # Task 3: Add new connections
    expand_knowledge_task = Task(
        description="""Add new information to the knowledge graph:
        1. Elon Musk was a co-founder of OpenAI but left the board
        2. OpenAI started as a non-profit but created a capped-profit subsidiary
        3. GPT-4 powers ChatGPT and is also available via API
        4. DALL-E uses diffusion models for image generation
        5. OpenAI's research influences the broader AI field
        
        Ensure these new facts are connected to the existing knowledge graph.""",
        expected_output="Updated knowledge graph with new relationships and connections",
        agent=researcher
    )
    
    # Run the multi-agent system with graph memory
    agents_system = PraisonAIAgents(
        agents=[researcher],
        tasks=[build_knowledge_task, query_knowledge_task, expand_knowledge_task],
        verbose=1,
        memory=True,
        memory_config=memory_config
    )
    
    print("\n🚀 Starting graph memory demonstration...")
    result = agents_system.start()
    
    print("\n✅ Graph Memory Example Complete!")
    print("=" * 50)
    print("The agent has built and queried a knowledge graph that captures")
    print("complex relationships between entities, demonstrating how graph memory")
    print("enhances traditional vector-based memory with relationship awareness.")
    
    return result

def test_direct_memory_api():
    """
    Direct example using the Memory class with graph support
    """
    print("\n🔬 Direct Memory API Test")
    print("=" * 30)
    
    from praisonaiagents.memory import Memory
    
    # Configure memory with graph support (using local fallback)
    memory_config = {
        "provider": "mem0",
        "config": {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "path": ".praison/test_graph_memory"
                }
            }
        }
    }
    
    memory = Memory(config=memory_config, verbose=5)
    
    # Test storing user memories with relationships
    user_id = "alice"
    
    memories = [
        "I love hiking in the mountains",
        "My friend John also loves hiking", 
        "John has a dog named Max",
        "Max loves to go on hikes with us",
        "We often hike in Yosemite National Park",
        "Yosemite has beautiful waterfalls"
    ]
    
    print("Storing memories with potential relationships...")
    for memory_text in memories:
        memory.store_user_memory(user_id, memory_text)
        print(f"✓ Stored: {memory_text}")
    
    print("\nSearching for relationship-aware memories...")
    
    # Test relationship-aware searches
    queries = [
        "Who likes hiking?",
        "Tell me about John",
        "What do we know about dogs?",
        "Where do they go hiking?"
    ]
    
    for query in queries:
        print(f"\n🔍 Query: {query}")
        results = memory.search_user_memory(user_id, query, limit=3, rerank=True)
        for i, result in enumerate(results, 1):
            if isinstance(result, dict):
                print(f"  {i}. {result.get('memory', result.get('text', str(result)))}")
            else:
                print(f"  {i}. {result}")

if __name__ == "__main__":
    # Check if required environment variables are set
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Warning: OPENAI_API_KEY not set. Some features may not work.")
        print("   Set your API key: export OPENAI_API_KEY='your-key-here'")
    
    try:
        # Run the main agent example
        main()
        
        # Run direct API test
        test_direct_memory_api()
        
    except ImportError as e:
        print(f"❌ Import Error: {e}")
        print("💡 Try installing graph memory support:")
        print("   pip install \"praisonaiagents[graph]\"")
    except Exception as e:
        print(f"❌ Error: {e}")
        print("💡 Make sure you have the required dependencies and configuration.")