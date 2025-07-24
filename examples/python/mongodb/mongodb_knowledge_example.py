#!/usr/bin/env python3
"""
MongoDB Knowledge Example for PraisonAI Agents

This example demonstrates how to use MongoDB as a knowledge store for PraisonAI agents.
MongoDB can store and retrieve knowledge documents with vector search capabilities.

Prerequisites:
- Install MongoDB dependencies: pip install 'praisonaiagents[mongodb]'
- MongoDB server running (local or Atlas)
- OpenAI API key for embeddings

Features demonstrated:
- MongoDB as knowledge vector store
- Document processing and storage
- Vector search for knowledge retrieval
- Knowledge-based agent interactions
- File processing with MongoDB storage
"""

import os
from praisonaiagents import Agent, Task, PraisonAIAgents

# Ensure OpenAI API key is set
if not os.environ.get("OPENAI_API_KEY"):
    raise ValueError("Please set the OPENAI_API_KEY environment variable")

def main():
    # MongoDB knowledge configuration
    mongodb_knowledge_config = {
        "vector_store": {
            "provider": "mongodb",
            "config": {
                "connection_string": "mongodb://localhost:27017/",  # Replace with your MongoDB connection string
                "database": "praisonai_knowledge",
                "collection": "knowledge_base",
                "use_vector_search": True  # Enable Atlas Vector Search
            }
        },
        "embedder": {
            "provider": "openai",
            "config": {
                "model": "text-embedding-3-small",
                "api_key": os.getenv("OPENAI_API_KEY")
            }
        }
    }
    
    # Create a knowledge agent with MongoDB knowledge store
    knowledge_agent = Agent(
        name="MongoDB Knowledge Agent",
        role="Knowledge Specialist",
        goal="Provide accurate information from MongoDB knowledge base",
        backstory="""You are an expert knowledge specialist who can access and 
        retrieve information from a comprehensive MongoDB knowledge base. You excel 
        at finding relevant information, synthesizing knowledge from multiple sources, 
        and providing accurate, context-aware responses.""",
        knowledge_config=mongodb_knowledge_config,
        knowledge=[os.path.join(os.path.dirname(__file__), "llms.md")],
        memory=True,
        verbose=True,
        llm="gpt-4o-mini"
    )
    
    # Create a research assistant agent
    research_agent = Agent(
        name="Research Assistant",
        role="Research Assistant",
        goal="Gather information and store it in the knowledge base",
        backstory="""You are a research assistant who specializes in gathering 
        information from various sources and organizing it for storage in the 
        knowledge base. You ensure information is accurate, well-structured, 
        and properly categorized.""",
        memory=True,
        verbose=True,
        llm="gpt-4o-mini"
    )
    
    # Create tasks for knowledge management
    knowledge_tasks = [
        Task(
            description="""Research and store information about MongoDB Atlas Vector Search:
            1. Gather comprehensive information about MongoDB Atlas Vector Search
            2. Include technical specifications, use cases, and best practices
            3. Store the information in the MongoDB knowledge base
            4. Organize information by categories (features, performance, integration)
            """,
            expected_output="MongoDB Atlas Vector Search information stored in knowledge base",
            agent=research_agent
        ),
        Task(
            description="""Research and store information about AI agent frameworks:
            1. Research popular AI agent frameworks (LangChain, AutoGen, etc.)
            2. Compare their features, capabilities, and use cases
            3. Store comparative analysis in the knowledge base
            4. Include code examples and best practices
            """,
            expected_output="AI agent framework comparison stored in knowledge base",
            agent=research_agent
        ),
        Task(
            description="""Query the knowledge base for MongoDB information:
            1. Search for information about MongoDB Atlas Vector Search
            2. Extract key features and capabilities
            3. Provide a comprehensive summary
            4. Include technical recommendations
            """,
            expected_output="Comprehensive MongoDB Atlas Vector Search summary from knowledge base",
            agent=knowledge_agent
        ),
        Task(
            description="""Query the knowledge base for AI agent framework information:
            1. Search for information about AI agent frameworks
            2. Compare different frameworks based on stored knowledge
            3. Provide recommendations for different use cases
            4. Include best practices and examples
            """,
            expected_output="AI agent framework comparison and recommendations from knowledge base",
            agent=knowledge_agent
        )
    ]
    
    # Initialize the multi-agent system with MongoDB knowledge
    print("🚀 Starting MongoDB Knowledge Management System...")
    print("=" * 60)
    
    knowledge_system = PraisonAIAgents(
        agents=[research_agent, knowledge_agent],
        tasks=knowledge_tasks,
        memory=True,
        verbose=True
    )
    
    # Execute the knowledge management pipeline
    try:
        results = knowledge_system.start()
        
        print("\n" + "=" * 60)
        print("📊 Knowledge Management System Results:")
        print("=" * 60)
        
        # Handle results structure properly
        if isinstance(results, (list, tuple)):
            for i, result in enumerate(results, 1):
                print(f"\n{i}. Task Result:")
                if hasattr(result, 'raw') and hasattr(result, 'agent'):
                    print(f"   Output: {result.raw[:200]}...")
                    print(f"   Agent: {result.agent}")
                else:
                    print(f"   Output: {str(result)[:200]}...")
        else:
            print(f"\n1. Task Result:")
            print(f"   Output: {str(results)[:200]}...")
        
        print("\n" + "=" * 60)
        print("💾 MongoDB Knowledge Integration Complete!")
        print("=" * 60)
        
        # Demonstrate direct knowledge access
        print("\n🔍 Demonstrating Direct Knowledge Access:")
        print("-" * 40)
        
        # Access knowledge system directly
        from praisonaiagents.knowledge import Knowledge
        
        knowledge_system = Knowledge(config=mongodb_knowledge_config)
        
        # Store a sample document
        sample_doc = """
        MongoDB is a document-oriented database that provides high performance, 
        high availability, and easy scalability. It works on the concept of 
        collections and documents, using a flexible, JSON-like document model.
        """
        
        print("📄 Storing sample document...")
        knowledge_system.store(sample_doc, metadata={"category": "database", "type": "overview"})
        
        # Search for stored knowledge
        print("\n🔍 Searching knowledge base...")
        results = knowledge_system.search("MongoDB document database", limit=3)
        
        print(f"Found {len(results)} knowledge entries:")
        for result in results:
            print(f"  - {result.get('memory', '')[:100]}...")
            print(f"    Score: {result.get('score', 'N/A')}")
        
        print("\n✅ MongoDB Knowledge Example Completed Successfully!")
        
    except Exception as e:
        print(f"\n❌ Error during execution: {e}")
        print("Please check your MongoDB connection and API keys.")

if __name__ == "__main__":
    print("MongoDB Knowledge Example for PraisonAI Agents")
    print("=" * 50)
    print("This example demonstrates MongoDB integration for knowledge management")
    print("Make sure you have:")
    print("1. MongoDB server running (local or Atlas)")
    print("2. OpenAI API key set in environment variables")
    print("3. MongoDB dependencies installed: pip install 'praisonaiagents[mongodb]'")
    print("=" * 50)
    
    main()