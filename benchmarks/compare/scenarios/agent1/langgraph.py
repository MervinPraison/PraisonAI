# S2/S3/S5 single agent. make_tool() runs outside the timed region.
import os

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

URL = os.environ["BENCH_STUB_URL"] + "/v1"

def get_weather(city: str) -> str:
    """Get the weather for a city."""
    return f"Sunny in {city}"


def make_tool():
    return tool(get_weather)


def build(tools):
    llm = ChatOpenAI(model="gpt-4o-mini", base_url=URL)
    return create_react_agent(llm, tools, prompt="You are a helpful assistant.", name="Assistant")


def ask(agent, prompt):
    return agent.invoke({"messages": [("user", prompt)]})["messages"][-1].content
