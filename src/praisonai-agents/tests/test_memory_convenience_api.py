"""
Tests for the unified convenience Memory API: remember() / recall() / forget().

These are thin aliases over store_long_term / search_long_term /
delete_memory(_matching). They verify the friendly entry point works
standalone with the default local SQLite backend and that Memory() can be
constructed without an explicit config.
"""
import pytest


@pytest.fixture
def memory_config(tmp_path):
    """Minimal local SQLite config (no external providers)."""
    return {
        "provider": "sqlite",
        "short_db": str(tmp_path / "short_term.db"),
        "long_db": str(tmp_path / "long_term.db"),
    }


def test_memory_constructs_without_config():
    """Memory() should work standalone with sensible defaults."""
    from praisonaiagents.memory import Memory

    mem = Memory()
    assert mem is not None


def test_remember_recall_roundtrip(memory_config):
    """A remembered fact should be recalled with a matching query."""
    from praisonaiagents.memory import Memory

    mem = Memory(config=memory_config, verbose=0)
    mem.remember("PostgreSQL is the primary database")

    matches = mem.recall("database", limit=3)
    assert len(matches) >= 1
    assert any("PostgreSQL" in m.get("text", "") for m in matches)


def test_forget_by_id(memory_config):
    """forget(memory_id=...) removes a single record and returns 1."""
    from praisonaiagents.memory import Memory

    mem = Memory(config=memory_config, verbose=0)
    mem_id = mem.remember("Ephemeral note to delete")

    deleted = mem.forget(memory_id=mem_id)
    assert deleted == 1


def test_forget_by_query(memory_config):
    """forget(query=...) removes matching records and returns the count."""
    from praisonaiagents.memory import Memory

    mem = Memory(config=memory_config, verbose=0)
    mem.remember("Image analysis result cat")
    mem.remember("Image analysis result dog")

    deleted = mem.forget(query="Image analysis")
    assert deleted >= 1


def test_forget_requires_exactly_one_argument(memory_config):
    """forget() must be called with exactly one of memory_id or query."""
    from praisonaiagents.memory import Memory

    mem = Memory(config=memory_config, verbose=0)
    with pytest.raises(ValueError):
        mem.forget()
    with pytest.raises(ValueError):
        mem.forget(memory_id="x", query="y")


def test_forget_rejects_empty_query(memory_config):
    """forget(query="") must not trigger a broad LIKE '%%' deletion."""
    from praisonaiagents.memory import Memory

    mem = Memory(config=memory_config, verbose=0)
    mem.remember("A fact that must survive an empty-query forget")

    with pytest.raises(ValueError):
        mem.forget(query="")
    with pytest.raises(ValueError):
        mem.forget(query="   ")

    assert len(mem.recall("fact", limit=5)) >= 1
