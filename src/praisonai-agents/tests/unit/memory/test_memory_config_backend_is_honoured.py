"""MemoryConfig.backend must survive being combined with config=.

MemoryConfig validates `backend` in __post_init__ and echoes it from
to_dict(). But Agent's construction path had:

    elif _memory_config.config:
        memory = _memory_config.config

handing _init_memory the bare config dict. _init_memory reads the provider as
`memory.get("provider", memory.get("backend", "file"))`, so the backend was
never seen and the agent quietly built a FileMemory:

    backend='sqlite', no config     -> Memory      provider=sqlite
    backend='sqlite' + config={...} -> FileMemory  provider=None   <- dropped

...while to_dict() went on reporting 'sqlite'. Adding a config dict silently
downgraded the backend, which is the opposite of what supplying more
configuration should do.
"""
import os
import tempfile

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import MemoryConfig


def _memory_of(config):
    agent = Agent(name="t", instructions="x", llm="gpt-4o-mini", memory=config)
    return getattr(agent, "_memory_instance", None) or getattr(agent, "memory", None)


def _provider(instance):
    return getattr(instance, "provider", None) or getattr(instance, "_provider", None)


@pytest.fixture
def db_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


class TestBackendSurvivesAConfigDict:

    def test_backend_is_honoured_alongside_config(self, db_dir):
        inst = _memory_of(MemoryConfig(
            backend="sqlite", user_id="u1", config={"short_db": db_dir + "/s.db"}))
        assert _provider(inst) == "sqlite", (
            "supplying config= silently discarded the backend"
        )

    def test_it_matches_the_no_config_case(self, db_dir):
        """Adding configuration must not change which backend is chosen."""
        without = _memory_of(MemoryConfig(backend="sqlite", user_id="u1"))
        with_cfg = _memory_of(MemoryConfig(
            backend="sqlite", user_id="u1", config={"short_db": db_dir + "/s.db"}))
        assert type(with_cfg).__name__ == type(without).__name__
        assert _provider(with_cfg) == _provider(without)

    def test_an_explicit_provider_in_config_still_wins(self, db_dir):
        """The dict is the more specific statement of intent."""
        inst = _memory_of(MemoryConfig(
            backend="sqlite", user_id="u1", config={"provider": "file"}))
        assert type(inst).__name__ == "FileMemory"

    def test_an_explicit_backend_key_in_config_still_wins(self, db_dir):
        inst = _memory_of(MemoryConfig(
            backend="sqlite", user_id="u1", config={"backend": "file"}))
        assert type(inst).__name__ == "FileMemory"

    def test_file_backend_is_unchanged(self, db_dir):
        """The default path must not be disturbed."""
        inst = _memory_of(MemoryConfig(backend="file", user_id="u1"))
        assert type(inst).__name__ == "FileMemory"

    def test_the_callers_config_dict_is_not_mutated(self, db_dir):
        """Injecting the provider must not write into the user's own dict."""
        cfg = {"short_db": db_dir + "/s.db"}
        _memory_of(MemoryConfig(backend="sqlite", user_id="u1", config=cfg))
        assert "provider" not in cfg, "the caller's dict was mutated in place"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
