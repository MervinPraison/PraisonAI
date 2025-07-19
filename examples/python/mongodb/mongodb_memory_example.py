#!/usr/bin/env python3
"""
MongoDB Memory Example for PraisonAI Agents

This example demonstrates how to use MongoDB as a memory provider for PraisonAI agents.
MongoDB can be used as both a key-value store and a vector database for memory operations.

Prerequisites:
- Install MongoDB dependencies: pip install 'praisonaiagents[mongodb]'
- MongoDB server running (local or Atlas)
- OpenAI API key for embeddings

Features demonstrated:
- MongoDB as memory provider
- Vector search with Atlas Vector Search
- Quality scoring and filtering
- User-specific memory storage
- Persistent memory across sessions
"""

import os
from praisonaiagents import Agent, Task, PraisonAIAgents

# Ensure OpenAI API key is set
if not os.environ.get("OPENAI_API_KEY"):
    raise ValueError("Please set the OPENAI_API_KEY environment variable")

def main():
    # MongoDB memory configuration
    mongodb_memory_config = {
        "provider": "mongodb",
        "config": {
            "connection_string": "mongodb://localhost:27017/",  # Replace with your MongoDB connection string
            "database": "praisonai_memory",
            "use_vector_search": True,  # Enable Atlas Vector Search (requires MongoDB Atlas)
            "max_pool_size": 50,
            "min_pool_size": 10,
            "server_selection_timeout": 5000
        }
    }
    
    # Create a research agent with MongoDB memory
    research_agent = Agent(
        name="MongoDB Research Agent",
        role="Senior Research Specialist",
        goal="Research topics and maintain persistent memory using MongoDB",
        backstory="""You are an expert researcher who specializes in collecting, 
        analyzing, and storing information using advanced MongoDB-based memory systems. 
        You excel at maintaining context across multiple research sessions and can 
        retrieve relevant information from your persistent memory store.""",
        memory=True,
        verbose=True,
        llm="gpt-4o-mini"
    )
    
    # Create research tasks
    research_tasks = [
        Task(
            description="""Research the latest developments in AI/ML for 2024:
            1. Identify major AI breakthroughs and trends
            2. Analyze the impact on various industries
            3. Store key findings in MongoDB memory with quality scores
            4. Identify emerging technologies and their potential applications
            """,
            expected_output="Comprehensive AI/ML research report with key findings stored in MongoDB",
            agent=research_agent
        ),
        Task(
            description="""Research MongoDB Atlas Vector Search capabilities:
            1. Explore vector search features and use cases
            2. Compare with other vector databases
            3. Analyze performance and scalability
            4. Store technical insights in MongoDB memory
            """,
            expected_output="Technical analysis of MongoDB Atlas Vector Search with stored insights",
            agent=research_agent
        ),
        Task(
            description="""Research AI agent frameworks and tools:
            1. Compare popular AI agent frameworks
            2. Analyze their strengths and weaknesses
            3. Identify best practices for agent development
            4. Store comparative analysis in MongoDB memory
            """,
            expected_output="Comparative analysis of AI agent frameworks with stored insights",
            agent=research_agent
        )
    ]
    
    # Initialize the multi-agent system with MongoDB memory
    print("🚀 Starting MongoDB Memory Research System...")
    print("=" * 60)
    
    research_system = PraisonAIAgents(
        agents=[research_agent],
        tasks=research_tasks,
        memory=True,
        memory_config=mongodb_memory_config,
        verbose=True
    )
    
    # Execute the research pipeline
    try:
        results = research_system.start()
        
        print("\n" + "=" * 60)
        print("📊 Research System Results:")
        print("=" * 60)
        
        # Handle results structure properly
        if isinstance(results, (list, tuple)):
            for i, result in enumerate(results, 1):
                print(f"\n{i}. Task Result:")
                if hasattr(result, 'agent'):
                    print(f"   Output: {str(result)[:200]}...")
                    print(f"   Agent: {result.agent}")
                else:
                    print(f"   Output: {str(result)[:200]}...")
        else:
            print(f"\n1. Task Result:")
            print(f"   Output: {str(results)[:200]}...")
            
        print("\n" + "=" * 60)
        print("💾 MongoDB Memory Integration Complete!")
        print("=" * 60)
        
        # Demonstrate memory retrieval
        print("\n🔍 Demonstrating Memory Retrieval:")
        print("-" * 40)
        
        # Access the memory system directly
        memory_system = research_system.memory
        
        # Search for AI-related memories
        ai_memories = memory_system.search_long_term("AI machine learning", limit=3)
        print(f"Found {len(ai_memories)} AI-related memories:")
        for memory in ai_memories:
            print(f"  - {memory.get('text', '')[:100]}...")
        
        # Search for MongoDB-related memories
        mongo_memories = memory_system.search_long_term("MongoDB vector search", limit=3)
        print(f"\nFound {len(mongo_memories)} MongoDB-related memories:")
        for memory in mongo_memories:
            print(f"  - {memory.get('text', '')[:100]}...")
        
        print("\n✅ MongoDB Memory Example Completed Successfully!")
        
    except Exception as e:
        print(f"\n❌ Error during execution: {e}")
        print("Please check your MongoDB connection and API keys.")

if __name__ == "__main__":
    print("MongoDB Memory Example for PraisonAI Agents")
    print("=" * 50)
    print("This example demonstrates MongoDB integration for persistent memory")
    print("Make sure you have:")
    print("1. MongoDB server running (local or Atlas)")
    print("2. OpenAI API key set in environment variables")
    print("3. MongoDB dependencies installed: pip install 'praisonaiagents[mongodb]'")
    print("=" * 50)
    
    main()