import sys

import pytest

from praisonaiagents.session.store import DefaultSessionStore
from praisonai_mcp.mcp_server.adapters.cli_tools import register_cli_tools
from praisonai_mcp.mcp_server.registry import get_tool_registry


@pytest.fixture
def session_delete(tmp_path, monkeypatch):
    store = DefaultSessionStore(session_dir=str(tmp_path))
    monkeypatch.setattr('praisonaiagents.session.get_default_session_store', lambda: store)
    register_cli_tools()
    return store, get_tool_registry().get('praisonai.session.delete').handler


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows file sharing semantics')
def test_locked_session_file_reports_failure(session_delete):
    store, handler = session_delete
    assert store.add_message('locked', 'user', 'keep me')
    path = store._get_session_path('locked')
    with open(path, 'rb'):
        assert handler('locked') == 'Error: Failed to delete session: locked'
    assert store.session_exists('locked')


def test_success_and_missing_session_remain_idempotent(session_delete):
    store, handler = session_delete
    assert store.add_message('existing', 'user', 'hello')
    assert handler('existing') == 'Session deleted: existing'
    assert not store.session_exists('existing')
    assert handler('missing') == 'Session deleted: missing'


def test_store_false_and_exception_are_reported(session_delete, monkeypatch):
    store, handler = session_delete
    monkeypatch.setattr(store, 'delete_session', lambda _: False)
    assert handler('failed') == 'Error: Failed to delete session: failed'

    def fail(_):
        raise OSError('storage unavailable')

    monkeypatch.setattr(store, 'delete_session', fail)
    assert handler('failed') == 'Error: storage unavailable'
