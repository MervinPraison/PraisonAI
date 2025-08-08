from praisonaiagents import Agent

agent = Agent(instructions="""You are a helpful assistant.""", llm="gpt-5-nano")
agent.launch(path="/ask", port=3030)