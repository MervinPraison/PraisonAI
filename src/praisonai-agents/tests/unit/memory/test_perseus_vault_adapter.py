"""
Unit tests for the Perseus Vault memory adapter (``PerseusVaultMemoryAdapter``).

These tests inject a fake MCP stdio client so the adapter can be exercised
end-to-end without the real ``perseus-vault`` binary, mirroring how the other
wrapper adapters (dakera/mem0/chroma/mongodb) are unit tested.
"""

import json
import sys
import types

import pytest

from praisonaiagents.memory.adapters.perseus_vault_adapter import (
    PerseusVaultMemoryAdapter,
)
from praisonaiagents.memory.protocols import MemoryProtocol


# ---------------------------------------------------------------------------
# Fake MCP stdio client — records calls, models the vault's entity semantics
# ---------------------------------------------------------------------------

class _FakeVaultClient:
    """Stand-in for `_VaultStdioClient` that stores entities in a dict keyed by
    (category, key) and answers the handful of tools the adapter uses."""

    def __init__(self):
        self.entities = {}          # (category, key) -> body dict
        self.calls = []             # (tool_name, arguments)

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))

        if name == "perseus_vault_remember":
            cat = arguments["category"]
            key = arguments["key"]
            self.entities[(cat, key)] = json.loads(arguments["body_json"])
            return {"action": "created", "key": key}

        if name == "perseus_vault_recall":
            cat = arguments.get("category")
            query = (arguments.get("query") or "").lower()
            items = []
            for (c, k), body in self.entities.items():
                if cat is not None and c != cat:
                    continue
                content = str(body.get("content", "")).lower()
                # Empty query = enumerate all in category; else substring match
                # on any whitespace-separated term (models FTS5 OR semantics).
                if query == "" or any(tok in content for tok in query.split()):
                    items.append({"key": k, "body_json": json.dumps(body), "score": 0.5})
            return {"items": items, "total": len(items)}

        if name == "perseus_vault_prune":
            cat = arguments.get("category")
            if arguments.get("purge_all"):
                doomed = [(c, k) for (c, k) in self.entities if c == cat]
                for key in doomed:
                    del self.entities[key]
                return {"archived": len(doomed), "examined": len(doomed)}
            return {"archived": 0}

        if name == "perseus_vault_forget":
            key = (arguments["category"], arguments["key"])
            existed = key in self.entities
            self.entities.pop(key, None)
            return {"archived": 1 if existed else 0}

        if name == "perseus_vault_context":
            return {"markdown": "## Perseus Vault Context\n\n- (test)\n",
                    "entities_injected": len(self.entities)}

        raise AssertionError(f"unexpected tool {name}")

    def close(self):
        pass


def _make_adapter(**config):
    return PerseusVaultMemoryAdapter(config=config, client=_FakeVaultClient())


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class TestPerseusVaultRegistration:
    def test_factory_is_registered(self):
        from praisonaiagents.memory.adapters.registry import (
            list_memory_adapters, has_memory_adapter,
        )
        assert "perseus_vault" in list_memory_adapters()
        assert has_memory_adapter("perseus_vault")

    def test_factory_missing_binary_raises(self, monkeypatch):
        # Force the real client path and make the spawn fail like a missing binary.
        from praisonaiagents.memory.adapters import perseus_vault_adapter as mod

        def _boom(*a, **k):
            raise FileNotFoundError("no such file: perseus-vault")

        monkeypatch.setattr(mod, "_VaultStdioClient", _boom)
        from praisonaiagents.memory.adapters.factories import (
            create_perseus_vault_memory_adapter,
        )
        with pytest.raises(FileNotFoundError) as exc:
            create_perseus_vault_memory_adapter(binary="perseus-vault")
        assert "perseus-vault" in str(exc.value).lower()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class TestPerseusVaultConfig:
    def test_defaults(self):
        adapter = _make_adapter()
        assert adapter._st_cat == "working"
        assert adapter._lt_cat == "episodic"
        assert adapter._search_mode == "hybrid"

    def test_explicit_config(self):
        adapter = _make_adapter(
            short_term_category="scratch",
            long_term_category="semantic",
            search_mode="fts5",
            default_importance=0.9,
        )
        assert adapter._st_cat == "scratch"
        assert adapter._lt_cat == "semantic"
        assert adapter._search_mode == "fts5"
        assert adapter._default_importance == 0.9

    def test_env_fallback(self, monkeypatch):
        monkeypatch.setenv("PERSEUS_VAULT_BIN", "/opt/pv/perseus-vault")
        monkeypatch.setenv("PERSEUS_VAULT_DB", "/data/pv.db")
        adapter = _make_adapter()
        assert adapter._binary == "/opt/pv/perseus-vault"
        assert adapter._db_path == "/data/pv.db"


# ---------------------------------------------------------------------------
# Protocol conformance + behavior
# ---------------------------------------------------------------------------

class TestPerseusVaultBehavior:
    def test_satisfies_memory_protocol(self):
        adapter = _make_adapter()
        assert isinstance(adapter, MemoryProtocol)

    def test_store_and_search_short_term(self):
        adapter = _make_adapter()
        key = adapter.store_short_term("blue-green deployment health gate", {"topic": "deploy"})
        assert key.startswith("working-")
        hits = adapter.search_short_term("deployment", limit=5)
        assert len(hits) == 1
        assert "blue-green" in hits[0]["text"]
        assert hits[0]["metadata"] == {"topic": "deploy"}

    def test_store_and_search_long_term(self):
        adapter = _make_adapter()
        adapter.store_long_term("chose SQLite FTS5 for the index", {"topic": "arch"})
        hits = adapter.search_long_term("SQLite", limit=5)
        assert len(hits) == 1
        assert "FTS5" in hits[0]["text"]

    def test_tiers_are_isolated(self):
        adapter = _make_adapter()
        adapter.store_short_term("short lived note about caching", None)
        adapter.store_long_term("durable architectural decision", None)
        # A short-term query must not return the long-term entity and vice versa.
        assert adapter.search_short_term("architectural") == []
        assert adapter.search_long_term("caching") == []

    def test_explicit_key_via_metadata(self):
        adapter = _make_adapter()
        key = adapter.store_long_term("pinned fact", {"key": "fact-1"})
        assert key == "fact-1"

    def test_get_all_memories_spans_both_tiers(self):
        adapter = _make_adapter()
        adapter.store_short_term("one", None)
        adapter.store_long_term("two", None)
        allm = adapter.get_all_memories()
        assert len(allm) == 2

    def test_reset_short_term_preserves_long_term(self):
        adapter = _make_adapter()
        adapter.store_short_term("ephemeral", None)
        adapter.store_long_term("permanent", None)
        adapter.reset_short_term()
        assert adapter.search_short_term("ephemeral") == []
        assert len(adapter.search_long_term("permanent")) == 1

    def test_reset_long_term_preserves_short_term(self):
        adapter = _make_adapter()
        adapter.store_short_term("ephemeral", None)
        adapter.store_long_term("permanent", None)
        adapter.reset_long_term()
        assert adapter.search_long_term("permanent") == []
        assert len(adapter.search_short_term("ephemeral")) == 1

    def test_delete_memory(self):
        adapter = _make_adapter()
        key = adapter.store_long_term("to be deleted", {"key": "del-1"})
        assert adapter.delete_memory(key) is True
        assert adapter.search_long_term("deleted") == []

    def test_delete_memories_counts(self):
        adapter = _make_adapter()
        adapter.store_long_term("a", {"key": "k1"})
        adapter.store_long_term("b", {"key": "k2"})
        assert adapter.delete_memories(["k1", "k2"]) == 2

    def test_delete_memory_short_term_hint(self):
        adapter = _make_adapter()
        adapter.store_short_term("scratch note", {"key": "st-1"})
        # The MemoryProtocol hint "short_term" must target the short-term tier.
        assert adapter.delete_memory("st-1", memory_type="short_term") is True
        assert adapter.search_short_term("scratch") == []

    def test_delete_missing_reports_false(self):
        adapter = _make_adapter()
        # Nothing stored, so nothing is archived -> must not report success.
        assert adapter.delete_memory("does-not-exist") is False

    def test_importance_propagated_from_kwargs(self):
        client = _FakeVaultClient()
        adapter = PerseusVaultMemoryAdapter(config={}, client=client)
        adapter.store_long_term("weighted fact", {"key": "w1"}, importance=0.87)
        remember = [c for c in client.calls if c[0] == "perseus_vault_remember"][-1]
        assert remember[1]["importance"] == 0.87

    def test_search_metadata_and_score_never_none(self):
        adapter = _make_adapter()
        # Stored without metadata: result metadata must be {} not None, and
        # score must be numeric so downstream filtering never crashes.
        adapter.store_long_term("bare memory with no metadata", None)
        hits = adapter.search_long_term("bare", limit=5)
        assert len(hits) == 1
        assert hits[0]["metadata"] == {}
        assert isinstance(hits[0]["score"], (int, float))

    def test_get_context_returns_markdown(self):
        adapter = _make_adapter()
        adapter.store_long_term("some fact", None)
        ctx = adapter.get_context(query="fact")
        assert ctx.startswith("## Perseus Vault Context")
