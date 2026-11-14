import os

import pytest

from praisonaiagents.session.store import DefaultSessionStore
from praisonai_mcp.mcp_server.adapters.cli_tools import register_cli_tools
from praisonai_mcp.mcp_server.adapters.resources import register_mcp_resources
from praisonai_mcp.mcp_server.registry import get_resource_registry, get_tool_registry


@pytest.fixture
def interfaces(tmp_path, monkeypatch):
    store = DefaultSessionStore(session_dir=str(tmp_path))
    monkeypatch.setattr('praisonaiagents.session.get_default_session_store', lambda: store)
    register_cli_tools()
    register_mcp_resources()
    tool = get_tool_registry().get('praisonai.session.list').handler
    resource = get_resource_registry().get('praisonai://memory/sessions').handler
    return store, tool, resource


def test_directory_failure_reaches_callers(interfaces, monkeypatch):
    store, tool, resource = interfaces
    assert store.add_message('existing', 'user', 'hello')
    original_listdir = os.listdir

    def unavailable(path):
        if os.fspath(path) == store.session_dir:
            raise PermissionError('session directory unavailable')
        return original_listdir(path)

    monkeypatch.setattr(os, 'listdir', unavailable)
    with pytest.raises(PermissionError, match='session directory unavailable'):
        store.list_sessions()
    assert tool() == 'Error: session directory unavailable'
    assert resource() == {'error': 'session directory unavailable', 'sessions': []}


def test_empty_populated_and_bad_file_behavior(interfaces, tmp_path, caplog):
    store, tool, resource = interfaces
    assert store.list_sessions() == []
    assert tool() == '[]'
    assert resource() == {'sessions': []}
    assert store.add_message('existing', 'user', 'hello')
    (tmp_path / 'bad.json').write_text('{', encoding='utf-8')
    assert [item['session_id'] for item in store.list_sessions()] == ['existing']
    assert 'Skipping unreadable session file' in caplog.text
    assert 'existing' in tool()
    assert resource()['sessions'][0]['session_id'] == 'existing'
