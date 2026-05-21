"""
Unit tests for Valkey persistence stores.

These tests do NOT require a live Valkey server.  They use ``unittest.mock``
to stub out ``glide_sync`` so that all logic in the Valkey modules is
exercised without any network I/O.
"""

from __future__ import annotations

import json
import sys
import types
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Minimal glide_sync stub
# ---------------------------------------------------------------------------

def _make_glide_stub() -> types.ModuleType:
    """Return a minimal stub for glide_sync so no real install is needed."""
    glide_sync = types.ModuleType("glide_sync")

    # --- Fake classes -------------------------------------------------------

    class NodeAddress:
        def __init__(self, host, port):
            self.host = host
            self.port = port

    class ServerCredentials:
        def __init__(self, password=None, username=None, iam_config=None):
            self.password = password

    class GlideClientConfiguration:
        def __init__(self, addresses, credentials=None, **kwargs):
            self.addresses = addresses
            self.credentials = credentials

    class ExpiryType:
        SEC = "SEC"

    class ExpirySet:
        def __init__(self, expiry_type, value):
            self.expiry_type = expiry_type
            self.value = value

    class GlideClient(MagicMock):
        pass

    # Expose everything on the module
    for obj in [
        NodeAddress, ServerCredentials, GlideClientConfiguration,
        ExpiryType, ExpirySet, GlideClient,
    ]:
        setattr(glide_sync, obj.__name__, obj)

    return glide_sync


# Inject the stub before any praisonai import
_glide_stub = _make_glide_stub()
sys.modules["glide_sync"] = _glide_stub


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_client() -> MagicMock:
    """Return a MagicMock that behaves like a synchronous GlideClient."""
    client = MagicMock()
    client.ping.return_value = b"PONG"
    # scan returns [cursor, [keys]] — cursor b"0" signals end of iteration
    client.scan.return_value = [b"0", []]
    return client


# ---------------------------------------------------------------------------
# _valkey_client module
# ---------------------------------------------------------------------------

class TestCreateValkeyClient:
    def test_uses_defaults(self):
        from praisonai.persistence._valkey_client import create_valkey_client

        with patch("glide_sync.GlideClient") as mock_cls, \
             patch("glide_sync.GlideClientConfiguration") as mock_cfg, \
             patch("glide_sync.NodeAddress") as mock_addr:
            create_valkey_client()
            mock_addr.assert_called_once_with("localhost", 6379)
            # No credentials when no password supplied
            cfg_call_kwargs = mock_cfg.call_args.kwargs
            assert cfg_call_kwargs.get("credentials") is None

    def test_uses_env_vars(self, monkeypatch):
        from praisonai.persistence._valkey_client import create_valkey_client

        monkeypatch.setenv("VALKEY_HOST", "myhost")
        monkeypatch.setenv("VALKEY_PORT", "6380")
        monkeypatch.setenv("VALKEY_PASSWORD", "test_password")

        with patch("glide_sync.GlideClient"), \
             patch("glide_sync.GlideClientConfiguration") as mock_cfg, \
             patch("glide_sync.NodeAddress") as mock_addr, \
             patch("glide_sync.ServerCredentials") as mock_creds:
            create_valkey_client()
            mock_addr.assert_called_once_with("myhost", 6380)
            mock_creds.assert_called_once_with(password="test_password")
            assert mock_cfg.call_args.kwargs["credentials"] is mock_creds.return_value

    def test_explicit_args_take_precedence_over_env(self, monkeypatch):
        from praisonai.persistence._valkey_client import create_valkey_client

        monkeypatch.setenv("VALKEY_HOST", "envhost")
        monkeypatch.setenv("VALKEY_PORT", "9999")

        with patch("glide_sync.GlideClient"), \
             patch("glide_sync.GlideClientConfiguration"), \
             patch("glide_sync.NodeAddress") as mock_addr:
            create_valkey_client(host="explicit", port=1234)
            mock_addr.assert_called_once_with("explicit", 1234)


class TestScanKeys:
    def test_single_page(self):
        from praisonai.persistence._valkey_client import scan_keys

        client = MagicMock()
        # scan returns one batch of two keys, then signals done with cursor "0"
        client.scan.return_value = [b"0", [b"praison:a", b"praison:b"]]

        result = scan_keys(client, "praison:*")
        assert sorted(result) == ["praison:a", "praison:b"]
        client.scan.assert_called_once_with(b"0", match="praison:*", count=100)

    def test_multi_page(self):
        from praisonai.persistence._valkey_client import scan_keys

        client = MagicMock()
        client.scan.side_effect = [
            [b"42", [b"k1", b"k2"]],   # first page — cursor != 0
            [b"0",  [b"k3"]],           # second page — done
        ]
        result = scan_keys(client, "*")
        assert sorted(result) == ["k1", "k2", "k3"]
        assert client.scan.call_count == 2


# ---------------------------------------------------------------------------
# ValkeyStateStore
# ---------------------------------------------------------------------------

class TestValkeyStateStore:
    @pytest.fixture()
    def store(self):
        mock_client = _make_mock_client()
        with patch(
            "praisonai.persistence._valkey_client.create_valkey_client",
            return_value=mock_client,
        ):
            from praisonai.persistence.state.valkey import ValkeyStateStore
            store = ValkeyStateStore(host="localhost", port=6379)
            store._client = mock_client
            yield store, mock_client

    def test_get_returns_none_for_missing_key(self, store):
        s, client = store
        client.get.return_value = None
        assert s.get("missing") is None

    def test_get_decodes_json(self, store):
        s, client = store
        client.get.return_value = b'{"x": 1}'
        assert s.get("k") == {"x": 1}

    def test_get_returns_string_for_non_json(self, store):
        s, client = store
        client.get.return_value = b"hello"
        assert s.get("k") == "hello"

    def test_set_no_ttl(self, store):
        s, client = store
        s.set("mykey", {"a": 1})
        client.set.assert_called_once_with("praison:mykey", '{"a": 1}')

    def test_set_with_ttl(self, store):
        s, client = store
        from glide_sync import ExpirySet, ExpiryType  # type: ignore[import]
        s.set("mykey", "value", ttl=60)
        call_kwargs = client.set.call_args.kwargs
        expiry = call_kwargs.get("expiry")
        assert expiry is not None
        assert expiry.expiry_type == ExpiryType.SEC
        assert expiry.value == 60

    def test_delete_returns_true_on_success(self, store):
        s, client = store
        client.delete.return_value = 1
        assert s.delete("k") is True
        client.delete.assert_called_once_with(["praison:k"])

    def test_delete_returns_false_when_not_found(self, store):
        s, client = store
        client.delete.return_value = 0
        assert s.delete("k") is False

    def test_exists_true(self, store):
        s, client = store
        client.exists.return_value = 1
        assert s.exists("k") is True

    def test_exists_false(self, store):
        s, client = store
        client.exists.return_value = 0
        assert s.exists("k") is False

    def test_keys_strips_prefix(self, store):
        s, client = store
        client.scan.return_value = [b"0", [b"praison:foo", b"praison:bar"]]
        result = s.keys("*")
        assert sorted(result) == ["bar", "foo"]

    def test_ttl_returns_none_for_missing(self, store):
        s, client = store
        client.ttl.return_value = -2
        assert s.ttl("k") is None

    def test_ttl_returns_none_for_no_expiry(self, store):
        s, client = store
        client.ttl.return_value = -1
        assert s.ttl("k") is None

    def test_ttl_returns_value(self, store):
        s, client = store
        client.ttl.return_value = 120
        assert s.ttl("k") == 120

    def test_hget_decodes_json(self, store):
        s, client = store
        client.hget.return_value = b'[1, 2, 3]'
        assert s.hget("h", "field") == [1, 2, 3]

    def test_hset_serialises_value(self, store):
        s, client = store
        s.hset("h", "f", {"data": True})
        client.hset.assert_called_once_with("praison:h", {"f": '{"data": true}'})

    def test_hgetall_decodes_bytes_keys(self, store):
        s, client = store
        client.hgetall.return_value = {b"field": b'"value"'}
        result = s.hgetall("h")
        assert result == {"field": "value"}

    def test_hdel_converts_tuple_to_list(self, store):
        s, client = store
        client.hdel.return_value = 2
        s.hdel("h", "f1", "f2")
        client.hdel.assert_called_once_with("praison:h", ["f1", "f2"])

    def test_hdel_empty_returns_zero(self, store):
        s, client = store
        assert s.hdel("h") == 0
        client.hdel.assert_not_called()

    def test_incr(self, store):
        s, client = store
        client.incrby.return_value = 5
        assert s.incr("counter", 2) == 5
        client.incrby.assert_called_once_with("praison:counter", 2)

    def test_decr(self, store):
        s, client = store
        client.decrby.return_value = 3
        assert s.decr("counter", 1) == 3
        client.decrby.assert_called_once_with("praison:counter", 1)

    def test_close_sets_client_none(self, store):
        s, client = store
        s.close()
        assert s._client is None
        client.close.assert_called_once()


# ---------------------------------------------------------------------------
# ValkeyStorageAdapter
# ---------------------------------------------------------------------------

class TestValkeyStorageAdapter:
    @pytest.fixture()
    def adapter(self):
        mock_client = _make_mock_client()
        with patch(
            "praisonai.persistence._valkey_client.create_valkey_client",
            return_value=mock_client,
        ):
            from praisonai.storage.valkey_adapter import ValkeyStorageAdapter
            a = ValkeyStorageAdapter(host="localhost", port=6379)
            a._client = mock_client
            yield a, mock_client

    def test_save_no_ttl(self, adapter):
        a, client = adapter
        a.save("sess", {"msg": "hi"})
        client.set.assert_called_once_with("praisonai:sess", '{"msg": "hi"}')

    def test_save_with_ttl(self, adapter):
        a, client = adapter
        a.ttl = 30
        from glide_sync import ExpirySet, ExpiryType  # type: ignore[import]
        a.save("sess", {})
        call_kwargs = client.set.call_args.kwargs
        expiry = call_kwargs.get("expiry")
        assert expiry is not None
        assert expiry.value == 30

    def test_load_decodes_json(self, adapter):
        a, client = adapter
        client.get.return_value = b'{"x": 42}'
        assert a.load("k") == {"x": 42}

    def test_load_returns_none_for_missing(self, adapter):
        a, client = adapter
        client.get.return_value = None
        assert a.load("k") is None

    def test_load_returns_none_for_invalid_json(self, adapter):
        a, client = adapter
        client.get.return_value = b"not-json"
        assert a.load("k") is None

    def test_delete_delegated(self, adapter):
        a, client = adapter
        client.delete.return_value = 1
        assert a.delete("k") is True
        client.delete.assert_called_once_with(["praisonai:k"])

    def test_list_keys_uses_scan(self, adapter):
        a, client = adapter
        client.scan.return_value = [b"0", [b"praisonai:foo"]]
        keys = a.list_keys()
        assert keys == ["foo"]

    def test_exists(self, adapter):
        a, client = adapter
        client.exists.return_value = 1
        assert a.exists("k") is True

    def test_clear_uses_scan_then_delete(self, adapter):
        a, client = adapter
        client.scan.return_value = [b"0", [b"praisonai:a", b"praisonai:b"]]
        client.delete.return_value = 2
        count = a.clear()
        assert count == 2
        client.delete.assert_called_once()

    def test_clear_returns_zero_when_empty(self, adapter):
        a, client = adapter
        client.scan.return_value = [b"0", []]
        assert a.clear() == 0


# ---------------------------------------------------------------------------
# ValkeyVectorKnowledgeStore – registry and lazy import
# ---------------------------------------------------------------------------

class TestValkeyRegistryIntegration:
    def test_valkey_registered_in_state_stores(self):
        from praisonai.persistence.registry import STATE_STORES
        assert "valkey" in STATE_STORES.list_names()

    def test_valkey_registered_in_knowledge_stores(self):
        from praisonai.persistence.registry import KNOWLEDGE_STORES
        assert "valkey" in KNOWLEDGE_STORES.list_names()

    def test_state_store_factory_raises_without_dependency(self):
        """Creating the store must raise ImportError when glide_sync is absent."""
        import importlib
        original = sys.modules.pop("glide_sync", None)
        try:
            # Remove cached modules that depend on glide_sync
            for mod in list(sys.modules.keys()):
                if "valkey" in mod:
                    sys.modules.pop(mod, None)

            sys.modules["glide_sync"] = None  # type: ignore[assignment]

            from praisonai.persistence.registry import STATE_STORES
            with pytest.raises((ImportError, TypeError)):
                STATE_STORES.create("valkey", host="localhost", port=6379)
        finally:
            if original is not None:
                sys.modules["glide_sync"] = original
            else:
                sys.modules.pop("glide_sync", None)
            # Reload the stub for subsequent tests
            sys.modules["glide_sync"] = _glide_stub
