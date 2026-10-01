"""Enumerating SQLite memories must include rows beyond search-sized caps."""

import pytest

from praisonaiagents.memory.adapters.sqlite_adapter import SqliteMemoryAdapter
from praisonaiagents.memory.memory import Memory


@pytest.mark.parametrize('facade', [False, True])
@pytest.mark.parametrize('short_count,long_count', [(0, 0), (1000, 1), (1, 1000), (1001, 1001)])
def test_get_all_memories_includes_every_stored_row(tmp_path, monkeypatch, facade, short_count, long_count):
    monkeypatch.setenv('PRAISONAI_HOME', str(tmp_path / 'home'))
    monkeypatch.chdir(tmp_path)
    store = Memory(config={'provider': 'sqlite'}) if facade else SqliteMemoryAdapter(
        short_db=str(tmp_path / 'short.db'), long_db=str(tmp_path / 'long.db'),
    )
    adapter = store.memory_adapter if facade else store
    expected = set()
    try:
        for tier, count in [('short', short_count), ('long', long_count)]:
            write = getattr(store, f'store_{tier}_term')
            for index in range(count):
                text = f'{tier} entry {index}'
                memory_id = write(text, metadata={'index': index})
                expected.add((f'{tier}_term', memory_id, text, index))
        records = store.get_all_memories()
        assert len(records) == short_count + long_count
        assert {
            (record['memory_type'], record['id'], record['text'], record['metadata']['index'])
            for record in records
        } == expected
        if facade:
            assert all(record['type'] == record['memory_type'] for record in records)
        # Enumeration must not widen the public search defaults or explicit limit.
        for tier, count in [('short', short_count), ('long', long_count)]:
            search = getattr(adapter, f'search_{tier}_term')
            assert len(search('')) == min(5, count)
            assert len(search('', limit=2)) == min(2, count)
    finally:
        adapter.close_connections()
        if facade:
            store.close_connections()
