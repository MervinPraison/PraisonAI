from praisonaiagents import Agent, Task, PraisonAIAgents
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define the configuration for the Knowledge instance
config = {
    "vector_store": {
        "provider": "chroma",
        "config": {
            "collection_name": "knowledge_test",
            "path": ".praison",
        }
    }
}

# Create an agent with knowledge capabilities
knowledge_agent = Agent(
    name="KnowledgeAgent",
    role="Information Specialist",
    goal="Store and retrieve knowledge efficiently",
    backstory="Expert in managing and utilizing stored knowledge",
    knowledge=["sample.pdf"],
    knowledge_config=config,
    verbose=True
)

# Define a task for the agent
knowledge_task = Task(
    name="knowledge_task",
    description="Who is Mervin Praison?",
    expected_output="Answer to the question",
    agent=knowledge_agent
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
