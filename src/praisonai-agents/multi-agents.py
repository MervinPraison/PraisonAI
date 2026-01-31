from praisonaiagents import Agent, AgentTeam

research_agent = Agent(instructions="Research about AI")
summarise_agent = Agent(instructions="Summarise research agent's findings")

agents = AgentTeam(agents=[research_agent, summarise_agent])
response = agents.start()