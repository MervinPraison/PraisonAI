"""Opt-in real Agent.start inference after a simulated native Chroma failure."""

import os
import sys
from types import ModuleType

import pytest


@pytest.mark.live
def test_agent_runs_after_default_memory_backend_panic(monkeypatch, tmp_path):
    from praisonaiagents import Agent
    from praisonaiagents.memory.memory import Memory

    class NativePanic(BaseException):
        pass

    def fail_client(**kwargs):
        raise NativePanic("corrupt sqlite store")

    chroma = ModuleType("chromadb")
    config = ModuleType("chromadb.config")
    config.Settings = lambda **kwargs: kwargs
    chroma.PersistentClient = fail_client
    monkeypatch.setitem(sys.modules, "chromadb", chroma)
    monkeypatch.setitem(sys.modules, "chromadb.config", config)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))

    options = dict(
        instructions="Give a brief answer.",
        llm={"model": os.environ.get("PRAISONAI_TEST_MODEL", "openai/gpt-4o-mini"), "max_tokens": 96},
        reflection=False, rules=False, output="silent",
    )
    if os.environ.get("OPENAI_BASE_URL"):
        options["base_url"] = os.environ["OPENAI_BASE_URL"]
    with Memory({"rag_db_path": str(tmp_path / "chroma")}) as memory:
        assert memory.provider == "sqlite"
        with Agent(memory=memory, **options) as agent:
            answer = agent.start("Say hello in one short sentence.")
            print("Full Agent.start output:", answer)
            assert isinstance(answer, str) and answer.strip()
