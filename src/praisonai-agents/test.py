from praisonaiagents import Agent, Task, PraisonAIAgents
import os
from dotenv import load_dotenv

load_dotenv()

llm_config = {
    "model": "openai/gpt-4o-mini",
    "api_key": os.getenv('OPENAI_API_KEY'),
    "temperature": 0.7,
    "max_tokens": 2000
}

blog_agent = Agent(
    role="Blog Writer",
    goal="Write a blog post about AI",
    backstory="Expert at writing blog posts",
    llm=llm_config,
)

blog_task = Task(
    description="Write a blog post about AI trends in 1 paragraph",
    expected_output="Well-written blog post about AI trends",
    agent=blog_agent
)

agents = PraisonAIAgents(
    agents=[blog_agent],
    tasks=[blog_task],
    memory=False
)

result = agents.start()
