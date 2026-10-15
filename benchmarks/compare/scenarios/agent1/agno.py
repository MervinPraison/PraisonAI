# S2/S3/S5 single agent. make_tool() runs outside the timed region.
import os

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.tools import tool

URL = os.environ["BENCH_STUB_URL"] + "/v1"

def get_weather(city: str) -> str:
    """Get the weather for a city."""
    return f"Sunny in {city}"


def make_tool():
    return tool(get_weather)


def build(tools):
    return Agent(name="Assistant", model=OpenAIChat(id="gpt-4o-mini", base_url=URL),
                 instructions="You are a helpful assistant.", tools=tools)


def ask(agent, prompt):
    return agent.run(prompt).content
