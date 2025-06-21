from praisonaiagents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import (
    read_file, write_file, list_files, get_file_info,
    copy_file, move_file, delete_file
)

# Get user input
d = input("Demande: ")

# Create file manager agent
file_manager_agent = Agent(
    name="FileManager",
    tools=[read_file, write_file, list_files, get_file_info,
           copy_file, move_file, delete_file],
    llm={
        "model": "ollama/llama3.2",
        "base_url": "http://localhost:11434"  # Ollama default
    }
)

# Dynamically create a task based on input
file_task = Task(
    name="Q",
    description=f"faire '{d}'.",
    expected_output=f"'{d}' bien fait.",
    agent=file_manager_agent
)

# Run agent with the task
agents = PraisonAIAgents(
    agents=[file_manager_agent],
    tasks=[file_task],
    process="sequential"
)

agents.start()
