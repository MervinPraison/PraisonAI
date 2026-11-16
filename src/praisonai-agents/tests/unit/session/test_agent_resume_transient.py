"""A transient session read error at first resume must not permanently start
the Agent with empty history, and must not raise out of the turn."""
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

import pytest

from praisonaiagents import Agent, MemoryConfig
from praisonaiagents.session.store import DefaultSessionStore
from praisonaiagents.session.sqlite_transcript_store import SqliteTranscriptStore
from praisonaiagents.session.sqlite_store import SqliteSessionStore


@pytest.fixture(autouse=True)
def isolate_spill_directory(tmp_path, monkeypatch):
    monkeypatch.setattr('praisonaiagents.paths.get_session_spill_dir', lambda: tmp_path / 'spill')


def _run_turns(agent, *prompts, between=None):
    """Run chat turns against a fake LLM; return the messages each call saw."""
    received = []

    def completion(messages, *args, **kwargs):
        received.append([(m.get('role'), m.get('content')) for m in messages])
        message = SimpleNamespace(content='answer', tool_calls=None, role='assistant', reasoning_content=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason='stop', index=0)],
                               usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
                               model='synthetic')

    with patch.object(Agent, '_openai_client', new_callable=PropertyMock, return_value=None), \
            patch.object(agent, '_chat_completion', side_effect=completion):
        for i, prompt in enumerate(prompts):
            if i and between:
                between()
            agent.chat(prompt)
    return received


def _seeded_store(tmp_path):
    DefaultSessionStore(session_dir=str(tmp_path)).add_user_message('s', 'old')
    return DefaultSessionStore(session_dir=str(tmp_path))


class _FlakyStore:
    """A store whose first history read raises OSError, then succeeds."""

    def __init__(self):
        self.calls = 0
        self.messages = [{'role': 'user', 'content': 'old'}]

    def get_working_history(self, session_id):
        self.calls += 1
        if self.calls == 1:
            raise PermissionError('storage briefly unavailable')
        return list(self.messages)

    def set_agent_info(self, *args, **kwargs):
        return True

    def add_user_message(self, session_id, content, metadata=None):
        self.messages.append({'role': 'user', 'content': content})

    def add_assistant_message(self, session_id, content, metadata=None):
        self.messages.append({'role': 'assistant', 'content': content})


def test_store_raising_oserror_is_retried_next_turn():
    store = _FlakyStore()
    agent = Agent(name='test', memory=MemoryConfig(session_id='s'))
    agent._session_store = store
    received = _run_turns(agent, 'new', 'next')
    assert ('user', 'old') not in received[0]
    assert agent._session_store is store and agent._session_store_initialized
    assert ('user', 'old') in received[1]
    assert [c for r, c in received[1] if r != 'system'] == ['old', 'new', 'answer', 'next']


def test_default_store_single_read_failure_still_resumes(tmp_path, monkeypatch):
    store = _seeded_store(tmp_path)
    load = store._load_session_from_disk
    failures = [1]

    def transient(*args):
        if failures[0]:
            failures[0] -= 1
            raise PermissionError('temporary')
        return load(*args)

    monkeypatch.setattr(store, '_load_session_from_disk', transient)
    agent = Agent(name='test', memory=MemoryConfig(session_id='s'))
    agent._session_store = store
    received = _run_turns(agent, 'new')
    assert ('user', 'old') in received[0]


@pytest.mark.parametrize('outage', ['init', 'whole_turn'])
def test_default_store_outage_retries_without_losing_or_duplicating(tmp_path, monkeypatch, outage):
    store = _seeded_store(tmp_path)
    path = tmp_path / 's.json'
    load = store._load_session_from_disk
    down = [True]

    def transient(*args):
        if down[0]:
            raise PermissionError('storage down')
        return load(*args)

    monkeypatch.setattr(store, '_load_session_from_disk', transient)
    agent = Agent(name='test', memory=MemoryConfig(session_id='s'))
    agent._session_store = store
    original = agent._init_session_store

    def init_then_maybe_recover():
        original()
        if outage == 'init':
            down[0] = False  # storage recovers before turn 1 is persisted

    monkeypatch.setattr(agent, '_init_session_store', init_then_maybe_recover)
    before = path.read_bytes()

    def recover():
        if outage == 'whole_turn':
            assert path.read_bytes() == before  # nothing overwritten while down
        down[0] = False

    received = _run_turns(agent, 'new', 'next', between=recover)
    assert ('user', 'old') not in received[0]
    convo = [c for r, c in received[1] if r != 'system']
    assert convo == ['old', 'new', 'answer', 'next']
    assert agent._session_store is store and agent._session_store_initialized


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


def test_custom_store_without_set_agent_info_still_restores_history():
    """A store that only implements the protocol keeps resuming history."""
    from praisonaiagents import Agent

    class MinimalStore:
        def get_chat_history(self, session_id, max_messages=None):
            return [{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "reply"}]

        def add_message(self, *a, **k):
            return True

        def add_user_message(self, *a, **k):
            return True

        def add_assistant_message(self, *a, **k):
            return True

    agent = Agent(name="t", instructions="x", llm="gpt-4o-mini")
    agent._session_store = MinimalStore()
    agent._session_id = "s1"
    agent._session_store_initialized = False
    agent._init_session_store()
    assert [m["content"] for m in agent.chat_history][:2] == ["earlier", "reply"]

