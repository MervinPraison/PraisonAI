"""Facts stored via ``agent.store_memory()`` reach the model on every backend (#6040).

The full ``Memory`` class (sqlite/chroma/mem0) returns no system-prompt context
without a query, so recall depends on turn-start prefetch, which now defaults to
"auto" (on for those backends, off for FileMemory).
"""

import asyncio

import pytest

from praisonaiagents import Agent, MemoryConfig
from praisonaiagents.model_harness import ScriptedModel

FACT = "The project codename is BLUEHERON."
QUESTION = "What is the project codename?"


@pytest.fixture(autouse=True)
def _isolated_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home" / ".praisonai"))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)  # the SQLite backend writes under the cwd


def _sent_to_model(model: ScriptedModel, needle: str) -> bool:
    request = model.requests[0]
    if needle in (request.system_prompt or ""):
        return True
    return any(needle in str(m.get("content")) for m in request.messages)


def _ask(memory, *, use_async: bool, fact: str = FACT) -> ScriptedModel:
    model = ScriptedModel(["(answer)"])
    agent = Agent(
        name="recall",
        instructions="You are a helpful assistant.",
        llm=model,
        memory=memory,
        output="silent",
    )
    agent.store_memory(fact, memory_type="long_term")
    if use_async:
        asyncio.run(agent.achat(QUESTION))
    else:
        agent.chat(QUESTION)
    return model


@pytest.mark.parametrize("use_async", [False, True], ids=["sync", "async"])
@pytest.mark.parametrize(
    "memory",
    [
        {"user_id": "u1"},
        "sqlite",
        MemoryConfig(backend="sqlite", user_id="u1"),
        MemoryConfig(backend="sqlite", user_id="u1", prefetch=True),
    ],
    ids=["file", "sqlite", "sqlite+user_id", "sqlite+user_id+prefetch"],
)
def test_stored_fact_reaches_model(memory, use_async):
    model = _ask(memory, use_async=use_async)
    assert _sent_to_model(model, "BLUEHERON")


@pytest.mark.parametrize("use_async", [False, True], ids=["sync", "async"])
def test_prefetch_false_still_disables_recall(use_async):
    model = _ask(
        MemoryConfig(backend="sqlite", user_id="u1", prefetch=False),
        use_async=use_async,
    )
    assert not _sent_to_model(model, "BLUEHERON")


def test_other_user_records_are_not_recalled():
    # u2 writes a fact; u1 asks the same question and must not see it.
    _ask(MemoryConfig(backend="sqlite", user_id="u2"), use_async=False)
    model = _ask(
        MemoryConfig(backend="sqlite", user_id="u1"),
        use_async=False,
        fact="The project codename is SECRETOWL.",
    )
    assert _sent_to_model(model, "SECRETOWL")
    assert not _sent_to_model(model, "BLUEHERON")


def test_store_long_term_stamps_configured_user_id():
    from praisonaiagents.memory.memory import Memory

    memory = Memory({"provider": "sqlite", "user_id": "u1"})
    assert memory._stamp_user_id(None) == {"user_id": "u1"}
    # An explicit metadata user_id wins and the caller's dict is not mutated.
    meta = {"user_id": "other"}
    assert memory._stamp_user_id(meta) == {"user_id": "other"}
    assert meta == {"user_id": "other"}
    assert Memory({"provider": "sqlite"})._stamp_user_id({"k": 1}) == {"k": 1}
