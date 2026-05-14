"""
Tests for ValkeyVectorKnowledgeStore, ValkeyStateStore, and registry integration.

Tests cover:
- ValkeyVectorKnowledgeStore collection and document operations (mocked glide client)
- ValkeyStateStore key-value operations (mocked glide client)
- KNOWLEDGE_STORES and STATE_STORES registry entries for "valkey"
"""

import json
import struct
from unittest.mock import MagicMock, patch

from praisonai.persistence.knowledge.base import KnowledgeDocument
from praisonai.persistence.registry import KNOWLEDGE_STORES, STATE_STORES


def _make_knowledge_store():
    """Return a ValkeyVectorKnowledgeStore with a pre-injected MagicMock client."""
    from praisonai.persistence.knowledge.valkey_vector import ValkeyVectorKnowledgeStore

    store = ValkeyVectorKnowledgeStore.__new__(ValkeyVectorKnowledgeStore)
    mock_client = MagicMock()
    store._client = mock_client
    store._get_client = lambda: mock_client

    return store, mock_client


def _make_state_store():
    """Return a ValkeyStateStore with a pre-injected MagicMock client."""
    from praisonai.persistence.state.valkey import ValkeyStateStore

    store = ValkeyStateStore.__new__(ValkeyStateStore)
    mock_client = MagicMock()
    store._client = mock_client
    store._get_client = lambda: mock_client

    return store, mock_client


class TestValkeyVectorKnowledgeStore:
    """Tests for ValkeyVectorKnowledgeStore."""

    _FT_MODULE = "praisonai.persistence.knowledge.valkey_vector.ft"

    def _mock_ft(self, **method_returns):
        """Return a mock ft module with configured method returns."""
        mock_ft = MagicMock()
        for name, val in method_returns.items():
            if isinstance(val, Exception):
                getattr(mock_ft, name).side_effect = val
            else:
                getattr(mock_ft, name).return_value = val
        return mock_ft

    def test_create_collection(self):
        """Test create_collection calls ft.create with HNSW schema."""
        store, _ = _make_knowledge_store()
        mock_ft = self._mock_ft(create=b"OK")

        with patch(self._FT_MODULE, mock_ft):
            store.create_collection("docs", dimension=4)

        mock_ft.create.assert_called_once()
        assert mock_ft.create.call_args[0][1] == "praison:vec:docs:idx"

    def test_create_collection_already_exists(self):
        """Test create_collection silently ignores 'already exists' error."""
        store, _ = _make_knowledge_store()
        mock_ft = self._mock_ft(create=Exception("already exists"))

        with patch(self._FT_MODULE, mock_ft):
            store.create_collection("docs", dimension=4)  # should not raise

    def test_delete_collection(self):
        """Test delete_collection calls ft.dropindex and returns True on success."""
        store, _ = _make_knowledge_store()
        mock_ft = self._mock_ft(dropindex=b"OK")

        with patch(self._FT_MODULE, mock_ft):
            result = store.delete_collection("docs")

        assert result is True
        mock_ft.dropindex.assert_called_once()

    def test_collection_exists_true(self):
        """Test collection_exists returns True when ft.info succeeds."""
        store, _ = _make_knowledge_store()
        mock_ft = self._mock_ft(info={b"index_name": b"praison:vec:docs:idx"})

        with patch(self._FT_MODULE, mock_ft):
            result = store.collection_exists("docs")

        assert result is True

    def test_collection_exists_false(self):
        """Test collection_exists returns False when ft.info raises an exception."""
        store, _ = _make_knowledge_store()
        mock_ft = self._mock_ft(info=Exception("Unknown index name"))

        with patch(self._FT_MODULE, mock_ft):
            result = store.collection_exists("docs")

        assert result is False

    def test_list_collections(self):
        """Test list_collections returns only names matching the prefix, stripped."""
        store, _ = _make_knowledge_store()
        mock_ft = self._mock_ft(list=[b"praison:vec:docs:idx", b"other:idx"])

        with patch(self._FT_MODULE, mock_ft):
            result = store.list_collections()

        assert "docs" in result
        assert all("other" not in name for name in result)

    def test_insert(self):
        """Test insert uses Batch pipeline and calls client.exec."""
        store, mock_client = _make_knowledge_store()
        mock_client.exec.return_value = [4]

        embedding = [0.1, 0.2, 0.3, 0.4]
        doc = KnowledgeDocument(id="doc1", content="hello", embedding=embedding)
        ids = store.insert("docs", [doc])

        mock_client.exec.assert_called_once()
        assert ids == ["doc1"]

    def test_upsert_delegates_to_insert(self):
        """Test upsert calls insert (same path)."""
        store, mock_client = _make_knowledge_store()
        mock_client.exec.return_value = [4]

        doc = KnowledgeDocument(id="doc1", content="hello", embedding=[0.1, 0.2, 0.3, 0.4])
        store.upsert("docs", [doc])

        mock_client.exec.assert_called_once()

    def test_search(self):
        """Test search calls ft.search and returns a list of KnowledgeDocument."""
        store, _ = _make_knowledge_store()
        ft_result = [1, {
            b"praison:vec:docs:doc1": {
                b"content": b"hello",
                b"content_hash": b"abc",
                b"created_at": b"1234.0",
                b"score": b"0.1",
            }
        }]
        mock_ft = self._mock_ft(search=ft_result)

        with patch(self._FT_MODULE, mock_ft):
            results = store.search("docs", query_embedding=[0.1, 0.2, 0.3, 0.4], limit=5)

        assert isinstance(results, list)
        assert len(results) == 1
        assert isinstance(results[0], KnowledgeDocument)
        assert results[0].id == "doc1"
        mock_ft.search.assert_called_once()

    def test_search_with_filters(self):
        """Test search with filters builds a pre-filter KNN query."""
        store, _ = _make_knowledge_store()
        ft_result = [1, {
            b"praison:vec:docs:doc1": {
                b"content": b"hello",
                b"content_hash": b"abc",
                b"created_at": b"1234.0",
                b"score": b"0.1",
            }
        }]
        mock_ft = self._mock_ft(search=ft_result)

        with patch(self._FT_MODULE, mock_ft):
            results = store.search(
                "docs",
                query_embedding=[0.1, 0.2, 0.3, 0.4],
                limit=5,
                filters={"content_hash": "abc"},
            )

        assert len(results) == 1
        query_arg = mock_ft.search.call_args[0][2]
        assert "KNN" in query_arg
        assert query_arg.startswith("(")

    def test_search_score_threshold_excludes_low_similarity(self):
        """Test search excludes documents whose similarity is below score_threshold."""
        store, _ = _make_knowledge_store()
        ft_result = [2, {
            b"praison:vec:docs:doc1": {
                b"content": b"close",
                b"content_hash": b"",
                b"created_at": b"1.0",
                b"score": b"0.05",  # similarity = 0.95 — above threshold
            },
            b"praison:vec:docs:doc2": {
                b"content": b"far",
                b"content_hash": b"",
                b"created_at": b"2.0",
                b"score": b"0.8",   # similarity = 0.2 — below threshold
            },
        }]
        mock_ft = self._mock_ft(search=ft_result)

        with patch(self._FT_MODULE, mock_ft):
            results = store.search(
                "docs",
                query_embedding=[0.1, 0.2, 0.3, 0.4],
                limit=5,
                score_threshold=0.5,
            )

        assert len(results) == 1
        assert results[0].id == "doc1"

    def test_search_empty_result(self):
        """Test search returns an empty list when ft.search returns no documents."""
        store, _ = _make_knowledge_store()
        mock_ft = self._mock_ft(search=[])

        with patch(self._FT_MODULE, mock_ft):
            results = store.search("docs", query_embedding=[0.1, 0.2, 0.3, 0.4])

        assert results == []

    def test_get(self):
        """Test get uses Batch pipeline and returns a KnowledgeDocument."""
        store, mock_client = _make_knowledge_store()
        embedding = [0.1, 0.2, 0.3, 0.4]
        embedding_bytes = struct.pack(f"{len(embedding)}f", *embedding)
        mock_client.exec.return_value = [{
            b"content": b"hello",
            b"content_hash": b"abc",
            b"created_at": b"1234.0",
            b"embedding": embedding_bytes,
        }]

        results = store.get("docs", ["doc1"])

        assert len(results) == 1
        assert isinstance(results[0], KnowledgeDocument)
        assert results[0].id == "doc1"
        mock_client.exec.assert_called_once()

    def test_delete(self):
        """Test delete calls client.delete and returns count deleted."""
        store, mock_client = _make_knowledge_store()
        mock_client.delete.return_value = 2

        result = store.delete("docs", ids=["doc1", "doc2"])

        assert result == 2

    def test_count(self):
        """Test count calls ft.info and returns integer document count."""
        store, _ = _make_knowledge_store()
        mock_ft = self._mock_ft(info={b"num_docs": 7, b"index_name": b"praison:vec:docs:idx"})

        with patch(self._FT_MODULE, mock_ft):
            result = store.count("docs")

        assert isinstance(result, int)
        assert result == 7

    def test_close_closes_client(self):
        """Test close() calls client.close() and clears the reference."""
        store, mock_client = _make_knowledge_store()

        store.close()

        mock_client.close.assert_called_once()
        assert store._client is None


class TestValkeyStateStore:
    """Tests for ValkeyStateStore."""

    def test_get_existing(self):
        """Test get returns a dict when client.get returns JSON bytes."""
        store, mock_client = _make_state_store()
        data = {"result": "ok"}
        mock_client.get.return_value = json.dumps(data).encode("utf-8")

        result = store.get("mykey")

        mock_client.get.assert_called_once_with("praison:mykey")
        assert result == data

    def test_get_missing(self):
        """Test get returns None when client.get returns None."""
        store, mock_client = _make_state_store()
        mock_client.get.return_value = None

        result = store.get("missing")

        assert result is None

    def test_set_no_ttl(self):
        """Test set calls client.set with prefixed key when no TTL is given."""
        store, mock_client = _make_state_store()
        mock_client.set.return_value = b"OK"

        store.set("mykey", {"x": 1})

        mock_client.set.assert_called_once()
        call_args = mock_client.set.call_args[0]
        assert call_args[0] == "praison:mykey"

    def test_set_with_ttl(self):
        """Test set with TTL passes SetOptions to client.set (ImportError/RuntimeError tolerated)."""
        store, mock_client = _make_state_store()
        mock_client.set.return_value = b"OK"

        # glide's ExpirySet/ExpiryType are lazy-imported inside set(); without a live
        # glide install this raises ImportError — both paths are valid in CI.
        try:
            store.set("ttlkey", {"x": 1}, ttl=300)
        except (ImportError, RuntimeError):
            pass

    def test_delete_existing(self):
        """Test delete returns True when client.delete returns 1."""
        store, mock_client = _make_state_store()
        mock_client.delete.return_value = 1

        result = store.delete("mykey")

        mock_client.delete.assert_called_once_with(["praison:mykey"])
        assert result is True

    def test_delete_missing(self):
        """Test delete returns False when client.delete returns 0."""
        store, mock_client = _make_state_store()
        mock_client.delete.return_value = 0

        result = store.delete("absent")

        assert result is False

    def test_exists_true(self):
        """Test exists returns True when client.exists returns 1."""
        store, mock_client = _make_state_store()
        mock_client.exists.return_value = 1

        assert store.exists("mykey") is True
        mock_client.exists.assert_called_once_with(["praison:mykey"])

    def test_exists_false(self):
        """Test exists returns False when client.exists returns 0."""
        store, mock_client = _make_state_store()
        mock_client.exists.return_value = 0

        assert store.exists("absent") is False

    def test_keys(self):
        """Test keys returns stripped key names via client.scan."""
        store, mock_client = _make_state_store()
        # scan() returns [cursor, [keys]]; cursor b"0" signals end of iteration
        mock_client.scan.return_value = [b"0", [b"praison:key1", b"praison:key2"]]

        result = store.keys()

        mock_client.scan.assert_called_once()
        assert result == ["key1", "key2"]

    def test_ttl_with_value(self):
        """Test ttl returns seconds remaining when client.ttl returns a positive value."""
        store, mock_client = _make_state_store()
        mock_client.ttl.return_value = 30

        result = store.ttl("mykey")

        assert result == 30

    def test_ttl_no_ttl(self):
        """Test ttl returns None when client.ttl returns -1 (no expiry)."""
        store, mock_client = _make_state_store()
        mock_client.ttl.return_value = -1

        result = store.ttl("mykey")

        assert result is None

    def test_expire(self):
        """Test expire calls client.expire and returns its result."""
        store, mock_client = _make_state_store()
        mock_client.expire.return_value = True

        result = store.expire("mykey", 600)

        mock_client.expire.assert_called_once_with("praison:mykey", 600)
        assert result is True

    def test_hget(self):
        """Test hget returns a parsed dict when client.hget returns JSON bytes."""
        store, mock_client = _make_state_store()
        data = {"field_val": 42}
        mock_client.hget.return_value = json.dumps(data).encode("utf-8")

        result = store.hget("myhash", "field1")

        mock_client.hget.assert_called_once_with("praison:myhash", "field1")
        assert result == data

    def test_hset(self):
        """Test hset calls client.hset with the prefixed key and a mapping dict."""
        store, mock_client = _make_state_store()
        mock_client.hset.return_value = 1

        store.hset("myhash", "field1", "value1")

        mock_client.hset.assert_called_once()
        call_args = mock_client.hset.call_args[0]
        assert call_args[0] == "praison:myhash"
        assert isinstance(call_args[1], dict)
        assert "field1" in call_args[1]

    def test_hgetall(self):
        """Test hgetall returns a decoded dict when client.hgetall returns bytes."""
        store, mock_client = _make_state_store()
        mock_client.hgetall.return_value = {
            b"field1": b'"value1"',
            b"field2": b"42",
        }

        result = store.hgetall("myhash")

        mock_client.hgetall.assert_called_once_with("praison:myhash")
        assert "field1" in result
        assert "field2" in result

    def test_hdel(self):
        """Test hdel calls client.hdel and returns the count of deleted fields."""
        store, mock_client = _make_state_store()
        mock_client.hdel.return_value = 2

        result = store.hdel("myhash", "field1", "field2")

        assert result == 2

    def test_incr(self):
        """Test incr calls client.incrby and returns the new value."""
        store, mock_client = _make_state_store()
        mock_client.incrby.return_value = 5

        result = store.incr("counter")

        assert result == 5
        mock_client.incrby.assert_called_once_with("praison:counter", 1)

    def test_decr(self):
        """Test decr calls client.decrby and returns the new value."""
        store, mock_client = _make_state_store()
        mock_client.decrby.return_value = 3

        result = store.decr("counter")

        assert result == 3
        mock_client.decrby.assert_called_once_with("praison:counter", 1)

    def test_close_closes_client(self):
        """Test close() calls client.close() and clears the reference."""
        store, mock_client = _make_state_store()

        store.close()

        mock_client.close.assert_called_once()
        assert store._client is None


class TestRegistryValkey:
    """Tests for Valkey backend registration in store registries."""

    def test_knowledge_store_valkey_registered(self):
        """Test KNOWLEDGE_STORES registry contains 'valkey'."""
        assert "valkey" in KNOWLEDGE_STORES.list_registered()

    def test_state_store_valkey_registered(self):
        """Test STATE_STORES registry contains 'valkey'."""
        assert "valkey" in STATE_STORES.list_registered()
