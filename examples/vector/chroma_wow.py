"""ChromaDB Vector Store - Agent-First Example"""
from praisonaiagents import Agent

# Agent-first approach: use knowledge parameter with ChromaDB
agent = Agent(
    name="Assistant",
    instructions="You are a helpful assistant with access to documents.",
    knowledge=["./docs/guide.pdf"],  # Add your documents here
    knowledge={
        "vector_store": "chroma",
        "path": "/tmp/chroma_demo"
    }
)

# Chat - agent uses knowledge for RAG
response = agent.chat("What information do you have?")
print(f"Response: {response}")

print("PASSED: ChromaDB with Agent")

# --- Advanced: Direct Store Usage ---
# from praisonai.persistence import create_knowledge_store
# store = create_knowledge_store("chroma", path="/tmp/chroma_demo")
