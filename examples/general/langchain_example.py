from praisonaiagents import Agent, Task, PraisonAIAgents
from langchain_community.tools import YouTubeSearchTool
from langchain_community.utilities import WikipediaAPIWrapper

# Create an agent with both tools
agent = Agent(
    name="SearchAgent",
    role="Research Assistant",
    goal="Search for information from multiple sources",
    backstory="I am an AI assistant that can search YouTube and Wikipedia.",
    tools=[YouTubeSearchTool, WikipediaAPIWrapper],
    self_reflect=False
)

# Create tasks to demonstrate both tools
task = Task(
    name="search_task",
    description="Search for information about 'AI advancements' on both YouTube and Wikipedia",
    expected_output="Combined information from YouTube videos and Wikipedia articles",
    agent=agent
)

# Create and start the workflow
agents = PraisonAIAgents(
    agents=[agent],
    tasks=[task],
    verbose=True
)

agents.start()