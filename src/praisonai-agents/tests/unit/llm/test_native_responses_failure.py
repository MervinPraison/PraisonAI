"""Native failed Responses must surface without a second provider request."""

from types import SimpleNamespace

import pytest
from openai.types.responses import ResponseError
from openai.types.chat import ChatCompletionChunk

from praisonaiagents.llm.llm import LLMResponseError
from praisonaiagents.llm.openai_client import OpenAIClient


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['sync', 'async', 'sync_stream', 'async_stream'])
@pytest.mark.parametrize('shape', ['sdk', 'dict'])
@pytest.mark.parametrize('profile', ['failed', 'missing_error', 'completed', 'unsupported'])
async def test_native_responses_failure_and_compatibility_fallback(mode, shape, profile, monkeypatch):
    monkeypatch.delenv('OPENAI_API_BASE', raising=False)
    monkeypatch.delenv('OPENAI_BASE_URL', raising=False)
    calls = []
    error = ResponseError(code='server_error', message='Provider failed.') if profile == 'failed' else None
    fields = {
        'status': 'failed' if profile in ('failed', 'missing_error') else 'completed',
        'error': error if shape == 'sdk' or error is None else error.model_dump(),
        'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'answer'}]}],
        'usage': {'input_tokens': 3, 'output_tokens': 2, 'total_tokens': 5},
    }
    if shape == 'sdk':
        fields['usage'] = SimpleNamespace(**fields['usage'])
    raw = SimpleNamespace(**fields) if shape == 'sdk' else fields

    def respond(**kwargs):
        calls.append('responses')
        if profile == 'unsupported':
            raise NotImplementedError('Responses unsupported')
        return raw

    async def arespond(**kwargs):
        return respond(**kwargs)

    fallback = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='fallback'))])

    def chat(**kwargs):
        calls.append('chat')
        if kwargs.get('stream'):
            return iter([ChatCompletionChunk(
                id='chat-test', object='chat.completion.chunk', created=0, model='gpt-4o-mini',
                choices=[{'index': 0, 'delta': {'content': 'fallback'}, 'finish_reason': 'stop'}],
            )])
        return fallback

    async def achat(**kwargs):
        result = chat(**kwargs)
        if kwargs.get('stream'):
            async def chunks():
                for chunk in result:
                    yield chunk
            return chunks()
        return result

    client = OpenAIClient(api_key='sk-test-not-real')
    client._sync_client = SimpleNamespace(
        responses=SimpleNamespace(create=respond), chat=SimpleNamespace(completions=SimpleNamespace(create=chat)),
    )
    client._async_client = SimpleNamespace(
        responses=SimpleNamespace(create=arespond), chat=SimpleNamespace(completions=SimpleNamespace(create=achat)),
    )

    async def invoke():
        messages = [{'role': 'user', 'content': 'question'}]
        if mode == 'sync_stream':
            return client.process_stream_response(messages, model='gpt-4o-mini')
        if mode == 'async_stream':
            return await client.process_stream_response_async(messages, model='gpt-4o-mini')
        return client.create_completion(messages) if mode == 'sync' else await client.acreate_completion(messages)

    if profile in ('failed', 'missing_error'):
        with pytest.raises(LLMResponseError, match='Responses API failed') as caught:
            await invoke()
        if error:
            assert 'server_error' in str(caught.value)
            assert 'Provider failed.' in str(caught.value)
        assert calls == ['responses']
    else:
        result = await invoke()
        assert result.choices[0].message.content == ('fallback' if profile == 'unsupported' else 'answer')
        assert calls == (['responses', 'chat'] if profile == 'unsupported' else ['responses'])
        if profile == 'completed':
            assert result.usage is not None
            assert result.usage.prompt_tokens == 3
            assert result.usage.completion_tokens == 2
            assert result.usage.total_tokens == 5
