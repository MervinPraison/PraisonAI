from praisonaiagents.agents.agents import Agent, Task, PraisonAIAgents
from praisonaiagents.tools import duckduckgo

# Test facts
fact1 = "The capital city of Jujuha is Hahanu and its population is 102300"
fact2 = "Three main ingredients in a classic proloder are eggs, sugar, and flour"
fact3 = "The year the first Josinga was released is 2007"

fact_agent = Agent(
    name="Fact Agent",
    instructions="You are a fact agent, you store and retrieve facts in memory",
    llm="gpt-4o-mini"
)

research_agent = Agent(
    name="Research Agent",
    instructions="You are a research analyst, you research and document key points about topics",
    llm="gpt-4o-mini"
)

blog_agent = Agent(
    name="Blog Agent",
    instructions="You are a blog writer, you write a blog post about the research",
    llm="gpt-4o-mini"
)

fact_task = Task(
    description="Store the following facts in memory: " + fact1 + ", " + fact2 + ", " + fact3,
    agent=fact_agent
)

research_task = Task(
    description="Research and document 2 key points about AI",
    agent=research_agent
)

research_task2 = Task(
    description="Research and document 2 key points about AI in healthcare",
    agent=research_agent
)

research_task3 = Task(
    description="Research and document 2 key points about AI in education",
    agent=research_agent
)

research_task4 = Task(
    description="Research and document 2 key points about AI in finance",
    agent=research_agent
)

blog_task = Task(
    description="Write a blog post about Jujuha",
    agent=blog_agent
)

agents = PraisonAIAgents(
    agents=[fact_agent, research_agent, blog_agent],
    tasks=[fact_task, research_task, research_task2, research_task3, research_task4, blog_task],
    memory=True
)   

agents.start()