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


# Repo root, walked up from this test file
# (.../src/praisonai-agents/tests/unit/session/test_...py -> repo root).
_REPO_ROOT = Path(__file__).resolve().parents[5]

# Directories that ship user-facing Agent examples where the same
# ``Agent(session_id=...)`` / ``Agent(db=...)`` spelling regressed (issue #4161).
_EXAMPLE_ROOTS = (
    _REPO_ROOT / "src" / "praisonai" / "praisonai" / "db",
    _REPO_ROOT / "examples" / "persistence",
)

_FICTIONAL_IMPORTS = ("PostgresAdapter",)


def _example_files():
    files = []
    for root in _EXAMPLE_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if "Agent(" in path.read_text():
                files.append(path)
    return files


_EXAMPLE_FILES = _example_files()


@pytest.mark.parametrize("path", _EXAMPLE_FILES, ids=lambda p: p.name)
@pytest.mark.parametrize("name", ["session_id", "db", "user_id"])
def test_example_files_do_not_pass_rejected_kwargs_to_agent(path, name):
    """Neither docstrings nor runnable examples may show a rejected kwarg.

    The textual session-doc guard only covered two files; the identical broken
    spelling shipped in the db package docstrings and the redis example too.
    """
    hit = re.search(TOP_LEVEL_KWARG.format(name=name), path.read_text())
    assert hit is None, f"{path.name} shows Agent({name}=...): {hit.group(0)!r}"


@pytest.mark.parametrize(
    "path", _EXAMPLE_FILES + list(DOCS), ids=lambda p: p.name
)
def test_examples_do_not_reference_nonexistent_classes(path):
    """A doc that imports a class we do not ship (e.g. ``PostgresAdapter``)."""
    text = path.read_text()
    for fictional in _FICTIONAL_IMPORTS:
        assert fictional not in text, f"{path.name} references {fictional!r}"


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
