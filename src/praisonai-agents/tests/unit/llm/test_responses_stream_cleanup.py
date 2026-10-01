"""Responses streams release their transport on every consumer exit."""

import asyncio

import httpx
import pytest

from praisonaiagents.llm.llm import LLM, LLMResponseError


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['sync', 'async'])
@pytest.mark.parametrize('shape', ['direct', 'litellm'])
@pytest.mark.parametrize('exit_kind', ['completed', 'failed', 'callback', 'cancelled'])
async def test_responses_stream_releases_transport(mode, shape, exit_kind, monkeypatch):
    import litellm
    if mode == 'sync' and exit_kind == 'cancelled':
        pytest.skip('Task cancellation is an asynchronous exit')
    closed = []

    class SyncTransport(httpx.SyncByteStream):
        def __iter__(self):
            return iter([])

        def close(self):
            closed.append('closed')

    class AsyncTransport(httpx.AsyncByteStream):
        async def __aiter__(self):
            if False:
                yield b''

        async def aclose(self):
            closed.append('closed')

    response = httpx.Response(200, stream=SyncTransport() if mode == 'sync' else AsyncTransport())
    event = {'type': 'response.output_text.delta', 'delta': 'answer'}
    if exit_kind == 'failed':
        event = {'type': 'response.failed', 'response': {'error': {'code': 'server_error', 'message': 'Provider failed.'}}}

    class Stream:
        def __init__(self):
            self.events = iter([event])
            if shape == 'litellm':
                self.response = response
            elif mode == 'sync':
                self.close = response.close
            else:
                self.aclose = response.aclose

        def __iter__(self):
            return self

        def __next__(self):
            return next(self.events)

        def __aiter__(self):
            return self

        async def __anext__(self):
            if exit_kind == 'cancelled':
                raise asyncio.CancelledError()
            try:
                return next(self.events)
            except StopIteration:
                raise StopAsyncIteration

    stream = Stream()
    monkeypatch.setattr('praisonaiagents.llm.llm.check_model_request', lambda *args: None)
    monkeypatch.setattr(litellm, 'responses', lambda **kwargs: stream)

    async def arespond(**kwargs):
        return stream

    monkeypatch.setattr(litellm, 'aresponses', arespond)
    llm = LLM(model='gpt-4o-mini')

    def callback(event):
        if exit_kind == 'callback':
            raise ValueError('Callback failed.')

    async def invoke():
        kwargs = dict(stream_callback=callback, emit_events=True)
        if mode == 'sync':
            return llm._stream_responses_api({'model': llm.model}, **kwargs)
        return await llm._stream_responses_api_async({'model': llm.model}, **kwargs)

    if exit_kind == 'failed':
        with pytest.raises(LLMResponseError, match='Provider failed.'):
            await invoke()
    elif exit_kind == 'callback':
        with pytest.raises(ValueError, match='Callback failed.'):
            await invoke()
    elif exit_kind == 'cancelled':
        with pytest.raises(asyncio.CancelledError):
            await invoke()
    else:
        assert (await invoke())[0] == 'answer'
    assert response.is_closed
    assert closed == ['closed']


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['sync', 'async'])
async def test_cleanup_error_does_not_mask_provider_failure(mode, monkeypatch):
    import litellm
    event = {'type': 'error', 'message': 'Original failure.'}

    def fail_close():
        raise ValueError('Cleanup failed.')

    async def fail_aclose():
        fail_close()

    class AsyncStream:
        aclose = staticmethod(fail_aclose)

        def __aiter__(self):
            async def events():
                yield event
            return events()

    monkeypatch.setattr('praisonaiagents.llm.llm.check_model_request', lambda *args: None)
    class SyncStream:
        close = staticmethod(fail_close)

        def __iter__(self):
            return iter([event])

    monkeypatch.setattr(litellm, 'responses', lambda **kwargs: SyncStream())

    async def arespond(**kwargs):
        return AsyncStream()

    monkeypatch.setattr(litellm, 'aresponses', arespond)
    llm = LLM(model='gpt-4o-mini')
    with pytest.raises(LLMResponseError, match='Original failure.'):
        if mode == 'sync':
            llm._stream_responses_api({'model': llm.model})
        else:
            await llm._stream_responses_api_async({'model': llm.model})
