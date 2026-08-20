"""Knowledge must resolve vector_store.provider through the adapter registry.

Regression tests for provider_mapping.get(provider, "mem0"), which made every
adapter outside a hardcoded four-name list silently resolve to Mem0.
"""
import pytest

from praisonaiagents.knowledge.adapters import (
    list_knowledge_adapters,
    register_knowledge_adapter,
)
from praisonaiagents.knowledge.adapters.registry import _knowledge_registry
from praisonaiagents.knowledge.knowledge import Knowledge


class QdrantKnowledgeAdapter:
    """Stand-in for a plugin vector store."""

    def __init__(self, config=None, verbose=0):
        self.config = config

    def store(self, *a, **k):
        pass

    def search(self, *a, **k):
        return []

    def delete(self, *a, **k):
        pass


@pytest.fixture
def qdrant():
    register_knowledge_adapter("qdrant", QdrantKnowledgeAdapter)
    yield
    _knowledge_registry._adapters.pop("qdrant", None)


def test_registered_adapter_is_honoured(qdrant):
    """A registered adapter outside the legacy list must be used, not Mem0."""
    k = Knowledge(config={"vector_store": {"provider": "qdrant"}})
    assert isinstance(k.memory, QdrantKnowledgeAdapter)


def test_every_registered_adapter_is_reachable():
    """No registered adapter may be unreachable through the public config."""
    unreachable = []
    for name in list_knowledge_adapters():
        k = Knowledge(config={"vector_store": {"provider": name}})
        try:
            resolved = type(k.memory).__name__
        except Exception:
            continue  # backend present but not constructible in this env
        if name != "mem0" and resolved == "Mem0Adapter":
            unreachable.append(name)
    assert unreachable == [], f"registered but resolve to Mem0: {unreachable}"


def test_unknown_provider_raises_instead_of_silently_using_mem0():
    k = Knowledge(config={"vector_store": {"provider": "definitely_not_a_store"}})
    with pytest.raises(ValueError, match="definitely_not_a_store"):
        k.memory


@pytest.mark.parametrize("bad_provider", ["", None])
def test_explicit_falsey_provider_raises_instead_of_silently_using_mem0(bad_provider):
    """An explicitly supplied empty/null provider is a misconfiguration and must
    raise, rather than being treated as the implicit default and degrading to Mem0.
    """
    k = Knowledge(config={"vector_store": {"provider": bad_provider}})
    with pytest.raises(ValueError):
        k.memory
