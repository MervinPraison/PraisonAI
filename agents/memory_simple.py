from praisonaiagents.agents.agents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import duckduckgo

research_agent = Agent(
    role="Research Analyst",
    goal="Research and document key information about topics",
    backstory="Expert at analyzing and storing information in memory",
    llm="gpt-4o-mini",
    tools=[duckduckgo]
)

blog_agent = Agent(
    role="Blog Writer",
    goal="Write a blog post about the research",
    backstory="Expert at writing blog posts",
    llm="gpt-4o-mini"
)

research_task = Task(
    description="Research and document key information about topics",
    agent=research_agent
)

blog_task = Task(
    description="Write a blog post about the research",
    agent=blog_agent
)

agents = PraisonAIAgents(
    agents=[research_agent, blog_agent],
    tasks=[research_task, blog_task],
    memory=True
)   

agents.start()