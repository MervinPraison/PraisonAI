# S2/S3/S5 single agent. make_tool() runs outside the timed region.
from praisonaiagents import Agent

def get_weather(city: str) -> str:
    """Get the weather for a city."""
    return f"Sunny in {city}"


def make_tool():
    return get_weather


def build(tools):
    return Agent(name="Assistant", instructions="You are a helpful assistant.", llm="gpt-4o-mini",
                 tools=tools, output="silent")


def build_legacy(tools):
    # Historical PraisonAI-only config, kept so the instantiation history stays continuous.
    return Agent(name="Test", model="gpt-4o-mini", output="silent")


def ask(agent, prompt):
    return agent.start(prompt)
