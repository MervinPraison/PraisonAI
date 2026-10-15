# S2/S3/S5 single agent. make_tool() runs outside the timed region.
import asyncio
import os

from autogen_agentchat.agents import AssistantAgent
from autogen_core.tools import FunctionTool
from autogen_ext.models.openai import OpenAIChatCompletionClient

URL = os.environ["BENCH_STUB_URL"] + "/v1"

def get_weather(city: str) -> str:
    """Get the weather for a city."""
    return f"Sunny in {city}"


def make_tool():
    return FunctionTool(get_weather, description="Get the weather for a city.")


def build(tools):
    client = OpenAIChatCompletionClient(model="gpt-4o-mini", base_url=URL)
    return AssistantAgent("assistant", client, tools=tools, system_message="You are a helpful assistant.")


def ask(agent, prompt):
    return asyncio.run(agent.run(task=prompt)).messages[-1].content
