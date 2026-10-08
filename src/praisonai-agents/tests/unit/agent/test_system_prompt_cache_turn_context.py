"""Cached prompt prefixes must retain the current turn's trailing context."""

from types import SimpleNamespace

import pytest

from praisonaiagents import Agent


def sample_tool() -> str:
    """Return a fixed local result."""
    return 'result'


@pytest.fixture
def agent():
    """Close the local agent after each prompt assembly check."""
    instance = Agent(instructions='Answer briefly', tools=[sample_tool], context=False)
    yield instance
    instance.close()


@pytest.mark.parametrize('override', [None, [], [sample_tool]])
def test_cache_hit_preserves_complete_prompt(agent, override):
    """Retain full prompt contents for each explicit tool override."""
    first = agent._build_system_prompt(tools=override)
    second = agent._build_system_prompt(tools=override)
    assert second == first
    assert ('sample_tool' in second) is (override != [])


def test_cache_hit_refreshes_current_default_tools(agent, monkeypatch):
    """A reused prefix must advertise the current default tool set."""
    def replacement_tool() -> str:
        """Return a different fixed local result."""
        return 'replacement'

    builds = []
    monkeypatch.setattr(
        agent, '_resolve_harness_base_prompt',
        lambda: builds.append('build') or 'stable prefix',
    )
    first = agent._build_system_prompt(tools=None)
    assert 'sample_tool' in first
    assert 'replacement_tool' not in first

    agent.tools = [replacement_tool]
    second = agent._build_system_prompt(tools=None)
    assert builds == ['build']
    assert 'stable prefix' in second
    assert 'replacement_tool' in second
    assert 'sample_tool' not in second


def test_cache_hit_refreshes_session_context(agent, monkeypatch):
    """Read the current session origin instead of caching its old value."""
    import praisonaiagents.session.context as context

    current = SimpleNamespace(origin=SimpleNamespace(
        platform='first_platform', chat_type='private', display_name='first room', thread_id=None,
    ), reachable_targets=[])
    monkeypatch.setattr(context, 'get_session_context', lambda: current)
    first = agent._build_system_prompt()
    assert 'first_platform' in first
    current.origin.platform = 'second_platform'
    current.origin.display_name = 'second room'
    second = agent._build_system_prompt()
    assert 'second_platform' in second
    assert 'first_platform' not in second
    assert 'sample_tool' in second


def test_cache_hit_retains_prefix_reuse_and_appends_suffix_once(agent, monkeypatch):
    """Reuse the stable prefix while adding the suffix exactly once."""
    calls = []
    agent._resolve_harness_base_prompt = lambda: calls.append('build') or 'stable prefix'
    monkeypatch.setenv('PRAISONAI_APPEND_SYSTEM_PROMPT', 'per-turn suffix')
    first = agent._build_system_prompt()
    second = agent._build_system_prompt()
    assert calls == ['build']
    assert first.count('per-turn suffix') == 1
    assert second.count('per-turn suffix') == 1
    assert 'stable prefix' in second
