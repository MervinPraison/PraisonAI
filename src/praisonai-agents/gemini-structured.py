from pydantic import BaseModel
from praisonaiagents import Agent, Task, Agents

class Recipe(BaseModel):
    recipe_name: str
    ingredients: list[str]

agent = Agent(
    name="Chef",
    role="Recipe Creator",
    llm="gemini/gemini-2.5-flash"
)

task = Task(
    description="Create a cookie recipe",
    agent=agent,
    output_pydantic=Recipe  # Will use Gemini's native structured output!
)

agents = Agents(
    agents=[agent],
    tasks=[task]
)

agents.start()