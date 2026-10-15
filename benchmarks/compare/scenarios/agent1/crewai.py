# S2/S3/S5 single agent. make_tool() runs outside the timed region.
import os

from crewai import LLM, Agent, Task
from crewai.tools import tool

URL = os.environ["BENCH_STUB_URL"] + "/v1"

def get_weather(city: str) -> str:
    """Get the weather for a city."""
    return f"Sunny in {city}"


def make_tool():
    return tool("get_weather")(get_weather)


def build(tools):
    llm = LLM(model="openai/gpt-4o-mini", base_url=URL)
    return Agent(role="Assistant", goal="You are a helpful assistant.", backstory="Assistant",
                 llm=llm, tools=tools)


def ask(agent, prompt):
    return Task(description=prompt, expected_output="An answer", agent=agent).execute_sync().raw
