from praisonaiagents import Agent, Task, PraisonAIAgents

llm_config = {
    "model": "deepseek/deepseek-reasoner",
    "max_tokens": 1
}

reasoning_agent = Agent(role="Helpful Assistant", llm=llm_config, reasoning_steps=True)
small_agent = Agent(role="Helpful Assistant", llm="openai/gpt-3.5-turbo")

reasoning_task = Task(description="How many r's in the word 'Strawberry'?", agent=reasoning_agent)
small_task = Task(description="With the provided reasoning tell me how many r's in the word 'Strawberry'?", agent=small_agent)

agents = PraisonAIAgents(
    agents=[reasoning_agent, small_agent],
    tasks=[reasoning_task, small_task]
)

agents.start()