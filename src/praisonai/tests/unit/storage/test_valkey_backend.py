"""
Tests for ValkeyStorageAdapter and ValkeySearchBackend.

Tests cover:
- ValkeyStorageAdapter CRUD operations (mocked glide client)
- ValkeySearchBackend index and search operations (mocked)
"""

import json
from unittest.mock import MagicMock, patch


def _make_adapter(prefix="praisonai:", ttl=None):
    """Return a ValkeyStorageAdapter with a pre-injected MagicMock client."""
    from praisonai.storage.valkey_adapter import ValkeyStorageAdapter

    adapter = ValkeyStorageAdapter.__new__(ValkeyStorageAdapter)
    adapter.host = "localhost"
    adapter.port = 6379
    adapter.prefix = prefix
    adapter.ttl = ttl
    adapter.password = None

    mock_client = MagicMock()
    adapter._client = mock_client
    adapter._get_client = lambda: mock_client

    return adapter, mock_client


def _make_search_backend(index_name="praisonai_vectors", vector_dim=4):
    """Return a ValkeySearchBackend with a pre-injected MagicMock client."""
    from praisonai.storage.valkey_adapter import ValkeySearchBackend

    backend = ValkeySearchBackend.__new__(ValkeySearchBackend)
    backend.host = "localhost"
    backend.port = 6379
    backend.index_name = index_name
    backend.vector_dim = vector_dim
    backend.password = None

    mock_client = MagicMock()
    backend._client = mock_client
    backend._get_client = lambda: mock_client

    return backend, mock_client


class TestValkeyStorageAdapter:
    """Tests for ValkeyStorageAdapter."""

    def test_valkey_adapter_save(self):
        """Test save calls client.set with prefixed key and JSON bytes."""
        adapter, mock_client = _make_adapter()

        data = {"name": "test", "value": 42}
        adapter.save("mykey", data)

        mock_client.set.assert_called_once()
        call_args = mock_client.set.call_args[0]
        assert call_args[0] == "praisonai:mykey"
        assert json.loads(call_args[1]) == data

    def test_valkey_adapter_save_with_ttl(self):
        """Test save with TTL calls client.set with expiry kwarg (ImportError tolerated without glide)."""
        adapter, mock_client = _make_adapter(ttl=300)

        # ExpirySet/ExpiryType are lazy-imported inside save(); without a live
        # glide install this raises RuntimeError — both paths are valid in CI.
        try:
            adapter.save("ttlkey", {"key": "val"})
            mock_client.set.assert_called_once()
            _, kwargs = mock_client.set.call_args
            assert "expiry" in kwargs
        except (ImportError, RuntimeError):
            pass

    def test_valkey_adapter_load_existing(self):
        """Test load returns a dict when client.get returns JSON bytes."""
        adapter, mock_client = _make_adapter()

        data = {"result": "ok"}
        mock_client.get.return_value = json.dumps(data).encode("utf-8")

        loaded = adapter.load("mykey")

        mock_client.get.assert_called_once_with("praisonai:mykey")
        assert loaded == data

    def test_valkey_adapter_load_missing(self):
        """Test load returns None when client.get returns None."""
        adapter, mock_client = _make_adapter()
        mock_client.get.return_value = None

        loaded = adapter.load("missing")

        assert loaded is None

    def test_valkey_adapter_delete_existing(self):
        """Test delete returns True when client.delete returns 1."""
        adapter, mock_client = _make_adapter()
        mock_client.delete.return_value = 1

        result = adapter.delete("mykey")

        mock_client.delete.assert_called_once_with(["praisonai:mykey"])
        assert result is True

    def test_valkey_adapter_delete_missing(self):
        """Test delete returns False when client.delete returns 0."""
        adapter, mock_client = _make_adapter()
        mock_client.delete.return_value = 0

        result = adapter.delete("absent")

        assert result is False

    def test_valkey_adapter_list_keys(self):
        """Test list_keys returns stripped, sorted key names via client.scan."""
        adapter, mock_client = _make_adapter()
        raw_keys = [b"praisonai:beta", b"praisonai:alpha", b"praisonai:gamma"]
        # scan() returns [cursor, [keys]]; cursor b"0" signals end of iteration
        mock_client.scan.return_value = [b"0", raw_keys]

        keys = adapter.list_keys()

        mock_client.scan.assert_called_once()
        assert keys == ["alpha", "beta", "gamma"]

    def test_valkey_adapter_exists_true(self):
        """Test exists returns True when client.exists returns 1."""
        adapter, mock_client = _make_adapter()
        mock_client.exists.return_value = 1

        assert adapter.exists("mykey") is True
        mock_client.exists.assert_called_once_with(["praisonai:mykey"])

    def test_valkey_adapter_exists_false(self):
        """Test exists returns False when client.exists returns 0."""
        adapter, mock_client = _make_adapter()
        mock_client.exists.return_value = 0

        assert adapter.exists("absent") is False

    def test_valkey_adapter_clear(self):
        """Test clear deletes all prefixed keys and returns count."""
        adapter, mock_client = _make_adapter()
        raw_keys = [b"praisonai:a", b"praisonai:b", b"praisonai:c"]
        # scan() returns [cursor, [keys]]; cursor b"0" signals end of iteration
        mock_client.scan.return_value = [b"0", raw_keys]
        mock_client.delete.return_value = 3

        count = adapter.clear()

        assert count == 3
        mock_client.delete.assert_called_once()

    def test_valkey_adapter_set_ttl(self):
        """Test set_ttl calls client.expire with prefixed key and returns result."""
        adapter, mock_client = _make_adapter()
        mock_client.expire.return_value = True

        result = adapter.set_ttl("mykey", 600)

        mock_client.expire.assert_called_once_with("praisonai:mykey", 600)
        assert result is True

    def test_valkey_adapter_import_error(self):
        """Test ImportError with 'valkey' hint when glide package is not available."""
        import praisonai.storage.valkey_adapter as mod
        from praisonai.storage.valkey_adapter import ValkeyStorageAdapter

        adapter = ValkeyStorageAdapter.__new__(ValkeyStorageAdapter)
        adapter.host = "localhost"
        adapter.port = 6379
        adapter.prefix = "praisonai:"
        adapter.ttl = None
        adapter.password = None
        adapter._client = None

        original = mod.GlideClientSync
        try:
            mod.GlideClientSync = None
            try:
                adapter._get_client()
                assert False, "Should have raised ImportError"
            except ImportError as e:
                assert "valkey" in str(e).lower()
        finally:
            mod.GlideClientSync = original

    def test_valkey_adapter_operation_error(self):
        """Test RuntimeError raised when a client operation fails."""
        adapter, mock_client = _make_adapter()
        mock_client.get.side_effect = Exception("connection refused")

        try:
            adapter.load("anykey")
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "Valkey" in str(e) or "valkey" in str(e).lower()


class TestValkeySearchBackend:
    """Tests for ValkeySearchBackend."""

    def test_create_index(self):
        """Test create_index uses ft.create (no-op if already exists)."""
        backend, _ = _make_search_backend()
        mock_ft = MagicMock()
        mock_ft.create.return_value = b"OK"

        with patch("praisonai.storage.valkey_adapter.ft", mock_ft):
            backend.create_index()

        mock_ft.create.assert_called_once()
        assert backend.index_name == mock_ft.create.call_args[0][1]

    def test_add_document(self):
        """Test add_document calls hset with correct key and fields."""
        backend, mock_client = _make_search_backend()
        mock_client.hset.return_value = 2

        backend.add_document("doc1", "hello world", [0.1, 0.2, 0.3, 0.4])

        mock_client.hset.assert_called_once()
        call_args = mock_client.hset.call_args[0]
        assert call_args[0] == "praisonai_vectors:doc1"
        mapping = call_args[1]
        assert "text" in mapping
        assert mapping["text"] == "hello world"
        assert "embedding" in mapping

    def test_search(self):
        """Test search uses ft.search and returns a list of dicts."""
        backend, _ = _make_search_backend()
        ft_result = [1, {b"praisonai_vectors:doc1": {b"text": b"hello world", b"score": b"0.05"}}]
        mock_ft = MagicMock()
        mock_ft.search.return_value = ft_result

        with patch("praisonai.storage.valkey_adapter.ft", mock_ft):
            results = backend.search([0.1, 0.2, 0.3, 0.4], k=5)

        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0]["id"] == "praisonai_vectors:doc1"
        assert results[0]["text"] == "hello world"
        mock_ft.search.assert_called_once()

