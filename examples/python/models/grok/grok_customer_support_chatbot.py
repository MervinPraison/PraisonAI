from praisonaiagents import Agent

agent = Agent(
    instructions="You are a customer support AI agent for TechGadgets.com, an online electronics store. Answer customer queries helpfully.",
    llm="xai/grok-4"
)

response = agent.start("How to return an item?")