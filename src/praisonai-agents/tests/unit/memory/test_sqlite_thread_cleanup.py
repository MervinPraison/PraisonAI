"""Closing one Memory user's connections must leave shared SQLite usable."""

from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from praisonaiagents.memory.memory import Memory


@pytest.fixture
def memory(tmp_path):
    instance = Memory(config={
        'provider': 'sqlite',
        'short_db': str(tmp_path / 'short.db'),
        'long_db': str(tmp_path / 'long.db'),
    })
    adapter = instance.memory_adapter
    try:
        yield instance
    finally:
        instance.close_connections()
        adapter.close_connections()


@pytest.mark.parametrize('tier', ['short', 'long'])
@pytest.mark.parametrize('worker_has_connection', [False, True])
def test_worker_cleanup_preserves_other_thread_search(memory, tier, worker_has_connection):
    store = getattr(memory, f'store_{tier}_term')
    search = getattr(memory, f'search_{tier}_term')
    record_id = store('shared record')
    assert [record['id'] for record in search('shared record')] == [record_id]

    with ThreadPoolExecutor(max_workers=1) as pool:
        if worker_has_connection:
            assert [record['id'] for record in pool.submit(search, 'shared record').result()] == [record_id]
        pool.submit(memory.close_connections).result()
        assert [record['id'] for record in search('shared record')] == [record_id]


@pytest.mark.parametrize('tier', ['short', 'long'])
def test_calling_thread_can_reopen_after_cleanup(memory, tier):
    store = getattr(memory, f'store_{tier}_term')
    search = getattr(memory, f'search_{tier}_term')
    first_id = store('first record')
    connection = getattr(memory._local, 'stm_conn' if tier == 'short' else 'ltm_conn')
    memory.close_connections()
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        connection.execute('SELECT 1')
    memory.close_connections()
    assert [record['id'] for record in search('first record')] == [first_id]
    second_id = store('second record')
    assert second_id != first_id
    assert {record['id'] for record in search('record')} == {first_id, second_id}


@pytest.mark.parametrize('tier', ['short', 'long'])
def test_search_before_cleanup_is_unchanged(memory, tier):
    record_id = getattr(memory, f'store_{tier}_term')('control record')
    records = getattr(memory, f'search_{tier}_term')('control record')
    assert [record['id'] for record in records] == [record_id]
