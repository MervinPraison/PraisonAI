"""The session module's documented quick start must actually run.

`session/__init__.py` and `session/README.md` documented
`Agent(name=..., session_id=...)`, which raises
``TypeError: Agent.__init__() got unexpected keyword argument(s): session_id``.
The working spelling puts session_id on the memory config.
"""

import re
from pathlib import Path

import pytest

import praisonaiagents.session as session_pkg
from praisonaiagents import Agent, MemoryConfig

# ``Agent(`` ... ``session_id=`` with no *nested* call in between, so
# ``Agent(memory=MemoryConfig(session_id=...))`` is correctly not matched.
TOP_LEVEL_KWARG = r"Agent\((?:[^()]|\([^()]*\))*?\b{name}="

DOCS = (
    Path(session_pkg.__file__).parent / "__init__.py",
    Path(session_pkg.__file__).parent / "README.md",
)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
    import praisonaiagents.session.store as store_module

    monkeypatch.setattr(store_module, "_default_store", None, raising=False)


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
@pytest.mark.parametrize("name", ["session_id", "user_id", "db", "prompt_caching"])
def test_docs_do_not_pass_rejected_kwargs_to_agent(doc, name):
    """No session doc may show a kwarg Agent.__init__ rejects."""
    hit = re.search(TOP_LEVEL_KWARG.format(name=name), doc.read_text())
    assert hit is None, f"{doc.name} shows Agent({name}=...): {hit.group(0)!r}"


@pytest.mark.parametrize("name", ["session_id", "user_id", "db", "prompt_caching"])
def test_agent_rejects_those_kwargs(name):
    """The other half of the contract: they really are rejected."""
    with pytest.raises(TypeError, match=name):
        Agent(name="Assistant", **{name: "x"})


def test_documented_spellings_construct_and_restore():
    """The spelling the fixed docs show works, and restores history."""
    from praisonaiagents.session import get_default_session_store

    assert (
        Agent(name="A", memory={"session_id": "my-session-123"})
        ._memory_config.session_id
        == "my-session-123"
    )

    get_default_session_store().add_user_message(
        "my-session-123", "Hello, my name is Alice"
    )
    agent = Agent(name="Assistant", memory=MemoryConfig(session_id="my-session-123"))
    agent._init_session_store()

    assert agent.chat_history == [
        {"role": "user", "content": "Hello, my name is Alice"}
    ]
