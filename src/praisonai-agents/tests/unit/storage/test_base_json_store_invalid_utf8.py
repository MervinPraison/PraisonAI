"""Base stores keep malformed-input fallback consistent for undecodable bytes."""

import asyncio

import pytest

from praisonaiagents.storage.base import AsyncBaseJSONStore, BaseJSONStore


class DefaultStore(BaseJSONStore):
    def _default_data(self):
        return {"items": []}


class AsyncDefaultStore(AsyncBaseJSONStore):
    def _default_data(self):
        return {"items": []}


@pytest.mark.parametrize("flavor", ["locked", "unlocked", "async"])
@pytest.mark.parametrize("payload", [b"\xff", b'{"items":["\xe2\x82', b'{"items":["\xed\xa0\x80"]}', b"{invalid"])
def test_unreadable_bytes_use_defaults_without_rewriting_file(tmp_path, payload, flavor):
    path = tmp_path / "store.json"
    path.write_bytes(payload)
    if flavor == "async":
        pytest.importorskip("aiofiles")
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
def test_valid_unicode_and_missing_file_keep_existing_behavior(tmp_path, flavor):
    path = tmp_path / "store.json"
    expected = {"items": ["你好 café 😀"]}
    if flavor == "async":
        pytest.importorskip("aiofiles")
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
