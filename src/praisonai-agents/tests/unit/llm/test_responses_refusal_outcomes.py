"""Responses refusals retain their provider signal across public call paths."""

from types import SimpleNamespace

import pytest
from openai.types.responses import ResponseOutputMessage, ResponseOutputRefusal, ResponseOutputText

from praisonaiagents.llm.llm import LLM
from praisonaiagents.llm.openai_client import OpenAIClient


def output_response(shape, profile):
    blocks = []
    if profile != 'refusal':
        blocks.append(ResponseOutputText(type='output_text', text='answer', annotations=[]))
    if profile != 'normal':
        blocks.append(ResponseOutputRefusal(type='refusal', refusal='Cannot comply.'))
    message = ResponseOutputMessage(id='msg_test', type='message', role='assistant', status='completed', content=blocks)
    return SimpleNamespace(output=[message if shape == 'sdk' else message.model_dump()])


@pytest.mark.asyncio
@pytest.mark.parametrize('entry', ['llm_sync', 'llm_async', 'llm_stream', 'llm_astream', 'client_sync', 'client_async'])
@pytest.mark.parametrize('shape', ['sdk', 'dict'])
@pytest.mark.parametrize('profile', ['refusal', 'mixed', 'normal'])
async def test_public_responses_refusal_signal(entry, shape, profile, monkeypatch):
    response = output_response(shape, profile)
    requests = []

    def respond(**kwargs):
        requests.append(kwargs)
        return response

    async def arespond(**kwargs):
        return respond(**kwargs)

    expected_text = '' if profile == 'refusal' else 'answer'
    if entry.startswith('llm'):
        llm = LLM(model='gpt-4o-mini')
        llm._call_responses_api = respond
        llm._call_responses_api_async = arespond
        if entry in ('llm_stream', 'llm_astream'):
            import litellm
            monkeypatch.setattr('praisonaiagents.llm.llm.check_model_request', lambda *args: None)
            events = []
            if expected_text:
                events.append({'type': 'response.output_text.delta', 'delta': expected_text})
            events.append({'type': 'response.completed', 'response': response})
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
        assert answer == expected_text
        assert llm._last_stop_reason == ('completed' if profile == 'normal' else 'refused')
    else:
        client = OpenAIClient(api_key='sk-test-not-real')
        client._sync_client = SimpleNamespace(responses=SimpleNamespace(create=respond))
        client._async_client = SimpleNamespace(responses=SimpleNamespace(create=arespond))
        messages = [{'role': 'user', 'content': 'question'}]
        answer = client.create_completion(messages) if entry == 'client_sync' else await client.acreate_completion(messages)
        assert answer.choices[0].message.content == (expected_text or None)
        assert answer.choices[0].message.refusal == (None if profile == 'normal' else 'Cannot comply.')
    assert len(requests) == 1


@pytest.mark.parametrize('reason', ['max_steps', 'cancelled'])
def test_refusal_does_not_downgrade_existing_terminal_reason(reason):
    llm = LLM(model='gpt-4o-mini')
    llm._last_stop_reason = reason
    llm._extract_from_responses_output(output_response('sdk', 'refusal'))
    assert llm._last_stop_reason == reason


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['sync', 'async'])
@pytest.mark.parametrize('shape', ['sdk', 'dict'])
async def test_public_refusal_delta_without_completed_event(mode, shape, monkeypatch):
    import litellm
    llm = LLM(model='gpt-4o-mini')
    monkeypatch.setattr('praisonaiagents.llm.llm.check_model_request', lambda *args: None)
    event = {'type': 'response.refusal.delta', 'delta': 'Cannot comply.'}
    if shape == 'sdk':
        event = SimpleNamespace(**event)

    def stream(**kwargs):
        return iter([event])

    async def astream(**kwargs):
        async def iterate():
            yield event
        return iterate()

    monkeypatch.setattr(litellm, 'responses', stream)
    monkeypatch.setattr(litellm, 'aresponses', astream)
    kwargs = dict(stream=True, verbose=False)
    answer = llm.get_response('question', **kwargs) if mode == 'sync' else await llm.get_response_async('question', **kwargs)
    assert answer == ''
    assert llm._last_stop_reason == 'refused'


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['sync', 'async'])
async def test_following_normal_turn_clears_refusal(mode):
    llm = LLM(model='gpt-4o-mini')
    responses = iter([output_response('sdk', 'refusal'), output_response('sdk', 'normal')])

    def respond(**kwargs):
        return next(responses)

    async def arespond(**kwargs):
        return respond(**kwargs)

    llm._call_responses_api = respond
    llm._call_responses_api_async = arespond
    for expected_text, expected_reason in [('', 'refused'), ('answer', 'completed')]:
        kwargs = dict(stream=False, verbose=False)
        answer = llm.get_response('question', **kwargs) if mode == 'sync' else await llm.get_response_async('question', **kwargs)
        assert answer == expected_text
        assert llm._last_stop_reason == expected_reason
