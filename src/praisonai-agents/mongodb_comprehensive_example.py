#!/usr/bin/env python3
"""
Comprehensive MongoDB Integration Example for PraisonAI Agents

This example demonstrates a complete MongoDB integration with PraisonAI agents,
combining memory, knowledge, and tools for a comprehensive data management system.

Prerequisites:
- Install MongoDB dependencies: pip install 'praisonaiagents[mongodb]'
- MongoDB server running (local or Atlas)
- OpenAI API key for embeddings

Features demonstrated:
- MongoDB as memory provider
- MongoDB as knowledge store
- MongoDB tools for data operations
- Vector search capabilities
- Multi-agent coordination with MongoDB
- Real-world business scenario simulation
"""

import os
from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import mongodb_tools

# Ensure OpenAI API key is set
if not os.environ.get("OPENAI_API_KEY"):
    raise ValueError("Please set the OPENAI_API_KEY environment variable")

def main():
    # MongoDB configuration for different components
    mongodb_memory_config = {
        "provider": "mongodb",
        "config": {
            "connection_string": "mongodb://localhost:27017/",  # Replace with your connection string
            "database": "praisonai_comprehensive",
            "use_vector_search": True,
            "max_pool_size": 50
        }
    }
    
    mongodb_knowledge_config = {
        "vector_store": {
            "provider": "mongodb",
            "config": {
                "connection_string": "mongodb://localhost:27017/",
                "database": "praisonai_comprehensive",
                "collection": "knowledge_base",
                "use_vector_search": True
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
    
    # Create specialized agents for different business functions
    
    # 1. Data Manager Agent - handles data operations
    data_manager = Agent(
        name="Data Manager",
        role="Senior Data Operations Manager",
        goal="Manage and organize all data operations using MongoDB",
        backstory="""You are an expert data operations manager who specializes in 
        MongoDB database management. You handle data ingestion, organization, 
        indexing, and ensure data quality and accessibility across the organization.""",
        tools=[mongodb_tools],
        memory=True,
        verbose=True,
        llm="gpt-4o-mini"
    )
    
    # 2. Knowledge Curator Agent - manages knowledge base
    knowledge_curator = Agent(
        name="Knowledge Curator",
        role="Knowledge Management Specialist",
        goal="Curate and maintain organizational knowledge using MongoDB",
        backstory="""You are a knowledge management specialist who excels at 
        organizing, categorizing, and retrieving information from the knowledge base. 
        You ensure that knowledge is properly stored, indexed, and accessible.""",
        knowledge_config=mongodb_knowledge_config,
        memory=True,
        verbose=True,
        llm="gpt-4o-mini"
    )
    
    # 3. Business Analyst Agent - analyzes data and provides insights
    business_analyst = Agent(
        name="Business Analyst",
        role="Senior Business Intelligence Analyst",
        goal="Analyze business data and provide actionable insights",
        backstory="""You are a senior business analyst who specializes in extracting 
        insights from data stored in MongoDB. You create reports, identify trends, 
        and provide strategic recommendations based on data analysis.""",
        tools=[mongodb_tools],
        memory=True,
        verbose=True,
        llm="gpt-4o-mini"
    )
    
    # 4. Customer Service Agent - handles customer interactions
    customer_service = Agent(
        name="Customer Service Agent",
        role="Customer Service Representative",
        goal="Provide excellent customer service using stored knowledge and data",
        backstory="""You are a customer service representative who uses the 
        knowledge base and customer data to provide excellent support. You can 
        access customer history, product information, and troubleshooting guides.""",
        knowledge_config=mongodb_knowledge_config,
        tools=[mongodb_tools],
        memory=True,
        verbose=True,
        llm="gpt-4o-mini"
    )
    
    # Create comprehensive business tasks
    business_tasks = [
        Task(
            description="""Set up comprehensive business data infrastructure:
            1. Create collections for customers, products, orders, and support tickets
            2. Insert sample business data for an e-commerce platform
            3. Set up appropriate indexes for performance optimization
            4. Create vector indexes for product descriptions and customer support
            5. Implement data validation and business rules
            
            Focus on creating a realistic business data structure.
            """,
            expected_output="Complete business data infrastructure with sample data",
            agent=data_manager
        ),
        Task(
            description="""Build organizational knowledge base:
            1. Store product documentation and specifications
            2. Create customer service guidelines and FAQs
            3. Add troubleshooting guides and best practices
            4. Include company policies and procedures
            5. Organize knowledge by categories and tags
            
            Ensure knowledge is searchable and well-organized.
            """,
            expected_output="Comprehensive knowledge base with categorized information",
            agent=knowledge_curator
        ),
        Task(
            description="""Perform business intelligence analysis:
            1. Analyze customer purchase patterns and behavior
            2. Calculate key business metrics (revenue, conversion rates, etc.)
            3. Identify top-selling products and categories
            4. Analyze customer support ticket trends
            5. Generate insights for business optimization
            
            Use MongoDB aggregation and analytics capabilities.
            """,
            expected_output="Business intelligence report with actionable insights",
            agent=business_analyst
        ),
        Task(
            description="""Handle customer service scenarios:
            1. Process customer inquiries using knowledge base
            2. Look up customer order history and preferences
            3. Provide product recommendations based on customer data
            4. Access troubleshooting guides for technical issues
            5. Update customer records and interaction history
            
            Demonstrate excellent customer service with data-driven support.
            """,
            expected_output="Customer service interactions with knowledge-based responses",
            agent=customer_service
        ),
        Task(
            description="""Generate comprehensive business report:
            1. Combine insights from all data sources
            2. Create executive summary with key findings
            3. Provide recommendations for business improvement
            4. Include data visualizations and metrics
            5. Store report in knowledge base for future reference
            
            Create a comprehensive business intelligence report.
            """,
            expected_output="Executive business report with comprehensive insights",
            agent=business_analyst
        )
    ]
    
    # Initialize the comprehensive business system
    print("🚀 Starting Comprehensive MongoDB Business System...")
    print("=" * 60)
    
    business_system = PraisonAIAgents(
        agents=[data_manager, knowledge_curator, business_analyst, customer_service],
        tasks=business_tasks,
        memory=True,
        memory_config=mongodb_memory_config,
        verbose=True
    )
    
    # Execute the comprehensive business pipeline
    try:
        results = business_system.start()
        
        print("\n" + "=" * 60)
        print("📊 Comprehensive Business System Results:")
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
        print("💾 Comprehensive MongoDB Integration Complete!")
        print("=" * 60)
        
        # Demonstrate system integration
        print("\n🔍 Demonstrating System Integration:")
        print("-" * 40)
        
        # Access different components
        # Note: Direct memory access not available through business_system.memory
        print("📋 Memory integration enabled through memory_config...")
        print("Memory operations are handled internally by the agents")
        
        # Access memory system directly
        from praisonaiagents.memory import Memory
        memory_system = Memory(config=mongodb_memory_config)
        
        # Search business memories
        print("\n📋 Searching business memories...")
        business_memories = memory_system.search_long_term("business analysis", limit=3)
        print(f"Found {len(business_memories)} business-related memories")
        
        # Access knowledge system
        from praisonaiagents.knowledge import Knowledge
        knowledge_system = Knowledge(config=mongodb_knowledge_config)
        
        # Search knowledge base
        print("\n📚 Searching knowledge base...")
        knowledge_results = knowledge_system.search("customer service", limit=3)
        print(f"Found {len(knowledge_results)} knowledge entries")
        
        # Direct MongoDB operations
        print("\n🔧 Direct MongoDB operations...")
        mongo_client = mongodb_tools.connect_mongodb(
            "mongodb://localhost:27017/",
            "praisonai_comprehensive"
        )
        
        # Get database statistics
        stats = mongo_client.get_stats("customers")
        print(f"Customer collection stats: {stats}")
        
        print("\n" + "=" * 60)
        print("🎉 Comprehensive MongoDB Example Completed Successfully!")
        print("=" * 60)
        
        print("\n📈 System Overview:")
        print("- Memory System: MongoDB-based persistent memory")
        print("- Knowledge Base: MongoDB vector search enabled")
        print("- Tools Integration: Full MongoDB CRUD operations")
        print("- Multi-Agent Coordination: Business workflow simulation")
        print("- Vector Search: Semantic search capabilities")
        print("- Data Analytics: Business intelligence insights")
        
    except Exception as e:
        print(f"\n❌ Error during execution: {e}")
        print("Please check your MongoDB connection and API keys.")

if __name__ == "__main__":
    print("Comprehensive MongoDB Integration Example")
    print("=" * 50)
    print("This example demonstrates complete MongoDB integration with PraisonAI")
    print("Features:")
    print("- MongoDB Memory Provider")
    print("- MongoDB Knowledge Store")
    print("- MongoDB Tools Integration")
    print("- Vector Search Capabilities")
    print("- Multi-Agent Business Simulation")
    print("=" * 50)
    print("Make sure you have:")
    print("1. MongoDB server running (local or Atlas)")
    print("2. OpenAI API key set in environment variables")
    print("3. MongoDB dependencies installed: pip install 'praisonaiagents[mongodb]'")
    print("=" * 50)
    
    main()