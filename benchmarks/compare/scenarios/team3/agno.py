# Docs: https://docs.agno.com/workflows/overview  (Workflow, not Team: a Team leader adds LLM calls)
import os

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.workflow import Workflow

URL = os.environ["BENCH_STUB_URL"] + "/v1"  # bench:config


def build():
    model = OpenAIChat(id="gpt-4o-mini", base_url=URL)
    return Workflow(steps=[
        Agent(name="Researcher", model=model, instructions="Research the topic."),
        Agent(name="Writer", model=model, instructions="Write a draft from the research."),
        Agent(name="Editor", model=model, instructions="Edit the draft."),
    ])


def run(workflow):
    return workflow.run("AI agents").content
