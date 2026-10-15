# Docs: https://docs.praison.ai/docs/concepts/agents
from praisonaiagents import Agent, AgentTeam


def build():
    return AgentTeam(agents=[
        Agent(name="Researcher", instructions="Research the topic.", llm="gpt-4o-mini", output="silent"),
        Agent(name="Writer", instructions="Write a draft from the research.", llm="gpt-4o-mini", output="silent"),
        Agent(name="Editor", instructions="Edit the draft.", llm="gpt-4o-mini", output="silent"),
    ], output="silent")


def run(team):
    return team.start("AI agents")
