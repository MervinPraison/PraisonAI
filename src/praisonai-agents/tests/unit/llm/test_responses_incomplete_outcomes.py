"""Incomplete Responses retain their terminal reason and streamed usage."""

from types import SimpleNamespace

import pytest
from openai.types.responses.response import IncompleteDetails

from praisonaiagents.llm.llm import LLM
from praisonaiagents.llm.openai_client import OpenAIClient


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['llm_sync', 'llm_async', 'llm_stream', 'llm_astream', 'client_sync', 'client_async'])
@pytest.mark.parametrize('shape', ['sdk', 'dict'])
@pytest.mark.parametrize('status,reason,expected_finish,expected_outcome', [
    ('incomplete', 'max_output_tokens', 'length', 'length_truncated'),
    ('incomplete', 'content_filter', 'content_filter', 'content_filtered'),
    ('completed', 'max_output_tokens', 'stop', 'completed'),
])
async def test_public_incomplete_responses(entry, shape, status, reason, expected_finish, expected_outcome, monkeypatch):
    details = IncompleteDetails(reason=reason)
    response = SimpleNamespace(
        status=status, incomplete_details=details if shape == 'sdk' else details.model_dump(),
        output=[{'type': 'message', 'content': [{'type': 'output_text', 'text': 'partial'}]}],
        usage=SimpleNamespace(input_tokens=3, output_tokens=2, total_tokens=5),
    )
    requests = []
    tracked = []

    def respond(**kwargs):
        requests.append(kwargs)
        return response

    async def arespond(**kwargs):
        return respond(**kwargs)

    if entry.startswith('llm'):
        llm = LLM(model='gpt-4o-mini')
        llm._call_responses_api = respond
        llm._call_responses_api_async = arespond
        monkeypatch.setattr(llm, '_track_token_usage', lambda result, model: tracked.append(result))
        if entry in ('llm_stream', 'llm_astream'):
            import litellm
            monkeypatch.setattr('praisonaiagents.llm.llm.check_model_request', lambda *args: None)
            events = [
                {'type': 'response.output_text.delta', 'delta': 'partial'},
                {'type': 'response.' + status, 'response': response},
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
        kwargs = dict(stream=entry in ('llm_stream', 'llm_astream'), verbose=False)
        answer = await llm.get_response_async('question', **kwargs) if entry in ('llm_async', 'llm_astream') else llm.get_response('question', **kwargs)
        assert answer == 'partial'
        assert llm._last_stop_reason == expected_outcome
        if entry in ('llm_stream', 'llm_astream'):
            assert response in tracked
    else:
        client = OpenAIClient(api_key='sk-test-not-real')
        client._sync_client = SimpleNamespace(responses=SimpleNamespace(create=respond))
        client._async_client = SimpleNamespace(responses=SimpleNamespace(create=arespond))
        messages = [{'role': 'user', 'content': 'question'}]
        answer = client.create_completion(messages) if entry == 'client_sync' else await client.acreate_completion(messages)
        assert answer.choices[0].message.content == 'partial'
        assert answer.choices[0].finish_reason == expected_finish
        assert answer.usage.total_tokens == 5
    assert len(requests) == 1


@pytest.mark.parametrize('reason', ['max_output_tokens', 'content_filter'])
@pytest.mark.parametrize('existing', ['max_steps', 'cancelled'])
def test_incomplete_response_preserves_stronger_terminal_reason(reason, existing):
    llm = LLM(model='gpt-4o-mini')
    llm._last_stop_reason = existing
    llm._extract_from_responses_output(SimpleNamespace(
        status='incomplete', incomplete_details=IncompleteDetails(reason=reason), output=[],
    ))
    assert llm._last_stop_reason == existing


@pytest.mark.parametrize('reason', [None, 'unknown_future_reason'])
def test_unrecognised_incomplete_reason_preserves_existing_behavior(reason):
    llm = LLM(model='gpt-4o-mini')
    llm._extract_from_responses_output(SimpleNamespace(
        status='incomplete', incomplete_details={'reason': reason}, output=[],
    ))
    assert llm._last_stop_reason == 'completed'
