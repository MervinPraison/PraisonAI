"""
Unit tests for the Dakera memory adapter (``DakeraMemoryAdapter``).

These tests inject a fake ``dakera`` module into ``sys.modules`` so the adapter
can be exercised end-to-end without a running Dakera server or the real SDK,
mirroring how the other wrapper adapters (mem0/chroma/mongodb) are unit tested.
"""

import os
import sys
import types

import pytest


# ---------------------------------------------------------------------------
# Fake dakera SDK
# ---------------------------------------------------------------------------

class _FakeRecalledMemory:
    def __init__(self, id, content, memory_type, importance=0.5, score=0.9,
                 metadata=None):
        self.id = id
        self.content = content
        self.memory_type = memory_type
        self.importance = importance
        self.score = score
        self.metadata = metadata or {}


class _FakeRecallResponse:
    def __init__(self, memories):
        self.memories = memories


class _FakeBatchResponse:
    def __init__(self, memories):
        self.memories = memories
        self.total = len(memories)
        self.filtered = len(memories)


class _FakeBatchRecallRequest:
    def __init__(self, agent_id, filter=None, limit=100, min_importance=None):
        self.agent_id = agent_id
        self.filter = filter
        self.limit = limit
        self.min_importance = min_importance


class _FakeBatchForgetRequest:
    def __init__(self, agent_id, filter=None):
        self.agent_id = agent_id
        self.filter = filter


class _FakeBatchMemoryFilter:
    def __init__(self, memory_type=None, **kwargs):
        self.memory_type = memory_type
        self.kwargs = kwargs


class _FakeDakeraClient:
    """Records calls and returns canned responses."""

    instances = []

    def __init__(self, base_url=None, api_key=None):
        self.base_url = base_url
        self.api_key = api_key
        self.stored = []
        self.recall_calls = []
        self.batch_recall_calls = []
        self.forgotten = []
        self.batch_forget_calls = []
        self._counter = 0
        _FakeDakeraClient.instances.append(self)

    def store_memory(self, agent_id, content, memory_type="episodic",
                     importance=None, metadata=None, session_id=None, tags=None,
                     **kwargs):
        self._counter += 1
        mem = {
            "id": f"mem-{self._counter}",
            "content": content,
            "memory_type": memory_type,
            "importance": importance,
            "metadata": metadata,
            "session_id": session_id,
            "tags": tags,
        }
        self.stored.append(mem)
        return mem

    def recall(self, agent_id, query, top_k=5, memory_type=None,
               min_importance=None, **kwargs):
        self.recall_calls.append({
            "agent_id": agent_id, "query": query, "top_k": top_k,
            "memory_type": memory_type, "min_importance": min_importance,
        })
        mems = [
            m for m in self.stored
            if memory_type is None or m["memory_type"] == memory_type
        ][:top_k]
        return _FakeRecallResponse([
            _FakeRecalledMemory(m["id"], m["content"], m["memory_type"],
                                metadata=m["metadata"])
            for m in mems
        ])

    def batch_recall(self, request):
        self.batch_recall_calls.append(request)
        return _FakeBatchResponse([
            _FakeRecalledMemory(m["id"], m["content"], m["memory_type"],
                                metadata=m["metadata"])
            for m in self.stored[:request.limit]
        ])

    def forget(self, agent_id, memory_id):
        self.forgotten.append(memory_id)
        return {"deleted": 1}

    def batch_forget(self, request):
        self.batch_forget_calls.append(request)
        return {"deleted": 0}


def _make_fake_dakera():
    mod = types.ModuleType("dakera")
    mod.DakeraClient = _FakeDakeraClient
    mod.BatchRecallRequest = _FakeBatchRecallRequest
    mod.BatchForgetRequest = _FakeBatchForgetRequest
    mod.BatchMemoryFilter = _FakeBatchMemoryFilter
    return mod


@pytest.fixture
def fake_dakera(monkeypatch):
    """Install a fake ``dakera`` module for the duration of a test."""
    _FakeDakeraClient.instances = []
    monkeypatch.setitem(sys.modules, "dakera", _make_fake_dakera())
    # Ensure adapter config is not polluted by ambient env.
    for var in ("DAKERA_URL", "DAKERA_API_URL", "DAKERA_API_KEY", "DAKERA_AGENT_ID"):
        monkeypatch.delenv(var, raising=False)
    yield


def _make_adapter(**config):
    from praisonaiagents.memory.adapters.factories import create_dakera_memory_adapter
    return create_dakera_memory_adapter(config=config)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class TestDakeraRegistration:
    def test_factory_is_registered(self):
        from praisonaiagents.memory.adapters.registry import (
            list_memory_adapters, has_memory_adapter,
        )
        assert "dakera" in list_memory_adapters()
        assert has_memory_adapter("dakera")

    def test_factory_missing_dependency_raises_importerror(self, monkeypatch):
        # Block the import so the factory's ImportError branch is exercised.
        monkeypatch.setitem(sys.modules, "dakera", None)
        from praisonaiagents.memory.adapters.factories import (
            create_dakera_memory_adapter,
        )
        with pytest.raises(ImportError) as exc:
            create_dakera_memory_adapter()
        assert "dakera" in str(exc.value).lower()

    def test_memory_explicit_dakera_surfaces_install_hint(self, monkeypatch):
        # Full Memory(config={"provider": "dakera"}) path: when the SDK is
        # missing, the explicit-provider branch must re-raise the factory's
        # ImportError (with the install hint) rather than silently falling back
        # to sqlite/in_memory.
        monkeypatch.setitem(sys.modules, "dakera", None)
        from praisonaiagents.memory.memory import Memory
        with pytest.raises(ImportError) as exc:
            Memory(config={"provider": "dakera"})
        assert "dakera" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class TestDakeraConfig:
    def test_defaults(self, fake_dakera):
        adapter = _make_adapter()
        assert adapter.agent_id == "praisonai"
        assert adapter.short_term_type == "working"
        assert adapter.long_term_type == "episodic"
        assert adapter.client.base_url == "http://localhost:3000"

    def test_explicit_config(self, fake_dakera):
        adapter = _make_adapter(
            url="http://dakera.internal:3000",
            api_key="dk-secret",
            agent_id="agent-42",
            short_term_type="working",
            long_term_type="semantic",
        )
        assert adapter.client.base_url == "http://dakera.internal:3000"
        assert adapter.client.api_key == "dk-secret"
        assert adapter.agent_id == "agent-42"
        assert adapter.long_term_type == "semantic"

    def test_env_fallback(self, fake_dakera, monkeypatch):
        monkeypatch.setenv("DAKERA_URL", "http://env-host:3000")
        monkeypatch.setenv("DAKERA_API_KEY", "dk-env")
        monkeypatch.setenv("DAKERA_AGENT_ID", "env-agent")
        adapter = _make_adapter()
        assert adapter.client.base_url == "http://env-host:3000"
        assert adapter.client.api_key == "dk-env"
        assert adapter.agent_id == "env-agent"


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------

class TestDakeraProtocol:
    def test_implements_memory_protocol(self, fake_dakera):
        from praisonaiagents.memory.protocols import (
            MemoryProtocol, DeletableMemoryProtocol, ResettableMemoryProtocol,
        )
        adapter = _make_adapter()
        assert isinstance(adapter, MemoryProtocol)
        assert isinstance(adapter, DeletableMemoryProtocol)
        assert isinstance(adapter, ResettableMemoryProtocol)


# ---------------------------------------------------------------------------
# Store / search
# ---------------------------------------------------------------------------

class TestDakeraStoreSearch:
    def test_store_short_term_uses_working_type(self, fake_dakera):
        adapter = _make_adapter()
        mem_id = adapter.store_short_term("scratch note")
        assert mem_id == "mem-1"
        assert adapter.client.stored[0]["memory_type"] == "working"
        assert adapter.client.stored[0]["content"] == "scratch note"

    def test_store_long_term_uses_episodic_type(self, fake_dakera):
        adapter = _make_adapter()
        adapter.store_long_term("durable fact")
        assert adapter.client.stored[0]["memory_type"] == "episodic"

    def test_store_extracts_importance_and_tags(self, fake_dakera):
        adapter = _make_adapter()
        adapter.store_long_term(
            "important fact",
            metadata={"importance": 0.95, "tags": ["pref"], "topic": "food"},
        )
        stored = adapter.client.stored[0]
        assert stored["importance"] == 0.95
        assert stored["tags"] == ["pref"]
        # Non-reserved metadata keys survive.
        assert stored["metadata"] == {"topic": "food"}

    def test_store_kwargs_reserved_keys_do_not_leak_into_metadata(self, fake_dakera):
        # Reserved keys passed via kwargs must win over metadata AND be stripped
        # from the metadata copy, so they never leak into the stored payload.
        # Regression for the short-circuit `or` that skipped meta.pop() whenever
        # the kwarg was truthy, leaving a stale session_id/tags in metadata.
        adapter = _make_adapter()
        adapter.store_long_term(
            "fact",
            metadata={"session_id": "meta-sess", "tags": ["from-meta"], "topic": "food"},
            session_id="kw-sess",
            tags=["from-kwargs"],
            importance=0.8,
        )
        stored = adapter.client.stored[0]
        assert stored["session_id"] == "kw-sess"
        assert stored["tags"] == ["from-kwargs"]
        assert stored["importance"] == 0.8
        # Reserved keys stripped from metadata regardless of their source.
        assert stored["metadata"] == {"topic": "food"}

    def test_store_uses_default_importance(self, fake_dakera):
        adapter = _make_adapter(default_importance=0.3)
        adapter.store_short_term("note")
        assert adapter.client.stored[0]["importance"] == 0.3

    def test_search_short_term_filters_working(self, fake_dakera):
        adapter = _make_adapter()
        adapter.store_short_term("short one")
        adapter.store_long_term("long one")
        results = adapter.search_short_term("one", limit=3)
        assert adapter.client.recall_calls[-1]["memory_type"] == "working"
        assert len(results) == 1
        assert results[0]["text"] == "short one"
        assert results[0]["memory_type"] == "working"
        # Normalised result dict shape.
        assert set(results[0]) >= {"id", "text", "metadata", "score"}

    def test_search_long_term_filters_episodic(self, fake_dakera):
        adapter = _make_adapter()
        adapter.store_short_term("short one")
        adapter.store_long_term("long one")
        results = adapter.search_long_term("one")
        assert adapter.client.recall_calls[-1]["memory_type"] == "episodic"
        assert [r["text"] for r in results] == ["long one"]

    def test_get_all_memories_uses_batch_recall(self, fake_dakera):
        adapter = _make_adapter()
        adapter.store_short_term("a")
        adapter.store_long_term("b")
        results = adapter.get_all_memories()
        assert len(adapter.client.batch_recall_calls) == 1
        assert {r["text"] for r in results} == {"a", "b"}


# ---------------------------------------------------------------------------
# Delete / reset
# ---------------------------------------------------------------------------

class TestDakeraDeleteReset:
    def test_delete_memory_success(self, fake_dakera):
        adapter = _make_adapter()
        assert adapter.delete_memory("mem-1") is True
        assert adapter.client.forgotten == ["mem-1"]

    def test_delete_memory_failure_returns_false(self, fake_dakera):
        adapter = _make_adapter()

        def boom(agent_id, memory_id):
            raise RuntimeError("network down")

        adapter.client.forget = boom
        assert adapter.delete_memory("mem-x") is False

    def test_delete_memories_counts(self, fake_dakera):
        adapter = _make_adapter()
        assert adapter.delete_memories(["a", "b", "c"]) == 3
        assert adapter.client.forgotten == ["a", "b", "c"]

    def test_reset_short_term_filters_working(self, fake_dakera):
        adapter = _make_adapter()
        adapter.reset_short_term()
        req = adapter.client.batch_forget_calls[-1]
        assert req.filter.memory_type == "working"

    def test_reset_long_term_filters_episodic(self, fake_dakera):
        adapter = _make_adapter()
        adapter.reset_long_term()
        req = adapter.client.batch_forget_calls[-1]
        assert req.filter.memory_type == "episodic"


# ---------------------------------------------------------------------------
# Real-SDK integration (gated) — exercises the actual `dakera` client against a
# live self-hosted server. Skipped unless DAKERA_URL is set (e.g. a local
# `dakera-ai/dakera-deploy` compose), so CI stays hermetic while the real
# round-trip can be verified on demand:  DAKERA_URL=http://localhost:3000 pytest
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.getenv("DAKERA_URL"),
    reason="requires a running Dakera server (set DAKERA_URL to enable)",
)
class TestDakeraRealSDK:
    def test_store_then_recall_roundtrip(self):
        pytest.importorskip("dakera")
        from praisonaiagents.memory.adapters.factories import (
            create_dakera_memory_adapter,
        )

        adapter = create_dakera_memory_adapter(
            config={"agent_id": "praisonai-itest", "default_importance": 0.9}
        )
        adapter.reset_long_term()
        adapter.store_long_term(
            "The user's favourite programming language is Rust.",
            metadata={"topic": "preferences"},
        )
        results = adapter.search_long_term("what language does the user like?", limit=5)
        assert any("Rust" in r["text"] for r in results)
        adapter.reset_long_term()
