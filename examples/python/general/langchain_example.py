from praisonaiagents import Agent, Task, Agents
from langchain_community.tools import YouTubeSearchTool
from langchain_community.utilities import WikipediaAPIWrapper

# Create an agent with both tools
agent = Agent(
    name="SearchAgent",
    role="Research Assistant",
    goal="Search for information from multiple sources",
    backstory="I am an AI assistant that can search YouTube and Wikipedia.",
    tools=[YouTubeSearchTool, WikipediaAPIWrapper],
    reflection=False
)

# Create tasks to demonstrate both tools
task = Task(
    name="search_task",
    description="Search for information about 'AI advancements' on both YouTube and Wikipedia",
    expected_output="Combined information from YouTube videos and Wikipedia articles",
    agent=agent
)

# Create and start the workflow
agents = Agents(
    agents=[agent],
    tasks=[task], output="verbose"
)

agents.start()