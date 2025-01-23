from praisonaiagents import Agent

agent = Agent(
    instructions="You are helpful Assisant", 
    llm="deepseek/deepseek-reasoner", 
    show_reasoning=True
)

result = agent.start("Why sky is Blue?")
print(result)