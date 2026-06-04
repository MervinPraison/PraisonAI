from pathlib import Path

from praisonaiagents import Agent, Task, AgentTeam
import logging
import os
import sys

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

_sample_path = Path(__file__).with_name("sample_knowledge.txt")
if not _sample_path.exists():
    _sample_path.write_text("Mervin Praison is the creator of PraisonAI.\n", encoding="utf-8")

# Create an agent with knowledge capabilities
knowledge_agent = Agent(
    name="KnowledgeAgent",
    role="Information Specialist",
    goal="Store and retrieve knowledge efficiently",
    backstory="Expert in managing and utilizing stored knowledge",
    knowledge={**config, "sources": [str(_sample_path)]},
)

# Define a task for the agent
knowledge_task = Task(
    name="knowledge_task",
    description="Who is Mervin Praison?",
    expected_output="Answer to the question",
    agent=knowledge_agent
)

# Create and start the agents
agents = AgentTeam(
    agents=[knowledge_agent],
    tasks=[knowledge_task],
    process="sequential",
)

if __name__ == "__main__":
    if not os.environ.get("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY to run this example.")
        sys.exit(0)
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    result = agents.start()
    print(result)
