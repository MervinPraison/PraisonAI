# Docs: https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/teams.html
import asyncio
import os

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient

URL = os.environ["BENCH_STUB_URL"] + "/v1"  # bench:config


def build():
    client = OpenAIChatCompletionClient(model="gpt-4o-mini", base_url=URL)
    return RoundRobinGroupChat([
        AssistantAgent("researcher", client, system_message="Research the topic."),
        AssistantAgent("writer", client, system_message="Write a draft from the research."),
        AssistantAgent("editor", client, system_message="Edit the draft."),
    ], max_turns=3)


def run(team):
    return asyncio.run(team.run(task="AI agents")).messages[-1].content
