"""Caller edits must not rewrite previously stored in-memory records."""

import pytest

from praisonaiagents.memory.adapters.in_memory_adapter import InMemoryAdapter


@pytest.mark.parametrize('tier', ['short', 'long'])
def test_store_snapshots_nested_metadata(tier):
    adapter = InMemoryAdapter()
    metadata = {'labels': ['original'], 'details': {'count': 1}}
    memory_id = getattr(adapter, f'store_{tier}_term')('original text', metadata)
    metadata['labels'].append('caller edit')
    metadata['details']['count'] = 2
    record = getattr(adapter, f'search_{tier}_term')('original')[0]
    assert record['id'] == memory_id
    assert record['metadata'] == {'labels': ['original'], 'details': {'count': 1}}


@pytest.mark.parametrize('tier', ['short', 'long'])
@pytest.mark.parametrize('read', ['search', 'all'])
def test_read_results_do_not_alias_stored_records(tier, read):
    adapter = InMemoryAdapter()
    memory_id = getattr(adapter, f'store_{tier}_term')(
        'original text', {'labels': ['original'], 'details': {'count': 1}},
    )
    search = getattr(adapter, f'search_{tier}_term')
    records = search('original') if read == 'search' else adapter.get_all_memories()
    records[0]['id'] = 'caller id'
    records[0]['text'] = 'caller text'
    records[0]['metadata']['labels'].append('caller edit')
    records[0]['metadata']['details']['count'] = 2
    records.clear()
    assert search('original') == [{
        'id': memory_id, 'text': 'original text', 'type': tier,
        'metadata': {'labels': ['original'], 'details': {'count': 1}},
    }]
    assert adapter.delete_memory(memory_id, tier=tier)
    assert adapter.get_all_memories() == []


@pytest.mark.parametrize('tier', ['short', 'long'])
@pytest.mark.parametrize('metadata', [None, {}])
def test_metadata_defaults_and_search_limits_remain_unchanged(tier, metadata):
    adapter = InMemoryAdapter()
    write = getattr(adapter, f'store_{tier}_term')
    expected_ids = [write('matching text', metadata) for _ in range(6)]
    search = getattr(adapter, f'search_{tier}_term')
    assert [record['id'] for record in search('matching')] == expected_ids[:5]
    assert [record['id'] for record in search('matching', limit=2)] == expected_ids[:2]
    assert all(record['metadata'] == metadata for record in adapter.get_all_memories())
