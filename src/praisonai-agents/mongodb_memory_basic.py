from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.memory import Memory
from praisonaiagents.agent import ContextAgent
import pymongo

context_agent = ContextAgent(llm="gpt-4o-mini", auto_analyze=False)

context_output = context_agent.start("https://github.com/MervinPraison/PraisonAI/ Need to add Authentication")

mongodb_memory_config = {
    "provider": "mongodb",
    "config": {
        "connection_string": "mongodb+srv://username:password@cluster2.bofm7.mywebsite.net/?retryWrites=true&w=majority&appName=Cluster2",
        "database": "praisonai_memory",
        "use_vector_search": True,
        "max_pool_size": 50,
        "min_pool_size": 10,
        "server_selection_timeout": 5000
    }
}

implementation_agent = Agent(
    name="Implementation Agent",
    role="Authentication Implementation Specialist",
    goal="Implement authentication features based on project requirements",
    backstory="Expert software implementer specializing in authentication systems, security features, and seamless integration with existing codebases",
    memory=True,
    llm="gpt-4o-mini",
)

implementation_task = Task(
    description="Implement authentication features based on the project requirements from context analysis",
    expected_output="Authentication implementation with code, configuration, and integration details",
    agent=implementation_agent,
    context=context_output,
)

implementation_system = PraisonAIAgents(
    agents=[implementation_agent],
    tasks=[implementation_task],
    memory=True,
    memory_config=mongodb_memory_config
)

results = implementation_system.start()
print(f"Results: {results}")

print("\n=== MEMORY VALIDATION ===")

try:
    # Check MongoDB connection and collections
    client = pymongo.MongoClient("mongodb+srv://username:password@cluster2.bofm7.mongodb.net/?retryWrites=true&w=majority&appName=Cluster2")
    db = client["praisonai_memory"]
    collections = db.list_collection_names()
    print(f"Available collections: {collections}")
    
    for collection_name in collections:
        count = db[collection_name].count_documents({})
        print(f"{collection_name}: {count} documents")
        if count > 0:
            sample = db[collection_name].find_one()
            print(f"Sample document: {sample}")
            
except Exception as e:
    print(f"MongoDB direct check error: {e}")

try:
    # Check memory system
    memory_system = Memory(mongodb_memory_config)
    
    # Try different search terms
    search_terms = ["authentication", "security", "implementation", "requirements", "PraisonAI"]
    for term in search_terms:
        memories = memory_system.search_long_term(term, limit=3)
        print(f"Search '{term}': {len(memories)} memories found")
        if memories:
            print(f"  Sample: {str(memories[0])[:100]}...")
            
    # Try to get all memories
    all_memories = memory_system.get_all_memories()
    print(f"Total memories: {len(all_memories)}")
    
except Exception as e:
    print(f"Memory system error: {e}")