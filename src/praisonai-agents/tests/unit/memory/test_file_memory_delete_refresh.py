"""Selective deletion must preserve records written by another file-memory user."""

import pytest

from praisonaiagents.memory.file_memory import FileMemory


def add(memory, kind, content):
    if kind.startswith('entity'):
        return memory.add_entity(content, 'concept')
    return getattr(memory, f'add_{kind}')(content)


def delete(memory, kind, memory_id, content):
    if kind == 'entity_name':
        return memory.delete_entity(content)
    if kind == 'entity_id':
        return memory.delete_entity(memory_id)
    return getattr(memory, f'delete_{kind}')(memory_id)


def ids(memory, kind):
    if kind.startswith('entity'):
        return {item.id for item in memory.get_all_entities()}
    return {item.id for item in getattr(memory, f'get_{kind}')()}


@pytest.mark.parametrize('kind', ['short_term', 'long_term', 'entity_name', 'entity_id'])
@pytest.mark.parametrize('target_from_other_instance', [False, True])
def test_selective_delete_uses_current_persisted_records(tmp_path, kind, target_from_other_instance):
    first = FileMemory(base_path=str(tmp_path))
    second = FileMemory(base_path=str(tmp_path))
    if target_from_other_instance:
        survivor_id = add(first, kind, 'preserve this record')
        target_id = add(second, kind, 'remove this record')
    else:
        target_id = add(first, kind, 'remove this record')
        survivor_id = add(second, kind, 'preserve this record')

    assert delete(first, kind, target_id, 'remove this record')
    reloaded = FileMemory(base_path=str(tmp_path))
    assert ids(reloaded, kind) == {survivor_id}
    assert ids(first, kind) == {survivor_id}


@pytest.mark.parametrize('kind', ['short_term', 'long_term', 'entity_name', 'entity_id'])
def test_missing_delete_preserves_other_instance_records(tmp_path, kind):
    first = FileMemory(base_path=str(tmp_path))
    second = FileMemory(base_path=str(tmp_path))
    survivor_id = add(second, kind, 'preserve this record')
    assert not delete(first, kind, 'missing-id', 'missing-name')
    assert ids(FileMemory(base_path=str(tmp_path)), kind) == {survivor_id}
