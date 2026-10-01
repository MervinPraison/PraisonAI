"""A stream fallback must preserve the provider retry replay policy."""

from types import SimpleNamespace

import pytest
from praisonaiagents.agent.chat_mixin import ChatMixin
from praisonaiagents.llm.llm import LLM


class ReadTimeout(Exception):
    pass


class ConnectTimeout(Exception):
    pass


@pytest.mark.parametrize("stage", ["request", "iterator", "wrapped_iterator"])
@pytest.mark.parametrize("tool_turn", [False, True])
@pytest.mark.parametrize("error_type", [ReadTimeout, ConnectTimeout])
def test_llm_stream_fallback_keeps_replay_gate(stage, tool_turn, error_type):
    llm = LLM(model="fake")
    llm._max_retries = 0
    llm._build_messages = lambda **kw: ([], kw['prompt'])
    llm._format_tools_for_litellm = lambda tools: tools
    llm._supports_streaming_tools = lambda: True
    llm._build_completion_params = lambda **kw: kw
    calls = []
    original = error_type('transport timeout')

    def failed_stream():
        if stage == 'wrapped_iterator':
            raise RuntimeError('decode failure') from original
        raise original
        yield  # Make failure happen during iteration.

    def completion(**kw):
        calls.append(kw['stream'])
        if kw['stream']:
            if stage == 'request':
                raise original
            return failed_stream()
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content='fallback answer', tool_calls=None),
        )])

    # Retain the actual retry driver; replace only the network function.
    llm._completion_with_retry = lambda **kw: llm._call_with_retry(completion, **kw)
    tools = [{'type': 'function'}] if tool_turn else []
    stream = llm.get_response_stream('question', tools=tools)
    if tool_turn and error_type is ReadTimeout:
        # The gate may surface the original timeout or a streaming-handler
        # wrapper around it; the contract is that the turn is NOT replayed
        # (only one streaming attempt, no non-streaming reissue).
        with pytest.raises(Exception):  # noqa: B017 - wrapper type varies by path
            list(stream)
        assert calls == [True]
    else:
        assert list(stream) == ['fallback answer']
        assert calls == [True, False]


class FallbackHost(ChatMixin):
    def __init__(self, tools):
        self.tools = tools
        self.calls = 0

    def chat(self, prompt, **kwargs):
        self.calls += 1
        return 'fallback answer'


@pytest.mark.parametrize('tool_source', ['instance', 'request'])
def test_host_fallback_does_not_replay_tool_turn(tool_source):
    host = FallbackHost(['tool'] if tool_source == 'instance' else [])
    kwargs = {'tools': ['tool']} if tool_source == 'request' else {}
    original = ReadTimeout('read timeout after request')
    with pytest.raises(ReadTimeout) as exc_info:
        host._stream_fallback_chat('question', kwargs, original)
    assert exc_info.value is original
    assert host.calls == 0


@pytest.mark.parametrize('error', [ReadTimeout('read timeout'), ConnectTimeout('connect timeout')])
def test_host_preserves_toolless_or_predispatch_fallback(error):
    # Tool-less host (no instance tools): a post-dispatch ReadTimeout is safe to
    # replay; a pre-dispatch ConnectTimeout is always safe.
    host = FallbackHost([])
    assert host._stream_fallback_chat('question', {}, error) == 'fallback answer'
    assert host.calls == 1


def test_host_empty_override_falls_back_to_instance_tools():
    # The native streaming path resolves an explicit empty ``tools=[]`` override
    # back to ``self.tools`` and sends them, so a post-dispatch ReadTimeout is
    # replay-unsafe and must surface rather than reissue the tool turn.
    host = FallbackHost(['tool'])
    original = ReadTimeout('read timeout after request')
    with pytest.raises(ReadTimeout) as exc_info:
        host._stream_fallback_chat('question', {'tools': []}, original)
    assert exc_info.value is original
    assert host.calls == 0


def test_host_keeps_wrapped_provider_failure():
    host = FallbackHost(['tool'])
    original = ReadTimeout('transport timeout')
    wrapper = RuntimeError('stream iteration failed')
    wrapper.__cause__ = original
    with pytest.raises(RuntimeError) as exc_info:
        host._stream_fallback_chat('question', {}, wrapper)
    assert exc_info.value is wrapper
    assert exc_info.value.__cause__ is original
    assert host.calls == 0


def test_exception_chain_cycle_does_not_prevent_safe_fallback():
    host = FallbackHost(['tool'])
    first = RuntimeError('unsupported streaming')
    second = RuntimeError('adapter failure')
    first.__cause__ = second
    second.__cause__ = first
    assert host._stream_fallback_chat('question', {}, first) == 'fallback answer'
    assert host.calls == 1
