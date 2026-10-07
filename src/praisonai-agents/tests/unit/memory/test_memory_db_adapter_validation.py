"""MemoryConfig.db must be a real adapter, never a bare path string (Issue #5668).

Previously ``Agent(memory={"db": "/path/to.db"})`` resolved into a
``MemoryConfig`` whose ``db`` was the raw string. The agent then stored that
string as ``self._db`` and the memory mixin called ``self._db.on_agent_start(...)``,
which raised ``'str' object has no attribute 'on_agent_start'``. The mixin
swallowed it as a warning, so persistence was silently disabled while memory
looked enabled.

The fix fails fast in ``MemoryConfig.__post_init__``: a non-adapter ``db`` is
rejected with a ``TypeError`` at construction, long before any LLM turn or the
mixin is reached.
"""
import os

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from praisonaiagents.config.feature_configs import MemoryConfig


class _FakeAdapter:
    """Minimal object exposing the DbAdapter entry hook."""

    def on_agent_start(self, *args, **kwargs):
        return []


class _FakeDbInstance:
    """Minimal object shaped like a db(...) backend instance."""

    database_url = "sqlite:///tmp/x.db"


def test_string_path_db_is_rejected():
    with pytest.raises(TypeError) as exc:
        MemoryConfig(db="/tmp/x.db")
    assert "DbAdapter" in str(exc.value)


def test_empty_string_db_is_rejected():
    with pytest.raises(TypeError):
        MemoryConfig(db="")


def test_int_db_is_rejected():
    with pytest.raises(TypeError):
        MemoryConfig(db=123)


def test_dict_memory_with_string_db_is_rejected_at_resolve():
    from praisonaiagents.config.param_resolver import resolve

    with pytest.raises(TypeError):
        resolve(
            value={"db": "/tmp/x.db", "user_id": "u1"},
            param_name="memory",
            config_class=MemoryConfig,
        )


def test_adapter_db_is_accepted():
    cfg = MemoryConfig(db=_FakeAdapter())
    assert hasattr(cfg.db, "on_agent_start")


def test_db_instance_is_accepted():
    cfg = MemoryConfig(db=_FakeDbInstance())
    assert cfg.db.database_url


def test_none_db_is_accepted():
    cfg = MemoryConfig(db=None)
    assert cfg.db is None
