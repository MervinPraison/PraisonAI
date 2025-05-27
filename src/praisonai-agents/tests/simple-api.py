from praisonaiagents import Agent

agent = Agent(instructions="""You are a helpful assistant.""", llm="gpt-4o-mini")
agent.launch(path="/ask", port=3030)