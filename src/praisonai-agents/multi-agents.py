from praisonaiagents import Agent, AgentManager

research_agent = Agent(instructions="Research about AI")
summarise_agent = Agent(instructions="Summarise research agent's findings")

agents = AgentManager(agents=[research_agent, summarise_agent])
response = agents.start()