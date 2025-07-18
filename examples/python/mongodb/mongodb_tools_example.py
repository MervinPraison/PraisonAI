#!/usr/bin/env python3
"""
MongoDB Tools Example for PraisonAI Agents

This example demonstrates how to use MongoDB tools with PraisonAI agents.
Agents can perform MongoDB operations like inserting, querying, and vector search.

Prerequisites:
- Install MongoDB dependencies: pip install 'praisonaiagents[mongodb]'
- MongoDB server running (local or Atlas)
- OpenAI API key for embeddings

Features demonstrated:
- MongoDB tools integration
- Document CRUD operations
- Vector search with embeddings
- Data analysis with MongoDB
- Agent-driven database operations
"""

import os
from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import mongodb_tools

# Ensure OpenAI API key is set
if not os.environ.get("OPENAI_API_KEY"):
    raise ValueError("Please set the OPENAI_API_KEY environment variable")

def main():
    # Create a MongoDB Database Agent with MongoDB tools
    db_agent = Agent(
        name="MongoDB Database Agent",
        role="Database Operations Specialist",
        goal="Manage MongoDB operations and data analysis",
        backstory="""You are an expert database administrator who specializes in 
        MongoDB operations. You can perform complex database queries, manage 
        collections, and analyze data patterns. You excel at using MongoDB tools 
        for data management and retrieval.""",
        tools=[mongodb_tools],
        verbose=True,
        llm="gpt-4o-mini"
    )
    
    # Create a Data Analysis Agent
    analysis_agent = Agent(
        name="Data Analysis Agent",
        role="Data Analyst",
        goal="Analyze data stored in MongoDB and provide insights",
        backstory="""You are a data analyst who specializes in extracting insights 
        from MongoDB databases. You can query data, perform aggregations, and 
        identify patterns and trends in the stored information.""",
        tools=[mongodb_tools],
        verbose=True,
        llm="gpt-4o-mini"
    )
    
    # Create tasks for MongoDB operations
    mongodb_tasks = [
        Task(
            description="""Set up MongoDB collections and insert sample data:
            1. Create a collection called 'products' for e-commerce data
            2. Insert sample product documents with fields: name, price, category, description
            3. Create a collection called 'users' for user data
            4. Insert sample user documents with fields: name, email, age, preferences
            5. Create appropriate indexes for better query performance
            
            Use the MongoDB tools to perform these operations.
            """,
            expected_output="MongoDB collections created with sample data and indexes",
            agent=db_agent
        ),
        Task(
            description="""Perform vector search operations:
            1. Create a vector index for product descriptions
            2. Store products with text embeddings for vector search
            3. Demonstrate vector similarity search for product recommendations
            4. Show how to find similar products based on description embeddings
            
            Use the MongoDB vector search tools for these operations.
            """,
            expected_output="Vector search implementation with product recommendations",
            agent=db_agent
        ),
        Task(
            description="""Query and analyze the stored data:
            1. Find all products in a specific category
            2. Calculate average price by category
            3. Find users with specific preferences
            4. Perform text search on product descriptions
            5. Generate insights about the data patterns
            
            Use MongoDB query tools to perform these analyses.
            """,
            expected_output="Data analysis report with insights from MongoDB queries",
            agent=analysis_agent
        ),
        Task(
            description="""Demonstrate advanced MongoDB operations:
            1. Update product prices based on specific criteria
            2. Perform aggregation operations for statistical analysis
            3. Create reports on user demographics and preferences
            4. Implement data validation and error handling
            5. Show MongoDB best practices for data management
            
            Use MongoDB tools for these advanced operations.
            """,
            expected_output="Advanced MongoDB operations report with best practices",
            agent=db_agent
        )
    ]
    
    # Initialize the multi-agent system with MongoDB tools
    print("🚀 Starting MongoDB Tools Demo System...")
    print("=" * 60)
    
    mongodb_system = PraisonAIAgents(
        agents=[db_agent, analysis_agent],
        tasks=mongodb_tasks,
        verbose=True
    )
    
    # Execute the MongoDB operations pipeline
    try:
        results = mongodb_system.start()
        
        print("\n" + "=" * 60)
        print("📊 MongoDB Tools System Results:")
        print("=" * 60)
        
        for i, result in enumerate(results, 1):
            print(f"\n{i}. Task Result:")
            print(f"   Output: {result.raw[:200]}...")
            print(f"   Agent: {result.agent}")
        
        print("\n" + "=" * 60)
        print("💾 MongoDB Tools Integration Complete!")
        print("=" * 60)
        
        # Demonstrate direct MongoDB tools usage
        print("\n🔍 Demonstrating Direct MongoDB Tools Usage:")
        print("-" * 40)
        
        # Connect to MongoDB
        mongo_client = mongodb_tools.connect_mongodb(
            "mongodb://localhost:27017/",  # Replace with your connection string
            "praisonai_tools_demo"
        )
        
        # Insert a sample document
        print("📄 Inserting sample document...")
        result = mongo_client.insert_document(
            "demo_collection",
            {
                "title": "MongoDB Tools Demo",
                "description": "Demonstration of MongoDB tools with PraisonAI",
                "category": "database",
                "tags": ["mongodb", "praisonai", "tools", "demo"]
            },
            metadata={"created_by": "demo", "version": "1.0"}
        )
        print(f"   Result: {result}")
        
        # Query documents
        print("\n🔍 Querying documents...")
        documents = mongo_client.find_documents(
            "demo_collection",
            {"category": "database"},
            limit=5
        )
        print(f"   Found {len(documents)} documents")
        for doc in documents:
            print(f"   - {doc.get('title', 'N/A')}: {doc.get('description', '')[:50]}...")
        
        # Get collection statistics
        print("\n📈 Getting collection statistics...")
        stats = mongo_client.get_stats("demo_collection")
        print(f"   Collection stats: {stats}")
        
        print("\n✅ MongoDB Tools Example Completed Successfully!")
        
    except Exception as e:
        print(f"\n❌ Error during execution: {e}")
        print("Please check your MongoDB connection and API keys.")

if __name__ == "__main__":
    print("MongoDB Tools Example for PraisonAI Agents")
    print("=" * 50)
    print("This example demonstrates MongoDB tools integration")
    print("Make sure you have:")
    print("1. MongoDB server running (local or Atlas)")
    print("2. OpenAI API key set in environment variables")
    print("3. MongoDB dependencies installed: pip install 'praisonaiagents[mongodb]'")
    print("=" * 50)
    
    main()