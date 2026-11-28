from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

import pytest
from praisonaiagents import Agent
from praisonaiagents.compaction.compactor import ContextCompactor
from praisonaiagents.compaction.strategy import CompactionStrategy
from praisonaiagents.config import MemoryConfig
from praisonaiagents.session.store import DefaultSessionStore
from praisonaiagents.session.sqlite_store import SqliteSessionStore
from praisonaiagents.session.sqlite_transcript_store import SqliteTranscriptStore


@pytest.mark.parametrize('store_type', [DefaultSessionStore, SqliteSessionStore, SqliteTranscriptStore])
def test_resume_retains_recent_messages_from_compaction(tmp_path, store_type):
    store = store_type(session_dir=str(tmp_path))
    for i in range(10):
        store.add_user_message('s', f'user {i} ' + 'x' * 200)
        store.add_assistant_message('s', f'assistant {i} ' + 'y' * 200)
    agent = Agent(name='writer', memory=MemoryConfig(session_id='s'))
    agent._session_store = store
    agent._init_session_store()
    compactor = ContextCompactor(max_tokens=300, strategy=CompactionStrategy.SUMMARIZE, preserve_recent=4)
    policy = SimpleNamespace(strategy=SimpleNamespace(value='summarise'))
    _, compacted = agent._apply_compaction(agent.chat_history, compactor, policy)
    assert len(compacted) == 5
    resumed = Agent(name='writer', memory=MemoryConfig(session_id='s'))
    resumed._session_store = store_type(session_dir=str(tmp_path))
    resumed._init_session_store()
    assert resumed.chat_history == compacted


def test_append_during_compaction_survives_resume(tmp_path, monkeypatch):
    store = DefaultSessionStore(session_dir=str(tmp_path))
    for i in range(10):
        store.add_user_message('s', f'user {i} ' + 'x' * 200)
        store.add_assistant_message('s', f'assistant {i} ' + 'y' * 200)
    agent = Agent(name='writer', memory=MemoryConfig(session_id='s'))
    agent._session_store = store
    agent._init_session_store()
    compactor = ContextCompactor(max_tokens=300, strategy=CompactionStrategy.SUMMARIZE, preserve_recent=4)
    compact = compactor.compact
    def concurrent(messages):
        result = compact(messages)
        store.add_user_message('s', 'concurrent append')
        return result
    monkeypatch.setattr(compactor, 'compact', concurrent)
    _, compacted = agent._apply_compaction(agent.chat_history, compactor, SimpleNamespace(strategy=SimpleNamespace(value='summarise')))
    resumed = Agent(name='writer', memory=MemoryConfig(session_id='s'))
    resumed._session_store = DefaultSessionStore(session_dir=str(tmp_path))
    resumed._init_session_store()
    assert resumed.chat_history == compacted + [{'role': 'user', 'content': 'concurrent append'}]


def test_repeated_compaction_restores_latest_retained_tail(tmp_path):
    store = DefaultSessionStore(session_dir=str(tmp_path))
    for i in range(10):
        store.add_user_message('s', f'user {i} ' + 'x' * 200)
        store.add_assistant_message('s', f'assistant {i} ' + 'y' * 200)
    policy = SimpleNamespace(strategy=SimpleNamespace(value='summarise'))
    agent = Agent(name='writer', memory=MemoryConfig(session_id='s'))
    agent._session_store = store
    agent._init_session_store()
    agent._apply_compaction(agent.chat_history, ContextCompactor(max_tokens=300, preserve_recent=4), policy)
    for i in range(5):
        store.add_user_message('s', f'new {i} ' + 'z' * 200)
        store.add_assistant_message('s', f'reply {i} ' + 'q' * 200)
    restored = Agent(name='writer', memory=MemoryConfig(session_id='s'))
    restored._session_store = store
    restored._init_session_store()
    _, compacted = restored._apply_compaction(restored.chat_history, ContextCompactor(max_tokens=300, preserve_recent=4), policy)
    again = Agent(name='writer', memory=MemoryConfig(session_id='s'))
    again._session_store = DefaultSessionStore(session_dir=str(tmp_path))
    again._init_session_store()
    assert again.chat_history == compacted


def test_retained_tool_call_and_result_survive_resume(tmp_path):
    store = DefaultSessionStore(session_dir=str(tmp_path))
    for i in range(10):
        store.add_user_message('s', f'user {i} ' + 'x' * 200)
        store.add_assistant_message('s', f'assistant {i} ' + 'y' * 200)
    calls = [{'id': 'c1', 'type': 'function', 'function': {'name': 'lookup', 'arguments': '{}'}}]
    store.add_message('s', 'assistant', '', tool_calls=calls)
    store.add_message('s', 'tool', 'answer', tool_call_id='c1')
    agent = Agent(name='writer', memory=MemoryConfig(session_id='s'))
    agent._session_store = store
    agent._init_session_store()
    _, compacted = agent._apply_compaction(agent.chat_history, ContextCompactor(max_tokens=300, preserve_recent=4), SimpleNamespace(strategy=SimpleNamespace(value='summarise')))
    resumed = Agent(name='writer', memory=MemoryConfig(session_id='s'))
    resumed._session_store = DefaultSessionStore(session_dir=str(tmp_path))
    resumed._init_session_store()
    assert resumed.chat_history == compacted
    assert resumed.chat_history[-2]['tool_calls'] == calls
    assert resumed.chat_history[-1]['tool_call_id'] == 'c1'


def test_dynamic_system_prompt_is_not_replayed(tmp_path):
    store = DefaultSessionStore(session_dir=str(tmp_path))
    for i in range(10):
        store.add_user_message('s', f'user {i} ' + 'x' * 200)
        store.add_assistant_message('s', f'assistant {i} ' + 'y' * 200)
    agent = Agent(name='writer', memory=MemoryConfig(session_id='s'))
    agent._session_store = store
    agent._init_session_store()
    messages = [{'role': 'system', 'content': 'dynamic instructions'}] + agent.chat_history
    _, compacted = agent._apply_compaction(messages, ContextCompactor(max_tokens=300, preserve_recent=4), SimpleNamespace(strategy=SimpleNamespace(value='summarise')))
    resumed = Agent(name='writer', memory=MemoryConfig(session_id='s'))
    resumed._session_store = DefaultSessionStore(session_dir=str(tmp_path))
    resumed._init_session_store()
    assert resumed.chat_history == compacted[1:]


def test_persisted_system_message_is_retained(tmp_path):
    store = DefaultSessionStore(session_dir=str(tmp_path))
    store.add_message('s', 'system', 'persistent instruction')
    for i in range(10):
        store.add_user_message('s', f'user {i} ' + 'x' * 200)
        store.add_assistant_message('s', f'assistant {i} ' + 'y' * 200)
    agent = Agent(name='writer', memory=MemoryConfig(session_id='s'))
    agent._session_store = store
    agent._init_session_store()
    messages = [{'role': 'system', 'content': 'dynamic instructions'}] + agent.chat_history
    _, compacted = agent._apply_compaction(messages, ContextCompactor(max_tokens=300, preserve_recent=4), SimpleNamespace(strategy=SimpleNamespace(value='summarise')))
    resumed = Agent(name='writer', memory=MemoryConfig(session_id='s'))
    resumed._session_store = DefaultSessionStore(session_dir=str(tmp_path))
    resumed._init_session_store()
    assert resumed.chat_history == compacted[1:]


def test_replaced_transcript_is_not_hidden_by_stale_checkpoint(tmp_path, monkeypatch):
    store = DefaultSessionStore(session_dir=str(tmp_path))
    for i in range(10):
        store.add_user_message('s', f'user {i} ' + 'x' * 200)
        store.add_assistant_message('s', f'assistant {i} ' + 'y' * 200)
    agent = Agent(name='writer', memory=MemoryConfig(session_id='s'))
    agent._session_store = store
    agent._init_session_store()
    compactor = ContextCompactor(max_tokens=300, preserve_recent=4)
    compact = compactor.compact
    def replace(messages):
        result = compact(messages)
        store.clear_session('s')
        store.add_user_message('s', 'replacement')
        return result
    monkeypatch.setattr(compactor, 'compact', replace)
    agent._apply_compaction(agent.chat_history, compactor, SimpleNamespace(strategy=SimpleNamespace(value='summarise')))
    resumed = Agent(name='writer', memory=MemoryConfig(session_id='s'))
    resumed._session_store = DefaultSessionStore(session_dir=str(tmp_path))
    resumed._init_session_store()
    assert resumed.chat_history == [{'role': 'user', 'content': 'replacement'}]


def test_built_prompt_persisted_before_compaction_is_not_duplicated(tmp_path):
    store = DefaultSessionStore(session_dir=str(tmp_path))
    for i in range(10):
        store.add_user_message('s', f'user {i} ' + 'x' * 200)
        store.add_assistant_message('s', f'assistant {i} ' + 'y' * 200)
    agent = Agent(name='writer', memory=MemoryConfig(session_id='s'))
    agent._session_store = store
    agent._init_session_store()
    with patch.object(Agent, '_openai_client', new_callable=PropertyMock, return_value=None):
        messages, _ = agent._build_messages('current prompt')
    store.add_user_message('s', 'current prompt')
    _, compacted = agent._apply_compaction(messages, ContextCompactor(max_tokens=300, preserve_recent=4), SimpleNamespace(strategy=SimpleNamespace(value='summarise')))
    resumed = Agent(name='writer', memory=MemoryConfig(session_id='s'))
    resumed._session_store = DefaultSessionStore(session_dir=str(tmp_path))
    resumed._init_session_store()
    assert resumed.chat_history[-1] == {'role': 'user', 'content': 'current prompt'}
    assert sum(m.get('content') == 'current prompt' for m in resumed.chat_history) == 1
    assert resumed.chat_history == compacted[1:]
