from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

import pytest

from praisonaiagents import Agent, MemoryConfig
from praisonaiagents.session.store import DefaultSessionStore, SessionResumeReadError
from praisonaiagents.session.sqlite_transcript_store import SqliteTranscriptStore
from praisonaiagents.session.sqlite_store import SqliteSessionStore


@pytest.mark.parametrize('history', [False, True])
def test_agent_does_not_run_before_transient_resume_succeeds(tmp_path, monkeypatch, history):
    seed = DefaultSessionStore(session_dir=str(tmp_path))
    seed.add_user_message('s', 'old')
    path = tmp_path / 's.json'
    original_bytes = path.read_bytes()
    store = DefaultSessionStore(session_dir=str(tmp_path))
    load = store._load_session_from_disk
    failure = [True]

    def transient(*args):
        if failure[0]:
            failure[0] = False
            raise PermissionError('temporary')
        return load(*args)

    monkeypatch.setattr(store, '_load_session_from_disk', transient)
    agent = Agent(name='test', memory=MemoryConfig(session_id='s', history=history))
    agent._session_store = store
    received = []

    def completion(messages, *args, **kwargs):
        received.append(list(messages))
        message = SimpleNamespace(content='answer', tool_calls=None, role='assistant', reasoning_content=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason='stop', index=0)],
                               usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2), model='synthetic')

    with patch.object(Agent, '_openai_client', new_callable=PropertyMock, return_value=None), patch.object(agent, '_chat_completion', side_effect=completion):
        with pytest.raises(SessionResumeReadError):
            agent.chat('new')
        assert not received
        assert path.read_bytes() == original_bytes
        assert agent._session_store is store and not agent._session_store_initialized
        agent.chat('new')
        agent.chat('next')
    assert len(received) == 2
    assert any(item.get('content') == 'old' for item in received[0])
    messages = store.get_chat_history('s')
    assert [(x['role'], x['content']) for x in messages] == [
        ('user', 'old'), ('user', 'new'), ('assistant', 'answer'),
        ('user', 'next'), ('assistant', 'answer')]


def test_ordinary_reads_keep_existing_empty_fallback(tmp_path, monkeypatch):
    store = DefaultSessionStore(session_dir=str(tmp_path))
    store.add_user_message('cached', 'cached history')
    def fail(*args):
        raise PermissionError('temporary')
    monkeypatch.setattr(store, '_load_session_from_disk', fail)
    assert store.get_working_history('s') == []
    assert store.get_working_history('cached') == [{'role': 'user', 'content': 'cached history'}]


def test_custom_store_override_is_not_bypassed(tmp_path):
    class CustomStore(DefaultSessionStore):
        def get_working_history(self, session_id, max_messages=None):
            return [{'role': 'user', 'content': 'custom'}]
    store = CustomStore(session_dir=str(tmp_path))
    agent = Agent(name='test', memory=MemoryConfig(session_id='s'))
    agent._session_store = store
    agent._init_session_store()
    assert agent.chat_history == [{'role': 'user', 'content': 'custom'}]


def test_protocol_store_still_uses_its_public_history_method():
    class CustomStore:
        def get_working_history(self, session_id):
            return [{'role': 'user', 'content': 'custom protocol'}]
        def set_agent_info(self, *args, **kwargs):
            return True
    agent = Agent(name='test', memory=MemoryConfig(session_id='s'))
    agent._session_store = CustomStore()
    agent._init_session_store()
    assert agent.chat_history == [{'role': 'user', 'content': 'custom protocol'}]


def test_sqlite_transcript_resume_uses_its_own_backend(tmp_path):
    store = SqliteTranscriptStore(session_dir=str(tmp_path), db_path=':memory:')
    store.add_user_message('s', 'sqlite old')
    agent = Agent(name='test', memory=MemoryConfig(session_id='s'))
    agent._session_store = store
    agent._init_session_store()
    assert agent.chat_history == [{'role': 'user', 'content': 'sqlite old'}]
    store._conn.close()


@pytest.mark.parametrize('store_type', [DefaultSessionStore, SqliteSessionStore])
def test_resume_preserves_working_history_and_empty_sessions(tmp_path, store_type):
    store = store_type(session_dir=str(tmp_path), active_window=3)
    store.add_user_message('s', 'old')
    for i in range(8):
        store.add_user_message('s', f'later {i}')
    expected = store.get_working_history('s')
    agent = Agent(name='test', memory=MemoryConfig(session_id='s'))
    agent._session_store = store
    agent._init_session_store()
    assert agent.chat_history == expected
    empty = Agent(name='test', memory=MemoryConfig(session_id='new'))
    empty._session_store = store
    empty._init_session_store()
    assert empty.chat_history == [] and empty._session_store_initialized
    conn = getattr(store, '_conn', None)
    if conn is not None:
        conn.close()
