from praisonaiagents import Agent

agent = Agent(instructions="You are helpful Assisant", llm="deepseek-reasoner")

agent.start("Why sky is Blue?", show_reasoning=True)