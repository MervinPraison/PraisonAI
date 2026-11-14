from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import builtins
import os
import json
import subprocess
import sys

import pytest

from praisonaiagents.session.store import DefaultSessionStore
from praisonaiagents.session.sqlite_transcript_store import SqliteTranscriptStore


def make_legacy(path):
    store = DefaultSessionStore(session_dir=str(path))
    assert store.add_message('a', 'user', 'old a')
    assert store.add_message('b', 'user', 'old b')


def test_json_named_directory_is_skipped(tmp_path):
    make_legacy(tmp_path)
    (tmp_path / 'broken.json').mkdir()
    store = SqliteTranscriptStore(session_dir=str(tmp_path))
    assert store.get_chat_history('a')[0]['content'] == 'old a'
    assert store.get_chat_history('b')[0]['content'] == 'old b'


def test_unreliable_isdir_result_does_not_suppress_legacy_import(tmp_path, monkeypatch):
    make_legacy(tmp_path)
    original_isdir = os.path.isdir
    db_path = str(tmp_path / 'database' / 'sessions.db')
    store = SqliteTranscriptStore(session_dir=str(tmp_path), db_path=db_path)
    with monkeypatch.context() as patch:
        patch.setattr(os.path, 'isdir', lambda path: False if os.fspath(path) == str(tmp_path) else original_isdir(path))
        assert store.get_chat_history('a')[0]['content'] == 'old a'
    assert SqliteTranscriptStore(session_dir=str(tmp_path), db_path=db_path).get_chat_history('b')[0]['content'] == 'old b'


def test_directory_access_failure_does_not_mark_migration_complete(tmp_path, monkeypatch):
    make_legacy(tmp_path)
    store = SqliteTranscriptStore(session_dir=str(tmp_path))
    original_listdir = os.listdir

    def inaccessible(path):
        if os.fspath(path) == str(tmp_path):
            raise PermissionError('directory unavailable')
        return original_listdir(path)

    with monkeypatch.context() as patch:
        patch.setattr(os, 'listdir', inaccessible)
        with pytest.raises(PermissionError):
            store.get_chat_history('a')
    assert store.get_chat_history('a')[0]['content'] == 'old a'
    assert store.get_chat_history('b')[0]['content'] == 'old b'


def test_oversized_json_integer_does_not_block_healthy_sessions(tmp_path):
    make_legacy(tmp_path)
    bad = tmp_path / '0-malformed.json'
    bad.write_text('{"session_id":"bad","metadata":{"value":' + '9' * 5000 + '}}', encoding='utf-8')
    store = SqliteTranscriptStore(session_dir=str(tmp_path))
    assert store.get_chat_history('a')[0]['content'] == 'old a'
    assert store.get_chat_history('b')[0]['content'] == 'old b'
    assert bad.exists()


@pytest.mark.parametrize('missing', [None, 'nonexistent'])
def test_missing_legacy_directory_does_not_scan_cwd(tmp_path, monkeypatch, missing):
    make_legacy(tmp_path)
    store = SqliteTranscriptStore(session_dir=str(tmp_path), db_path=str(tmp_path / 'separate.db'))
    store.session_dir = str(tmp_path / missing) if missing else None
    monkeypatch.chdir(tmp_path)
    assert store.list_sessions() == []


@pytest.mark.parametrize('bad_data', [
    {'session_id': 'bad', 'last_compaction': 5},
    {'session_id': 'bad', 'messages': 5},
    {'session_id': 'bad', 'metadata': 5},
    {'session_id': 'bad', 'agent_name': []},
    {'session_id': 'bad', 'agent_id': {}},
    {'session_id': 'bad', 'gateway_session_id': []},
    {'session_id': 'bad', 'updated_at': {}},
    {'session_id': [], 'agent_name': 'agent'},
    {'session_id': 'bad', 'agent_name': 2**80},
    {'session_id': 'bad', 'metadata': {'text': '\ud800'}},
    {'session_id': 'bad', 'agent_name': '\ud800'},
    {'session_id': 'bad', 'messages': [{'role': 'user', 'content': '\ud800'}]},
])
def test_malformed_legacy_structure_does_not_block_healthy_sessions(tmp_path, bad_data):
    make_legacy(tmp_path)
    bad = tmp_path / '0-malformed.json'
    bad.write_text(json.dumps(bad_data), encoding='utf-8')
    store = SqliteTranscriptStore(session_dir=str(tmp_path))
    assert store.get_chat_history('a')[0]['content'] == 'old a'
    assert store.get_chat_history('b')[0]['content'] == 'old b'
    assert bad.exists()


def test_valid_unicode_legacy_is_preserved(tmp_path):
    legacy = DefaultSessionStore(session_dir=str(tmp_path))
    assert legacy.add_message('unicode', 'user', '你好 🌍')
    store = SqliteTranscriptStore(session_dir=str(tmp_path))
    assert store.get_chat_history('unicode')[0]['content'] == '你好 🌍'


def test_interrupted_migration_rolls_back_and_retries(tmp_path, monkeypatch):
    make_legacy(tmp_path)
    first = SqliteTranscriptStore(session_dir=str(tmp_path))
    write = first._write_row
    calls = []

    def interrupt(session, **kwargs):
        calls.append(session.session_id)
        if len(calls) == 2:
            raise RuntimeError('interrupted migration')
        return write(session, **kwargs)

    monkeypatch.setattr(first, '_write_row', interrupt)
    with pytest.raises(RuntimeError, match='interrupted migration'):
        first.list_sessions()
    recovered = SqliteTranscriptStore(session_dir=str(tmp_path))
    assert recovered.get_chat_history('a')[0]['content'] == 'old a'
    assert recovered.get_chat_history('b')[0]['content'] == 'old b'


def test_process_exit_during_migration_rolls_back(tmp_path):
    make_legacy(tmp_path)
    script = '''
import os, sys
from praisonaiagents.session.sqlite_transcript_store import SqliteTranscriptStore
class Interrupted(SqliteTranscriptStore):
    def _write_row(self, session, **kwargs):
        result = super()._write_row(session, **kwargs)
        os._exit(23)
store = Interrupted(session_dir=sys.argv[1])
store.list_sessions()
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)], check=False)
    assert result.returncode == 23
    recovered = SqliteTranscriptStore(session_dir=str(tmp_path))
    assert recovered.get_chat_history('a')[0]['content'] == 'old a'
    assert recovered.get_chat_history('b')[0]['content'] == 'old b'


def test_transient_failed_write_does_not_commit_partial(tmp_path, monkeypatch):
    make_legacy(tmp_path)
    first = SqliteTranscriptStore(session_dir=str(tmp_path))
    write = first._write_row
    monkeypatch.setattr(first, '_write_row', lambda session, **kw: False if session.session_id == 'b' else write(session, **kw))
    with pytest.raises(OSError, match='migration'):
        first.list_sessions()
    recovered = SqliteTranscriptStore(session_dir=str(tmp_path))
    assert recovered.get_chat_history('a')[0]['content'] == 'old a'
    assert recovered.get_chat_history('b')[0]['content'] == 'old b'


def test_completed_migration_does_not_resurrect_deleted_rows(tmp_path):
    make_legacy(tmp_path)
    store = SqliteTranscriptStore(session_dir=str(tmp_path))
    assert len(store.list_sessions()) == 2
    assert store.delete_session('a')
    assert store.delete_session('b')
    reopened = SqliteTranscriptStore(session_dir=str(tmp_path))
    assert reopened.list_sessions() == []
    assert (tmp_path / 'a.json').exists() and (tmp_path / 'b.json').exists()


def test_transient_read_failure_retries_on_same_store(tmp_path, monkeypatch):
    make_legacy(tmp_path)
    store = SqliteTranscriptStore(session_dir=str(tmp_path))
    original_open = builtins.open

    def unavailable(path, *args, **kwargs):
        if os.fspath(path) == str(tmp_path / 'b.json'):
            raise PermissionError('temporarily unavailable')
        return original_open(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(builtins, 'open', unavailable)
        with pytest.raises(PermissionError, match='temporarily unavailable'):
            store.list_sessions()
    assert store.get_chat_history('a')[0]['content'] == 'old a'
    assert store.get_chat_history('b')[0]['content'] == 'old b'


def test_existing_sqlite_data_is_not_overwritten_by_legacy_files(tmp_path):
    store = SqliteTranscriptStore(session_dir=str(tmp_path))
    assert store.add_message('a', 'user', 'new sqlite')
    make_legacy(tmp_path)
    reopened = SqliteTranscriptStore(session_dir=str(tmp_path))
    assert reopened.get_chat_history('a')[0]['content'] == 'new sqlite'
    assert reopened.get_chat_history('b') == []


def test_unmarked_existing_database_is_not_reimported(tmp_path):
    store = SqliteTranscriptStore(session_dir=str(tmp_path))
    assert store.add_message('a', 'user', 'new sqlite')
    store._connect().execute('DROP TABLE migration_state')
    make_legacy(tmp_path)
    reopened = SqliteTranscriptStore(session_dir=str(tmp_path))
    assert reopened.get_chat_history('a')[0]['content'] == 'new sqlite'
    assert reopened.get_chat_history('b') == []


def test_concurrent_first_open_imports_once_without_overwrite(tmp_path):
    make_legacy(tmp_path)
    barrier = Barrier(2)

    def open_store():
        store = SqliteTranscriptStore(session_dir=str(tmp_path))
        barrier.wait(timeout=5)
        return sorted(row['session_id'] for row in store.list_sessions())

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: open_store(), range(2)))
    assert results == [['a', 'b'], ['a', 'b']]
