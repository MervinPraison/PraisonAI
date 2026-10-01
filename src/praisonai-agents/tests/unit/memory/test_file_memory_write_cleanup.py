"""An unsuccessful atomic JSON write must not leave its staging file behind."""

import pytest

from praisonaiagents.memory import FileMemory


def store(memory, kind, text, metadata):
    if kind == 'entity':
        return memory.add_entity(text, 'concept', attributes=metadata)
    if kind == 'summary':
        return memory.add_summary(text, 'short_term', 1, metadata=metadata)
    return getattr(memory, f'add_{kind}')(text, metadata=metadata)


def path_for(memory, kind):
    name = {'entity': 'entities', 'summary': 'summaries'}.get(kind, kind)
    return getattr(memory, f'{name}_file')


@pytest.mark.parametrize('kind', ['short_term', 'long_term', 'entity', 'summary'])
def test_serialization_failure_removes_atomic_write_temp_file(tmp_path, kind):
    memory = FileMemory(base_path=str(tmp_path))
    store(memory, kind, 'existing record', {'valid': True})
    before = path_for(memory, kind).read_bytes()
    with pytest.raises(TypeError, match='JSON serializable'):
        store(memory, kind, 'unsuccessful record', {'unsupported': object()})
    assert path_for(memory, kind).read_bytes() == before
    assert list(memory.user_path.glob('.*.tmp')) == []


@pytest.mark.parametrize('kind', ['short_term', 'long_term', 'entity', 'summary'])
def test_successful_atomic_write_does_not_leave_temp_file(tmp_path, kind):
    memory = FileMemory(base_path=str(tmp_path))
    store(memory, kind, 'successful record', {'valid': True})
    assert 'successful record' in path_for(memory, kind).read_text(encoding='utf-8')
    assert list(memory.user_path.glob('.*.tmp')) == []
