"""MongoDBStateStore: shared driver init via MongoDBStorageAdapter + TTL handling."""

import sys
import types
from datetime import timedelta
from unittest.mock import MagicMock

import pytest


class _FakeCollection:
    """Minimal in-memory stand-in for a pymongo collection."""

    def __init__(self):
        self.docs = {}

    def create_index(self, *args, **kwargs):
        return None

    def find_one(self, query, projection=None):
        doc = self.docs.get(query["_id"])
        return dict(doc) if doc else None

    def replace_one(self, query, doc, upsert=False):
        self.docs[query["_id"]] = dict(doc)

    def update_one(self, query, update, upsert=False):
        doc = self.docs.get(query["_id"])
        if doc is None:
            return MagicMock(modified_count=0)
        doc.update(update.get("$set", {}))
        return MagicMock(modified_count=1)

    def delete_one(self, query):
        return MagicMock(deleted_count=1 if self.docs.pop(query["_id"], None) else 0)


@pytest.fixture
def store(monkeypatch):
    collection = _FakeCollection()
    client = MagicMock()
    client.__getitem__.return_value.__getitem__.return_value = collection
    mongo_client_cls = MagicMock(return_value=client)
    fake_pymongo = types.ModuleType("pymongo")
    fake_pymongo.MongoClient = mongo_client_cls
    monkeypatch.setitem(sys.modules, "pymongo", fake_pymongo)

    from praisonai.persistence.state.mongodb import MongoDBStateStore

    s = MongoDBStateStore(url="mongodb://example:27017", database="db", collection="state")
    s._mongo_client_cls = mongo_client_cls
    return s


def test_uses_storage_adapter_for_driver(store):
    from praisonai.storage import MongoDBStorageAdapter

    assert isinstance(store._adapter, MongoDBStorageAdapter)
    store._mongo_client_cls.assert_called_once()
    assert store._mongo_client_cls.call_args.args[0] == "mongodb://example:27017"


def test_ttl_roundtrip_does_not_raise(store):
    store.set("k", {"a": 1}, ttl=60)
    assert store.get("k") == {"a": 1}
    assert store.exists("k") is True
    assert 0 < store.ttl("k") <= 60


def test_expired_key_is_hidden(store):
    store.set("k", "v", ttl=60)
    store._collection.docs["k"]["expires_at"] -= timedelta(seconds=120)
    assert store.exists("k") is False
    assert store.ttl("k") is None
    assert store.get("k") is None


def test_uri_options_override_adapter_defaults(store):
    from praisonai.persistence.state.mongodb import MongoDBStateStore

    MongoDBStateStore(url="mongodb://example:27017/?RetryWrites=false&maxPoolSize=7")
    kwargs = store._mongo_client_cls.call_args.kwargs
    assert "retryWrites" not in kwargs
    assert "maxPoolSize" not in kwargs
    assert kwargs["retryReads"] is True
