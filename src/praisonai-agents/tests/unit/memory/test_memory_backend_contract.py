"""The declared memory backends must match the ones that can be built."""
import pytest

from praisonaiagents import Agent, MemoryConfig
from praisonaiagents.config.feature_configs import MemoryBackend
from praisonaiagents.config.param_resolver import resolve, ArrayMode
from praisonaiagents.config.presets import MEMORY_PRESETS, MEMORY_URL_SCHEMES
from praisonaiagents.memory.adapters import list_memory_adapters, register_memory_adapter
from praisonaiagents.memory.adapters.in_memory_adapter import InMemoryAdapter
from praisonaiagents.memory.adapters.registry import get_default_memory_registry
from praisonaiagents.memory.memory import Memory


def _agent(**kw):
    return Agent(name="t", instructions="Be helpful", llm="gpt-4o-mini", **kw)


def test_memory_backend_enum_matches_registry():
    declared = {m.value for m in MemoryBackend}
    implemented = set(list_memory_adapters()) | {"file"}
    assert declared == implemented, (
        f"MemoryBackend declares {sorted(declared - implemented)} with no adapter")


@pytest.mark.parametrize("backend", ["redis", "postgres", "valkey"])
def test_unimplemented_backend_raises_instead_of_substituting(backend):
    with pytest.raises(ValueError, match="not implemented"):
        _agent(memory=MemoryConfig(backend=backend))


def test_sqlite_means_sqlite_on_agent_and_on_memory():
    """'sqlite' must not mean SQLite on Memory and ChromaDB on Agent."""
    assert _agent(memory=MemoryConfig(backend="sqlite"))._memory_instance.provider == "sqlite"
    assert Memory({"provider": "sqlite"}).provider == "sqlite"


def test_unknown_provider_on_memory_raises():
    with pytest.raises(ValueError, match="redis"):
        Memory({"provider": "redis"})


def test_url_scheme_without_adapter_raises():
    with pytest.raises(ValueError, match="redis"):
        resolve(value="redis://localhost:6379/0", param_name="memory",
                config_class=MemoryConfig, presets=MEMORY_PRESETS,
                url_schemes=MEMORY_URL_SCHEMES, array_mode=ArrayMode.SINGLE_OR_LIST)


def test_registered_custom_backend_is_honoured():
    """register_memory_adapter() is the supported escape hatch."""
    class MyRedisAdapter(InMemoryAdapter):
        pass

    register_memory_adapter("redis", MyRedisAdapter)
    try:
        agent = _agent(memory=MemoryConfig(backend="redis"))
        assert isinstance(agent._memory_instance.memory_adapter, MyRedisAdapter)
    finally:
        get_default_memory_registry()._adapters.pop("redis", None)
