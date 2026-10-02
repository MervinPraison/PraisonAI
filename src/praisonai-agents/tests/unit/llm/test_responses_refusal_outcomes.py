"""Responses refusals retain their provider signal across public call paths."""

from types import SimpleNamespace

import pytest
from openai.types.responses import ResponseOutputMessage, ResponseOutputRefusal, ResponseOutputText

from praisonaiagents.llm.llm import LLM
from praisonaiagents.llm.openai_client import OpenAIClient


@pytest.fixture(autouse=True)
def isolate_responses_endpoint(monkeypatch):
    """Fake Responses clients must not inherit a configured chat endpoint."""
    monkeypatch.delenv('OPENAI_API_BASE', raising=False)
    monkeypatch.delenv('OPENAI_BASE_URL', raising=False)


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
@pytest.mark.parametrize('incomplete_reason', [None, 'max_output_tokens', 'content_filter'])
def test_refusal_does_not_downgrade_existing_terminal_reason(reason, incomplete_reason):
    llm = LLM(model='gpt-4o-mini')
    llm._last_stop_reason = reason
    response = output_response('sdk', 'refusal')
    if incomplete_reason:
        response.status = 'incomplete'
        response.incomplete_details = SimpleNamespace(reason=incomplete_reason)
    llm._extract_from_responses_output(response)
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


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['sync', 'async'])
@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize('shape', ['sdk', 'dict'])
@pytest.mark.parametrize('final_profile', ['normal', 'refusal'])
@pytest.mark.parametrize('incomplete_reason', [None, 'max_output_tokens', 'content_filter', 'unknown'])
async def test_tool_continuation_uses_final_response_refusal(mode, stream, shape, final_profile, incomplete_reason, monkeypatch):
    import litellm

    llm = LLM(model='gpt-4o-mini')
    tool = {'type': 'function_call', 'id': 'fc_test', 'call_id': 'call_test',
            'name': 'lookup', 'arguments': '{}'}
    tool_item = SimpleNamespace(**tool) if shape == 'sdk' else tool
    first = output_response(shape, 'refusal')
    first.output.append(tool_item)
    if incomplete_reason:
        first.status = 'incomplete'
        first.incomplete_details = SimpleNamespace(reason=incomplete_reason)
        if shape == 'dict':
            first = {'output': first.output, 'status': first.status,
                     'incomplete_details': {'reason': incomplete_reason}}
    final = output_response(shape, final_profile)
    responses = iter([first, final])
    requests = []
    dispatched = []
    monkeypatch.setattr('praisonaiagents.llm.llm.check_model_request', lambda *args: None)

    def respond(**kwargs):
        requests.append(kwargs)
        return next(responses)

    async def arespond(**kwargs):
        return respond(**kwargs)

    def events(**kwargs):
        response = respond(**kwargs)
        result = []
        if response is first or final_profile == 'refusal':
            result.append({'type': 'response.refusal.delta', 'delta': 'Cannot comply.'})
        else:
            result.append({'type': 'response.output_text.delta', 'delta': 'answer'})
        if response is first:
            result.append({'type': 'response.output_item.done', 'output_index': 1, 'item': tool_item})
        event_type = 'response.incomplete' if response is first and incomplete_reason else 'response.completed'
        result.append({'type': event_type, 'response': response})
        return [SimpleNamespace(**event) for event in result] if shape == 'sdk' else result

    def stream_response(**kwargs):
        return iter(events(**kwargs))

    async def astream_response(**kwargs):
        batch = events(**kwargs)

        async def iterate():
            for event in batch:
                yield event

        return iterate()

    def execute(name, arguments, *args, **kwargs):
        dispatched.append((name, arguments))
        return 'lookup result'

    llm._call_responses_api = respond
    llm._call_responses_api_async = arespond
    monkeypatch.setattr(litellm, 'responses', stream_response)
    monkeypatch.setattr(litellm, 'aresponses', astream_response)
    kwargs = dict(stream=stream, verbose=False, execute_tool_fn=execute)
    answer = llm.get_response('question', **kwargs) if mode == 'sync' else await llm.get_response_async('question', **kwargs)
    assert answer == ('answer' if final_profile == 'normal' else '')
    assert dispatched == [('lookup', {})]
    assert len(requests) == 2
    assert any(item.get('type') == 'function_call_output' for item in requests[1]['input'])
    expected_reason = {'max_output_tokens': 'length_truncated', 'content_filter': 'content_filtered'}.get(incomplete_reason)
    assert llm._last_stop_reason == (expected_reason or ('completed' if final_profile == 'normal' else 'refused'))
