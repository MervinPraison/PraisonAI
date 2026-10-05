"""Provider additions must belong to the request rather than its caller."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from praisonaiagents.llm.llm import LLM


def memory_tool():
    return SimpleNamespace(
        get_tool_definition=lambda: {'type': 'memory_20250818', 'name': 'memory'},
        get_beta_header=lambda: 'context-management-2025-06-27',
    )


@pytest.mark.parametrize('source', ['override', 'settings'])
@pytest.mark.parametrize('web_fetch', [False, True])
@pytest.mark.parametrize('memory', [False, True])
def test_provider_tool_additions_do_not_mutate_inputs(source, web_fetch, memory):
    tools = [{'type': 'function', 'function': {'name': 'local_tool'}}]
    original = deepcopy(tools)
    llm = LLM(model='anthropic/claude-sonnet-4-5', web_fetch=web_fetch,
              **({'tools': tools} if source == 'settings' else {}))
    llm._supports_claude_memory = lambda: memory
    llm._get_claude_memory_tool = memory_tool
    overrides = {'tools': tools} if source == 'override' else {}
    first = llm._build_completion_params(**overrides)
    first_snapshot = deepcopy(first['tools'])
    second = llm._build_completion_params(**overrides)
    assert tools == original
    assert first['tools'] == first_snapshot
    assert second['tools'] == first_snapshot
    assert len(second['tools']) == 1 + int(web_fetch) + int(memory)


@pytest.mark.parametrize('source', ['override', 'settings'])
def test_memory_beta_header_does_not_mutate_input_headers(source):
    headers = {'x-custom': 'keep'}
    llm = LLM(model='anthropic/claude-sonnet-4-5',
              **({'extra_headers': headers} if source == 'settings' else {}))
    llm._supports_claude_memory = lambda: True
    llm._get_claude_memory_tool = memory_tool
    result = llm._build_completion_params(
        **({'extra_headers': headers} if source == 'override' else {}),
    )
    assert headers == {'x-custom': 'keep'}
    assert result['extra_headers'] == {
        'x-custom': 'keep', 'anthropic-beta': 'context-management-2025-06-27',
    }
