from praisonaiagents import Agent, AgentTeam, Tools

research_agent = Agent(name="Research", instructions="You are a research agent to search internet about AI 2024", tools=[Tools.internet_search])
summarise_agent = Agent(name="Summarise", instructions="You are a summarize agent to summarise in points")
agents = AgentTeam(agents=[research_agent, summarise_agent])
agents2 = AgentTeam(agents=[research_agent])
agents.launch(path="/agents", port=3030)
agents2.launch(path="/agents2", port=3030)