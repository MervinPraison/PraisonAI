import json
from threading import Event, Thread, current_thread

import pytest

from praisonaiagents.tools.todo_tools import TodoTools
from praisonaiagents.utils import atomic_io
from praisonai_mcp.mcp_server.adapters.cli_tools import register_cli_tools
from praisonai_mcp.mcp_server.registry import get_tool_registry


@pytest.mark.parametrize('operation', ['add', 'complete', 'delete'])
def test_registered_mcp_mutation_preserves_concurrent_runtime_add(
    tmp_path, monkeypatch, operation
):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
    monkeypatch.setattr('praisonaiagents.approval.is_env_auto_approve', lambda: True)
    owner = TodoTools()
    assert json.loads(owner.todo_add('original'))['success']
    register_cli_tools()
    handler = get_tool_registry().get(f'praisonai.todo.{operation}').handler

    entered, release, runtime_done = Event(), Event(), Event()
    original_write = atomic_io.atomic_write_json
    results = {}

    def pause_mcp_write(*args, **kwargs):
        if current_thread().name == 'mcp-writer':
            entered.set()
            assert release.wait(5)
        return original_write(*args, **kwargs)

    monkeypatch.setattr(atomic_io, 'atomic_write_json', pause_mcp_write)

    def mcp_call():
        results['mcp'] = handler('mcp task' if operation == 'add' else '1')

    def runtime_call():
        results['runtime'] = json.loads(owner.todo_add('runtime task'))
        runtime_done.set()

    mcp_thread = Thread(target=mcp_call, name='mcp-writer')
    runtime_thread = Thread(target=runtime_call)
    try:
        mcp_thread.start()
        assert entered.wait(5)
        runtime_thread.start()
        runtime_done.wait(0.3)
    finally:
        release.set()
        mcp_thread.join(5)
        if runtime_thread.ident is not None:
            runtime_thread.join(5)

    assert not mcp_thread.is_alive() and not runtime_thread.is_alive()
    assert results['runtime']['success']
    assert results['mcp'].startswith(f'Todo {"added" if operation == "add" else "completed" if operation == "complete" else "deleted"}:')
    todos = owner._load_todos()
    assert any(todo['task'] == 'runtime task' for todo in todos)
    assert len({todo['id'] for todo in todos}) == len(todos)
    if operation == 'add':
        assert any(todo['task'] == 'mcp task' for todo in todos)
    elif operation == 'complete':
        assert next(todo for todo in todos if todo['id'] == 1)['status'] == 'completed'
    else:
        assert not any(todo['task'] == 'original' for todo in todos)


def test_missing_id_and_storage_errors_are_reported(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('USERPROFILE', str(tmp_path))
    register_cli_tools()
    registry = get_tool_registry()
    complete = registry.get('praisonai.todo.complete').handler
    delete = registry.get('praisonai.todo.delete').handler
    add = registry.get('praisonai.todo.add').handler
    assert complete('42') == 'Todo not found: 42'
    assert delete('42') == 'Todo not found: 42'

    def fail(*args, **kwargs):
        raise OSError('storage unavailable')

    monkeypatch.setattr(atomic_io, 'atomic_write_json', fail)
    assert add('task') == 'Error: storage unavailable'
