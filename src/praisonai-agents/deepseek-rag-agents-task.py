from praisonaiagents import Agent, Task, PraisonAIAgents

config = {
    "vector_store": {
        "provider": "chroma",
        "config": {
            "collection_name": "praison",
            "path": ".praison"
        }
    },
    "llm": {
        "provider": "ollama",
        "config": {
            "model": "deepseek-r1:latest",
            "temperature": 0,
            "max_tokens": 8000,
            "ollama_base_url": "http://localhost:11434",
        },
    },
    "embedder": {
        "provider": "ollama",
        "config": {
            "model": "nomic-embed-text:latest",
            "ollama_base_url": "http://localhost:11434",
        },
    },
}

# Create an agent
rag_agent = Agent(
    name="RAG Agent",
    role="Information Specialist",
    goal="Retrieve knowledge efficiently",
    llm="deepseek-r1"
)

# Define a task for the agent
rag_task = Task(
    name="RAG Task",
    description="What is KAG?",
    expected_output="Answer to the question",
    agent=rag_agent,
    context=[config] # Vector Database provided as context
)

# Build Agents
agents = PraisonAIAgents(
    agents=[rag_agent],
    tasks=[rag_task],
    user_id="user1"
)

# Start Agents
agents.start()