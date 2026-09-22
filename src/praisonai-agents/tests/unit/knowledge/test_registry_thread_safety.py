"""
Unit tests for thread-safe knowledge registries.

Covers:
- Singleton identity under concurrent construction
- register/get/list/clear racing safely without KeyError or iteration errors
"""

import threading

import pytest

from praisonaiagents.knowledge.retrieval import (
    RetrieverRegistry,
    get_retriever_registry,
)
from praisonaiagents.knowledge.rerankers import (
    RerankerRegistry,
    get_reranker_registry,
    SimpleReranker,
)


@pytest.mark.parametrize("factory", [get_retriever_registry, get_reranker_registry])
def test_singleton_identity_under_concurrent_construction(factory):
    """Simultaneous construction must return one shared instance."""
    start = threading.Barrier(16)
    instances = []
    lock = threading.Lock()

    def build():
        start.wait()
        inst = factory()
        with lock:
            instances.append(inst)

    threads = [threading.Thread(target=build) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(instances) == 16
    first = instances[0]
    assert all(inst is first for inst in instances)


def test_retriever_registry_concurrent_ops_are_safe():
    """register/get/list/clear racing must not raise KeyError or iteration errors."""
    registry = get_retriever_registry()
    registry.clear()

    def make_factory(tag):
        def _factory(**kwargs):
            class _R:
                name = tag
                strategy = None

                def retrieve(self, *a, **k):
                    return []

                async def aretrieve(self, *a, **k):
                    return []

            return _R()
        return _factory

    errors = []
    barrier = threading.Barrier(20)

    def worker(i):
        barrier.wait()
        try:
            for _ in range(50):
                registry.register(f"r{i}", make_factory(f"r{i}"))
                registry.list_retrievers()
                registry.get(f"r{i}")
                if i % 5 == 0:
                    registry.clear()
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Concurrent registry ops raised: {errors}"
    registry.clear()


def test_reranker_registry_concurrent_ops_are_safe():
    """register/get/list/clear racing must not raise for the reranker registry."""
    registry = get_reranker_registry()
    registry.clear()

    errors = []
    barrier = threading.Barrier(20)

    def worker(i):
        barrier.wait()
        try:
            for _ in range(50):
                registry.register(f"rr{i}", SimpleReranker)
                registry.list_rerankers()
                registry.get(f"rr{i}")
                if i % 5 == 0:
                    registry.clear()
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Concurrent registry ops raised: {errors}"

    registry.clear()
    registry.register("simple", SimpleReranker)


def test_get_returns_none_for_unknown_name():
    """Unknown names return None (both registries)."""
    r = get_retriever_registry()
    r.clear()
    assert r.get("missing") is None

    rr = get_reranker_registry()
    assert rr.get("missing") is None
