from praisonaiagents import Agent, Agents

research_agent = Agent(instructions="Research about AI")
summarise_agent = Agent(instructions="Summarise research agent's findings")

agents = Agents(agents=[research_agent, summarise_agent])
response = agents.start()