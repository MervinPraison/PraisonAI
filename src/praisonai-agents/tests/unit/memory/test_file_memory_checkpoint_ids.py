"""Automatic checkpoint names must retain independent recoverable snapshots."""

from types import SimpleNamespace

import pytest

from praisonaiagents.memory import FileMemory
from praisonaiagents.memory import file_memory


@pytest.fixture
def fixed_second(monkeypatch):
    monkeypatch.setattr(file_memory, 'time', SimpleNamespace(time=lambda: 1700000000.0))


@pytest.mark.parametrize('reopen', [False, True])
def test_same_second_checkpoints_restore_their_own_snapshots(tmp_path, fixed_second, reopen):
    memory = FileMemory(base_path=str(tmp_path))
    memory.add_short_term('first record')
    first = memory.create_checkpoint()
    if reopen:
        memory = FileMemory(base_path=str(tmp_path))
    memory.add_short_term('second record')
    second = memory.create_checkpoint()

    assert first != second
    assert {entry['id'] for entry in memory.list_checkpoints()} == {first, second}
    assert memory.restore_checkpoint(first)
    assert [item.content for item in memory.get_short_term()] == ['first record']
    assert memory.restore_checkpoint(second)
    assert {item.content for item in memory.get_short_term()} == {'first record', 'second record'}
    assert memory.delete_checkpoint(first)
    assert memory.restore_checkpoint(second)


def test_explicit_checkpoint_name_is_preserved(tmp_path, fixed_second):
    memory = FileMemory(base_path=str(tmp_path))
    memory.add_short_term('named record')
    assert memory.create_checkpoint(name='before-edit') == 'before-edit'
    memory.clear_short_term()
    assert memory.restore_checkpoint('before-edit')
    assert [item.content for item in memory.get_short_term()] == ['named record']


def test_missing_checkpoint_returns_false(tmp_path):
    memory = FileMemory(base_path=str(tmp_path))
    memory.add_short_term('existing record')
    assert not memory.restore_checkpoint('missing-checkpoint')
    assert [item.content for item in memory.get_short_term()] == ['existing record']
