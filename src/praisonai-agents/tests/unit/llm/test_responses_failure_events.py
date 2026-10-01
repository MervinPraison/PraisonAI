"""Provider failures cannot become successful Responses answers."""

from types import SimpleNamespace

import pytest
from openai.types.responses import ResponseError

from praisonaiagents.llm.llm import LLM, LLMResponseError


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['sync', 'async', 'stream', 'astream'])
@pytest.mark.parametrize('shape', ['sdk', 'dict'])
@pytest.mark.parametrize('profile', ['failed', 'missing_error', 'completed'])
async def test_public_responses_failure(entry, shape, profile, monkeypatch):
    error = ResponseError(code='server_error', message='Provider failed.') if profile == 'failed' else None
    response = SimpleNamespace(
        status='completed' if profile == 'completed' else 'failed',
        error=error if shape == 'sdk' or error is None else error.model_dump(),
        output=[{'type': 'message', 'content': [{'type': 'output_text', 'text': 'partial'}]}],
    )
    llm = LLM(model='gpt-4o-mini')
    requests = []

    def respond(**kwargs):
        requests.append(kwargs)
        return response

    async def arespond(**kwargs):
        return respond(**kwargs)

    llm._call_responses_api = respond
    llm._call_responses_api_async = arespond
    if entry in ('stream', 'astream'):
        import litellm
        monkeypatch.setattr('praisonaiagents.llm.llm.check_model_request', lambda *args: None)
        events = [
            {'type': 'response.output_text.delta', 'delta': 'partial'},
            {'type': 'response.' + response.status, 'response': response},
        ]
        if shape == 'sdk':
            events = [SimpleNamespace(**event) for event in events]

        def stream(**kwargs):
            requests.append(kwargs)
            return iter(events)

        async def astream(**kwargs):
            requests.append(kwargs)

            async def iterate():
                for event in events:
                    yield event

            return iterate()

        monkeypatch.setattr(litellm, 'responses', stream)
        monkeypatch.setattr(litellm, 'aresponses', astream)

    async def invoke():
        kwargs = dict(stream=entry in ('stream', 'astream'), verbose=False)
        return await llm.get_response_async('question', **kwargs) if entry in ('async', 'astream') else llm.get_response('question', **kwargs)

    if profile == 'completed':
        assert await invoke() == 'partial'
        assert llm._last_stop_reason == 'completed'
    else:
        with pytest.raises(LLMResponseError, match='Responses API failed') as caught:
            await invoke()
        assert llm._last_stop_reason == 'error'
        if error:
            assert 'server_error' in str(caught.value)
            assert 'Provider failed.' in str(caught.value)
    assert len(requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['sync', 'async'])
@pytest.mark.parametrize('shape', ['sdk', 'dict'])
async def test_stream_error_event_prevents_pending_tool_execution(mode, shape, monkeypatch):
    import litellm
    llm = LLM(model='gpt-4o-mini')
    effects = []
    requests = []

    def lookup() -> str:
        """Return a lookup result."""
        effects.append('executed')
        return 'found'

    events = [
        {'type': 'response.output_item.done', 'output_index': 0, 'item': {
            'type': 'function_call', 'call_id': 'call_1', 'name': 'lookup', 'arguments': '{}',
        }},
        {'type': 'error', 'code': 'server_error', 'message': 'Stream failed.'},
    ]
    if shape == 'sdk':
        events = [SimpleNamespace(**event) for event in events]
    monkeypatch.setattr('praisonaiagents.llm.llm.check_model_request', lambda *args: None)

    def stream(**kwargs):
        requests.append(kwargs)
        return iter(events)

    async def astream(**kwargs):
        requests.append(kwargs)

        async def iterate():
            for event in events:
                yield event

        return iterate()

    monkeypatch.setattr(litellm, 'responses', stream)
    monkeypatch.setattr(litellm, 'aresponses', astream)
    with pytest.raises(LLMResponseError, match='Stream failed.'):
        kwargs = dict(stream=True, verbose=False, tools=[lookup], max_iterations=1)
        if mode == 'sync':
            llm.get_response('question', **kwargs)
        else:
            await llm.get_response_async('question', **kwargs)
    assert effects == []
    assert len(requests) == 1
