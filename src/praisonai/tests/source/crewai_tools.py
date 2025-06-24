import os
from crewai import Agent, Task, Crew
from duckduckgo_search import DDGS
from langchain.tools import tool

@tool("Internet Search Tool")
def internet_search_tool(query: str) -> list:
    """Search Internet for relevant information based on a query."""
    ddgs = DDGS()
    results = ddgs.text(keywords=query, region='wt-wt', safesearch='moderate', max_results=5)
    return results

# Define agents
researcher = Agent(
    role='Researcher',
    goal='Gather and analyze information on specific topics',
    verbose=True,
    backstory=(
        "As a seasoned researcher, you have a keen eye for detail and a "
        "deep understanding of your field. You're adept at sifting through "
        "information to find the most relevant and accurate data."
    ),
    tools=[internet_search_tool],
    allow_delegation=True
)

writer = Agent(
    role='Writer',
    goal='Compose informative and engaging articles based on research findings',
    verbose=True,
    backstory=(
        "With a talent for storytelling, you translate complex ideas into "
        "clear, compelling narratives. Your articles are well-researched, "
        "thought-provoking, and accessible to a broad audience."
    ),
    tools=[internet_search_tool],
    allow_delegation=False
)

# Define tasks
research_task = Task(
    description=(
        "Investigate the latest trends in renewable energy technologies. "
        "Identify key advancements, challenges, and potential impacts on "
        "global energy policies."
    ),
    expected_output='A detailed report summarizing the findings.',
    tools=[internet_search_tool],
    agent=researcher,
)

writing_task = Task(
    description=(
        "Based on the research findings, write an article that highlights "
        "the importance of renewable energy innovations. The article should "
        "educate the public on how these technologies can contribute to "
        "sustainable development."
    ),
    expected_output='An engaging and informative article suitable for publication.',
    tools=[internet_search_tool],
    agent=writer,
)

# Create and kick off the crew
crew = Crew(
    agents=[researcher, writer],
    tasks=[research_task, writing_task]
)

result = crew.kickoff(inputs={'topic': 'renewable energy'})
print(result)
