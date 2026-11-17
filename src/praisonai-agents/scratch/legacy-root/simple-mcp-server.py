from praisonaiagents import Agent

agent = Agent(instructions="Create a Tweet")
agent.launch(port=8080, protocol="mcp")