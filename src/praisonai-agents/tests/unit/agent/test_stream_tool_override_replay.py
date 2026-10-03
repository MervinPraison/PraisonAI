"""Stream tool overrides must agree with the fallback replay policy."""

from types import SimpleNamespace

import pytest

from praisonaiagents import Agent


class ReadTimeout(Exception):
    pass


def configured_tool() -> str:
    """Return a fixed result."""
    return 'result'


@pytest.fixture
def stream_agent():
    agent = Agent(instructions='Answer briefly', tools=[configured_tool], context=False)
    yield agent
    agent.close()


@pytest.mark.parametrize('custom', [False, True])
@pytest.mark.parametrize('override', ['absent', 'none', 'empty'])
@pytest.mark.parametrize('fails', [False, True])
def test_stream_request_tools_match_fallback_policy(custom, override, fails, stream_agent):
    agent = stream_agent
    agent._using_custom_llm = custom
    agent._build_messages = lambda *args, **kw: ([{'role': 'user', 'content': 'question'}], 'question')
    sent = []
    fallback = []
    original = ReadTimeout('transport timeout')

    def record(**kwargs):
        sent.append(kwargs.get('tools'))
        if fails:
            raise original

    def native_create(**kwargs):
        record(**kwargs)
        delta = SimpleNamespace(content='ok', tool_calls=None)
        return iter([SimpleNamespace(choices=[SimpleNamespace(delta=delta)])])

    def custom_stream(**kwargs):
        record(**kwargs)
        yield 'ok'

    agent._Agent__openai_client = SimpleNamespace(sync_client=SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=native_create)),
    ))
    agent.llm_instance = SimpleNamespace(get_response_stream=custom_stream)

    def chat(prompt, **kwargs):
        fallback.append(kwargs)
        return 'fallback'

    agent.chat = chat
    kwargs = {} if override == 'absent' else {'tools': None if override == 'none' else []}
    if fails and override != 'empty':
        with pytest.raises(ReadTimeout) as exc_info:
            list(agent._start_stream_impl('question', **kwargs))
        assert exc_info.value is original
        assert fallback == []
    else:
        assert ''.join(agent._start_stream_impl('question', **kwargs)) == ('fallback' if fails else 'ok')
        assert len(fallback) == int(fails)
    assert len(sent) == 1
    assert bool(sent[0]) is (override != 'empty')


@pytest.mark.parametrize('override', ['absent', 'none', 'empty'])
def test_native_stream_prompt_matches_effective_tools(override, stream_agent):
    agent = stream_agent
    agent._using_custom_llm = False
    sent = []

    def build_messages(prompt, system_prompt=None, chat_history=None, **kwargs):
        return [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': prompt},
        ], prompt

    def create(**kwargs):
        sent.append(kwargs)
        delta = SimpleNamespace(content='ok', tool_calls=None)
        return iter([SimpleNamespace(choices=[SimpleNamespace(delta=delta)])])

    agent._Agent__openai_client = SimpleNamespace(
        build_messages=build_messages,
        sync_client=SimpleNamespace(chat=SimpleNamespace(
            completions=SimpleNamespace(create=create),
        )),
    )
    kwargs = {} if override == 'absent' else {'tools': None if override == 'none' else []}
    assert ''.join(agent._start_stream_impl('question', **kwargs)) == 'ok'
    assert len(sent) == 1
    system_prompt = sent[0]['messages'][0]['content']
    enabled = override != 'empty'
    assert ('configured_tool' in system_prompt) is enabled
    assert ('You have access to the following tools:' in system_prompt) is enabled
    assert bool(sent[0].get('tools')) is enabled


@pytest.mark.parametrize('failure', ['empty', 'create', 'iterator'])
def test_post_tool_answer_failure_does_not_replay_turn(failure):
    effects = []

    def counted_tool() -> str:
        """Record one local execution."""
        effects.append('executed')
        return 'local result'

    agent = Agent(instructions='Answer briefly', tools=[counted_tool], context=False)
    agent._using_custom_llm = False
    requests = []
    original = RuntimeError('answer generation failed')

    def build_messages(prompt, system_prompt=None, **kwargs):
        return [{'role': 'user', 'content': prompt}], prompt

    def broken_answer():
        yield SimpleNamespace(choices=[SimpleNamespace(
            delta=SimpleNamespace(content='partial answer', tool_calls=None),
        )])
        raise original

    def create(**kwargs):
        requests.append(kwargs)
        if len(requests) == 1:
            call = SimpleNamespace(index=0, id='call_local', function=SimpleNamespace(
                name='counted_tool', arguments='{}',
            ))
            delta = SimpleNamespace(content=None, tool_calls=[call])
            return iter([SimpleNamespace(choices=[SimpleNamespace(delta=delta)])])
        if failure == 'create':
            raise original
        return broken_answer() if failure == 'iterator' else iter([])

    agent._Agent__openai_client = SimpleNamespace(
        build_messages=build_messages,
        sync_client=SimpleNamespace(chat=SimpleNamespace(
            completions=SimpleNamespace(create=create),
        )),
    )
    fallback = []

    def chat(prompt, **kwargs):
        fallback.append(prompt)
        counted_tool()
        return 'replayed answer'

    agent.chat = chat
    try:
        error = None
        try:
            list(agent._start_stream_impl('Use the counted tool'))
        except RuntimeError as exc:
            error = exc
        assert effects == ['executed']
        assert fallback == []
        assert error is not None
        if failure != 'empty':
            assert error is original
        else:
            assert 'no answer' in str(error)
        assert len(requests) == 2
        assert requests[1].get('tools') is None
        assert any(m.get('tool_call_id') == 'call_local' for m in agent.chat_history)
    finally:
        agent.close()


def test_custom_stream_failure_after_tool_execution_does_not_replay(stream_agent):
    agent = stream_agent
    agent._using_custom_llm = True
    effects = []
    original = RuntimeError('answer generation failed')

    def stream(**kwargs):
        effects.append(kwargs['execute_tool_fn']('configured_tool', {}))
        raise original
        yield

    agent.llm_instance = SimpleNamespace(get_response_stream=stream)
    fallback = []
    agent.chat = lambda *args, **kwargs: fallback.append(args) or 'replayed'
    with pytest.raises(RuntimeError) as exc_info:
        list(agent._start_stream_impl('Use the tool'))
    assert exc_info.value is original
    assert effects == ['result']
    assert fallback == []
