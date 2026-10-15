# Docs: https://openai.github.io/openai-agents-python/multi_agent/  (chained runs; handoffs are LLM-driven)
import os

from agents import Agent, OpenAIChatCompletionsModel, Runner, set_tracing_disabled
from openai import AsyncOpenAI

URL = os.environ["BENCH_STUB_URL"] + "/v1"  # bench:config
set_tracing_disabled(True)  # bench:config


def build():
    model = OpenAIChatCompletionsModel(model="gpt-4o-mini", openai_client=AsyncOpenAI(base_url=URL))
    return [
        Agent(name="Researcher", instructions="Research the topic.", model=model),
        Agent(name="Writer", instructions="Write a draft from the research.", model=model),
        Agent(name="Editor", instructions="Edit the draft.", model=model),
    ]


def run(agents):
    text = "AI agents"
    for agent in agents:
        text = Runner.run_sync(agent, text).final_output
    return text
