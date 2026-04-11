from praisonai import Agent, ManagedAgent

agent = Agent(name="teacher", backend=ManagedAgent())
result = agent.start("Write a Python script that prints 'Hello from Managed Agents!' and run it")
print(result)