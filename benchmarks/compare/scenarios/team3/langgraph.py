# Docs: https://langchain-ai.github.io/langgraph/concepts/low_level/
import os
from typing import TypedDict

from langchain_openai import ChatOpenAI
from langgraph.graph import START, StateGraph

URL = os.environ["BENCH_STUB_URL"] + "/v1"  # bench:config


class State(TypedDict):
    text: str


def build():
    llm = ChatOpenAI(model="gpt-4o-mini", base_url=URL)

    def step(instructions):
        return lambda s: {"text": llm.invoke([("system", instructions), ("user", s["text"])]).content}

    graph = StateGraph(State)
    graph.add_sequence([
        ("researcher", step("Research the topic.")),
        ("writer", step("Write a draft from the research.")),
        ("editor", step("Edit the draft.")),
    ])
    graph.add_edge(START, "researcher")
    return graph.compile()


def run(graph):
    return graph.invoke({"text": "AI agents"})["text"]
