import json
import os

import pytest

from praisonaiagents.session.store import DefaultSessionStore
from praisonaiagents.session.sqlite_store import SqliteSessionStore
from praisonaiagents.tools.session_tools import SessionTools


def deny_directory(monkeypatch, directory):
    original = os.listdir

    def listdir(path):
        if os.fspath(path) == directory:
            raise PermissionError('session directory unavailable')
        return original(path)

    monkeypatch.setattr(os, 'listdir', listdir)


@pytest.mark.parametrize('method', ['agent', 'gateway', 'gateway_agent', 'search'])
def test_scan_errors_and_empty_query(tmp_path, monkeypatch, method):
    store = DefaultSessionStore(session_dir=str(tmp_path))
    tools = SessionTools(store=store)
    assert store.list_sessions_by_agent('agent') == []
    assert store.get_by_gateway_session('gateway') is None
    assert store.list_sessions_by_gateway_agent('agent') == []
    assert store.search('hello') == []
    assert store.add_message('one', 'user', 'hello')
    deny_directory(monkeypatch, store.session_dir)

    calls = {
        'agent': lambda: store.list_sessions_by_agent('agent'),
        'gateway': lambda: store.get_by_gateway_session('gateway'),
        'gateway_agent': lambda: store.list_sessions_by_gateway_agent('agent'),
        'search': lambda: store.search('hello'),
    }
    with pytest.raises(PermissionError, match='session directory unavailable'):
        calls[method]()
    result = json.loads(tools.session_search(query='hello'))
    assert result['success'] is False
    assert 'session directory unavailable' in result['error']
    assert store.search('  ') == []


def test_per_file_corruption_still_skipped(tmp_path, caplog):
    store = DefaultSessionStore(session_dir=str(tmp_path))
    assert store.add_message('good', 'user', 'hello')
    (tmp_path / 'bad.json').write_text('{', encoding='utf-8')
    assert store.list_sessions_by_agent('missing') == []
    assert store.get_by_gateway_session('missing') is None
    assert store.list_sessions_by_gateway_agent('missing') == []
    assert len(store.search('hello')) == 1
    assert 'Skipping unreadable session file' in caplog.text


def test_indexed_route_fallback_propagates_scan_failure(tmp_path, monkeypatch):
    store = SqliteSessionStore(session_dir=str(tmp_path))
    monkeypatch.setattr(store, '_connect', lambda: None)
    deny_directory(monkeypatch, store.session_dir)
    with pytest.raises(PermissionError, match='session directory unavailable'):
        store.get_by_gateway_session('gateway')
    with pytest.raises(PermissionError, match='session directory unavailable'):
        store.list_sessions_by_gateway_agent('agent')
    monkeypatch.setattr(store, '_read_search_candidates', lambda *args, **kwargs: None)
    with pytest.raises(PermissionError, match='session directory unavailable'):
        store.search('hello')
    assert store.search(' ') == []
