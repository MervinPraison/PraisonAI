"""Base stores keep malformed-input fallback consistent for undecodable bytes."""

import asyncio
import importlib
import sys
import types

import pytest

from praisonaiagents.storage.base import AsyncBaseJSONStore, BaseJSONStore


class DefaultStore(BaseJSONStore):
    def _default_data(self):
        return {"items": []}


class AsyncDefaultStore(AsyncBaseJSONStore):
    def _default_data(self):
        return {"items": []}


@pytest.fixture
def ensure_aiofiles(monkeypatch):
    """Guarantee the async recovery branch runs even when aiofiles is absent.

    aiofiles is not a declared dependency, so CI may lack it and silently skip
    every async case. Rather than skip (hiding the regression), inject a minimal
    real-decode stub that mirrors aiofiles.open's text-read behaviour so the
    UnicodeDecodeError/JSONDecodeError recovery is always exercised.
    """
    try:
        importlib.import_module("aiofiles")
        return
    except ImportError:
        pass

    fake = types.ModuleType("aiofiles")

    class _AsyncFile:
        def __init__(self, path, mode, encoding):
            self._path = path
            self._mode = mode
            self._encoding = encoding
            self._fh = None

        async def __aenter__(self):
            self._fh = open(self._path, self._mode, encoding=self._encoding)
            return self

        async def __aexit__(self, exc_type, exc, tb):
            if self._fh is not None:
                self._fh.close()
            return False

        async def read(self):
            return self._fh.read()

        async def write(self, data):
            return self._fh.write(data)

    def _open(path, mode="r", encoding=None):
        return _AsyncFile(path, mode, encoding)

    fake.open = _open
    monkeypatch.setitem(sys.modules, "aiofiles", fake)


@pytest.mark.parametrize("flavor", ["locked", "unlocked", "async"])
@pytest.mark.parametrize("payload", [b"\xff", b'{"items":["\xe2\x82', b'{"items":["\xed\xa0\x80"]}', b"{invalid"])
def test_unreadable_bytes_use_defaults_without_rewriting_file(tmp_path, payload, flavor, ensure_aiofiles):
    path = tmp_path / "store.json"
    path.write_bytes(payload)
    if flavor == "async":
        store = AsyncDefaultStore(path)

        async def read_twice():
            assert await store.load_async() == {"items": []}
            assert await store.load_async() == {"items": []}

        asyncio.run(read_twice())
    else:
        store = DefaultStore(path, use_file_lock=flavor == "locked")
        assert store.load() == {"items": []}
    assert path.read_bytes() == payload


@pytest.mark.parametrize("flavor", ["locked", "unlocked", "async"])
def test_valid_unicode_and_missing_file_keep_existing_behavior(tmp_path, flavor, ensure_aiofiles):
    path = tmp_path / "store.json"
    expected = {"items": ["你好 café 😀"]}
    if flavor == "async":
        store = AsyncDefaultStore(path)

        async def round_trip():
            assert await store.load_async() == {"items": []}
            await store.save_async(expected)
            assert await store.load_async() == expected

        asyncio.run(round_trip())
    else:
        store = DefaultStore(path, use_file_lock=flavor == "locked")
        assert store.load() == {"items": []}
        store.save(expected)
        assert store.load() == expected
