# S2/S3/S5 single agent. make_tool() runs outside the timed region.
import os

from agents import Agent, OpenAIChatCompletionsModel, Runner, function_tool, set_tracing_disabled
from openai import AsyncOpenAI

URL = os.environ["BENCH_STUB_URL"] + "/v1"
set_tracing_disabled(True)

def get_weather(city: str) -> str:
    """Get the weather for a city."""
    return f"Sunny in {city}"


def make_tool():
    return function_tool(get_weather)


def build(tools):
    model = OpenAIChatCompletionsModel(model="gpt-4o-mini", openai_client=AsyncOpenAI(base_url=URL))
    return Agent(name="Assistant", instructions="You are a helpful assistant.", model=model, tools=tools)


def ask(agent, prompt):
    return Runner.run_sync(agent, prompt).final_output
