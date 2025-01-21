from praisonaiagents import Agent, Task, PraisonAIAgents
import logging
import os
import json

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define the configuration for the Knowledge instance
config = {
    "version": "v1.1",
    "vector_store": {
        "provider": "chroma",
        "config": {
            "collection_name": "praison",
            "path": os.path.abspath("./.praison"),
            "host": None,
            "port": None
        }
    },
    "embedder": {
        "provider": "openai",
        "config": {
            "model": "text-embedding-3-small",
            "embedding_dims": 1536
        }
    },
    "llm": {
        "provider": "openai",
        "config": {
            "model": "gpt-4o-mini",
            "temperature": 0,
            "max_tokens": 1000
        }
    }
}

# Create an agent with knowledge capabilities
knowledge_agent = Agent(
    name="KnowledgeAgent",
    role="Information Specialist",
    goal="Store and retrieve knowledge efficiently",
    backstory="Expert in managing and utilizing stored knowledge",
    verbose=True
)

# Define a task for the agent
knowledge_task = Task(
    name="knowledge_task",
    description="KAG",
    expected_output="Answer to the question",
    agent=knowledge_agent,
    context=[
        {
            "embedding_db_config": json.dumps(config["vector_store"])
        }
    ]
)

# Create and start the agents
agents = PraisonAIAgents(
    agents=[knowledge_agent],
    tasks=[knowledge_task],
    process="sequential",
    user_id="user1"
)

# Start execution
result = agents.start()
