"""G-19: the memory= config resolution of Agent.__init__ as a pure function.

Expected values were measured on main before the move. Reading the config's
fields into Agent locals, and the live-backend rule for clones, stay in
Agent.__init__.
"""
import pytest

from praisonaiagents import Agent
from praisonaiagents.config.agent_init import resolve_agent_memory
from praisonaiagents.config.feature_configs import MemoryConfig


class _LiveMemory:
    def search(self, *a, **k):
        return []

    def add(self, *a, **k):
        return None


class _Db:
    database_url = "sqlite:///x.db"


def _backend(cfg):
    return getattr(cfg.backend, "value", cfg.backend), cfg.history


@pytest.mark.parametrize("value", [None, False, []])
def test_no_memory(value):
    assert resolve_agent_memory(value) is None


@pytest.mark.parametrize("value, expected", [
    (True, ("file", False)),
    ("file", ("file", False)),
    ("sqlite", ("sqlite", False)),
    ("history", ("file", True)),
    ({"backend": "sqlite"}, ("sqlite", False)),
    (["file"], ("file", False)),
])
def test_resolves_to_memory_config(value, expected):
    cfg = resolve_agent_memory(value)
    assert isinstance(cfg, MemoryConfig) and _backend(cfg) == expected


@pytest.mark.parametrize("value", [MemoryConfig(backend="sqlite"), _LiveMemory(), _Db()])
def test_passthrough(value):
    assert resolve_agent_memory(value) is value


@pytest.mark.parametrize("value, error", [
    ("redis://localhost:6379", ValueError),
    (["sqlite", {"user_id": "u"}], TypeError),
])
def test_errors_unchanged(value, error):
    with pytest.raises(error):
        resolve_agent_memory(value)


def test_agent_keeps_the_resolved_config(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    mc = MemoryConfig(backend="file")
    assert Agent(name="a", instructions="x", memory=mc)._memory_config is mc
    assert Agent(name="a", instructions="x", memory=None)._memory_config is None
    # A live backend is not persisted as config, so clones rebuild an isolated one.
    assert Agent(name="a", instructions="x", memory=_LiveMemory())._memory_config is None
