"""One SQLite adapter must expose the same records to all its worker threads."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from praisonaiagents.memory.adapters.sqlite_adapter import SqliteMemoryAdapter


@pytest.mark.parametrize('tier', ['short', 'long'])
@pytest.mark.parametrize('backend', ['memory', 'file'])
def test_worker_write_is_visible_on_the_calling_thread(tmp_path, tier, backend):
    adapter = SqliteMemoryAdapter(
        short_db=':memory:' if backend == 'memory' else str(tmp_path / 'short.db'),
        long_db=':memory:' if backend == 'memory' else str(tmp_path / 'long.db'),
    )
    write = getattr(adapter, f'store_{tier}_term')
    search = getattr(adapter, f'search_{tier}_term')
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            memory_id = pool.submit(write, 'worker record', {'source': 'worker'}).result()
            worker_records = pool.submit(search, 'worker').result()
            assert [record['id'] for record in worker_records] == [memory_id]
            assert search('worker') == worker_records
            assert adapter.delete_memory(memory_id, tier=tier)
            assert pool.submit(search, 'worker').result() == []
    finally:
        adapter.close_connections()


def test_memory_database_isolated_between_adapters_and_tiers():
    first = SqliteMemoryAdapter(':memory:', ':memory:')
    second = SqliteMemoryAdapter(':memory:', ':memory:')
    try:
        first.store_short_term('short record')
        assert first.search_long_term('') == []
        assert second.get_all_memories() == []
        second.store_long_term('second record')
        assert first.search_long_term('') == []
        assert second.search_short_term('') == []
    finally:
        first.close_connections()
        second.close_connections()


def test_parallel_memory_writes_keep_all_rows_and_unique_ids():
    adapter = SqliteMemoryAdapter(':memory:', ':memory:')
    workers = 4
    per_worker = 10
    # A barrier guarantees every worker's first write races the others on the
    # shared in-memory database, so the unique-ID assertion actually exercises
    # the cross-thread ID-collision scenario this regression test guards.
    start = threading.Barrier(workers)

    def write_batch(worker):
        start.wait()
        return [
            adapter.store_short_term(f'entry {worker}-{index}')
            for index in range(per_worker)
        ]

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            ids = [i for batch in pool.map(write_batch, range(workers)) for i in batch]
            counts = list(pool.map(lambda _: len(adapter.search_short_term('', limit=100)), range(8)))
        total = workers * per_worker
        assert len(set(ids)) == total
        assert counts == [total] * 8
        assert len(adapter.search_short_term('', limit=100)) == total
    finally:
        adapter.close_connections()
