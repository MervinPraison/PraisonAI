"""Failed SQLite mutations must release transactions before peer access."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from praisonaiagents.memory.adapters.sqlite_adapter import SqliteMemoryAdapter


@pytest.mark.parametrize('tier', ['short', 'long'])
@pytest.mark.parametrize('backend', ['memory', 'file'])
@pytest.mark.parametrize('operation', ['store', 'delete', 'reset'])
def test_failed_mutation_releases_transaction_for_peer(tmp_path, tier, backend, operation):
    adapter = SqliteMemoryAdapter(
        ':memory:' if backend == 'memory' else str(tmp_path / 'short.db'),
        ':memory:' if backend == 'memory' else str(tmp_path / 'long.db'),
    )
    store = getattr(adapter, f'store_{tier}_term')
    search = getattr(adapter, f'search_{tier}_term')
    conn = getattr(adapter, '_get_stm_conn' if tier == 'short' else '_get_ltm_conn')()
    try:
        memory_id = store('existing record', {'user_id': 'owner'})
        sql_operation = 'INSERT' if operation == 'store' else 'DELETE'
        conn.execute(
            f"CREATE TRIGGER fail_mutation BEFORE {sql_operation} ON {tier}_term_memory "
            "BEGIN SELECT RAISE(ABORT, 'write failure'); END"
        )
        conn.commit()
        if operation == 'delete':
            assert adapter.delete_memory(memory_id, tier=tier) is False
        else:
            with pytest.raises(sqlite3.IntegrityError, match='write failure'):
                if operation == 'store':
                    store('failed record', {'user_id': 'owner'})
                else:
                    getattr(adapter, f'reset_{tier}_term')()
        assert conn.in_transaction is False
        conn.execute('DROP TRIGGER fail_mutation')
        conn.commit()

        def peer_round_trip():
            try:
                before = search('existing')
                peer_id = store('peer record')
                return before, peer_id, search('peer')
            finally:
                adapter.close_thread_connections()

        with ThreadPoolExecutor(max_workers=1) as pool:
            # Allow scheduling contention and SQLite's 10-second busy timeout;
            # this is a hang guard, not a three-second performance assertion.
            before, peer_id, after = pool.submit(peer_round_trip).result(timeout=60)
        assert [record['id'] for record in before] == [memory_id]
        assert [record['id'] for record in after] == [peer_id]
        assert search('failed') == []
        assert len(search('record')) == 2
    finally:
        conn.rollback()
        adapter.close_connections()
