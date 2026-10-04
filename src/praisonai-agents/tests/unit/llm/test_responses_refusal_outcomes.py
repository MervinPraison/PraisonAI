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


@pytest.mark.asyncio
@pytest.mark.parametrize("profile, expected_reason", [
    ("refusal", "refused"),
    ("max_output_tokens", "length_truncated"),
    ("content_filter", "content_filtered"),
])
@pytest.mark.parametrize("interleaving", ["after_return", "overlapping_provider"])
async def test_shared_llm_keeps_each_tasks_responses_outcome(profile, expected_reason, interleaving):
    import asyncio

    llm = LLM(model='gpt-4o-mini')
    terminal_returned = asyncio.Event()
    normal_dispatched = asyncio.Event()
    normal_returned = asyncio.Event()
    terminal = output_response('sdk', 'refusal')
    if profile != "refusal":
        terminal.status = 'incomplete'
        terminal.incomplete_details = SimpleNamespace(reason=profile)
    normal = output_response('sdk', 'normal')

    async def respond(**kwargs):
        if asyncio.current_task().get_name() == "terminal-request":
            if interleaving == "overlapping_provider":
                await normal_dispatched.wait()
            return terminal
        normal_dispatched.set()
        if interleaving == "overlapping_provider":
            await terminal_returned.wait()
        return normal

    llm._call_responses_api_async = respond

    async def terminal_call():
        answer = await llm.get_response_async('terminal', stream=False, verbose=False)
        terminal_returned.set()
        await normal_returned.wait()
        return answer, llm._last_stop_reason

    async def normal_call():
        if interleaving == "after_return":
            await terminal_returned.wait()
        answer = await llm.get_response_async('normal', stream=False, verbose=False)
        normal_returned.set()
        return answer, llm._last_stop_reason

    terminal_task = asyncio.create_task(terminal_call(), name="terminal-request")
    normal_task = asyncio.create_task(normal_call(), name="normal-request")
    terminal_result, normal_result = await asyncio.wait_for(
        asyncio.gather(terminal_task, normal_task), timeout=10)
    assert terminal_result == ('', expected_reason)
    assert normal_result == ('answer', 'completed')


def test_copied_llm_has_an_independent_terminal_outcome():
    import copy

    original = LLM(model='gpt-4o-mini')
    original._last_stop_reason = 'refused'
    clone = copy.deepcopy(original)
    assert clone._last_stop_reason == 'completed'
    clone._last_stop_reason = 'content_filtered'
    assert original._last_stop_reason == 'refused'
    assert clone._last_stop_reason == 'content_filtered'


def test_response_outcome_remains_visible_after_asyncio_run():
    import asyncio

    llm = LLM(model='gpt-4o-mini')

    async def respond(**kwargs):
        return output_response('sdk', 'refusal')

    llm._call_responses_api_async = respond
    assert asyncio.run(llm.get_response_async('question', stream=False, verbose=False)) == ''
    assert llm._last_stop_reason == 'refused'


@pytest.mark.parametrize("profile, expected_reason", [
    ("refusal", "refused"),
    ("max_output_tokens", "length_truncated"),
    ("content_filter", "content_filtered"),
])
def test_shared_llm_keeps_each_threads_responses_outcome(profile, expected_reason):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    llm = LLM(model='gpt-4o-mini')
    terminal_returned = threading.Event()
    normal_returned = threading.Event()
    terminal = output_response('sdk', 'refusal')
    if profile != "refusal":
        terminal.status = 'incomplete'
        terminal.incomplete_details = SimpleNamespace(reason=profile)

    def respond(**kwargs):
        return terminal if threading.current_thread().name.startswith("terminal") else output_response('sdk', 'normal')

    llm._call_responses_api = respond

    def terminal_call():
        answer = llm.get_response('terminal', stream=False, verbose=False)
        terminal_returned.set()
        assert normal_returned.wait(10)
        return answer, llm._last_stop_reason

    def normal_call():
        assert terminal_returned.wait(10)
        answer = llm.get_response('normal', stream=False, verbose=False)
        normal_returned.set()
        return answer, llm._last_stop_reason

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="terminal") as terminals, ThreadPoolExecutor(max_workers=1, thread_name_prefix="normal") as normals:
        terminal_task = terminals.submit(terminal_call)
        normal_task = normals.submit(normal_call)
        assert terminal_task.result(timeout=15) == ('', expected_reason)
        assert normal_task.result(timeout=15) == ('answer', 'completed')
    # Observers outside either request retain the latest completed result.
    assert llm._last_stop_reason == 'completed'


@pytest.mark.parametrize("first_profile, first_reason", [
    ("refusal", "refused"),
    ("max_output_tokens", "length_truncated"),
    ("content_filter", "content_filtered"),
])
@pytest.mark.parametrize("second_profile, second_reason", [
    ("normal", "completed"),
    ("refusal", "refused"),
])
def test_later_async_turn_replaces_a_sync_contexts_last_outcome(first_profile, first_reason, second_profile, second_reason):
    import asyncio

    llm = LLM(model='gpt-4o-mini')
    first = output_response('sdk', 'refusal')
    if first_profile != "refusal":
        first.status = 'incomplete'
        first.incomplete_details = SimpleNamespace(reason=first_profile)

    def respond(**kwargs):
        return first

    async def arespond(**kwargs):
        return output_response('sdk', second_profile)

    llm._call_responses_api = respond
    llm._call_responses_api_async = arespond
    assert llm.get_response('first', stream=False, verbose=False) == ''
    assert llm._last_stop_reason == first_reason
    answer = asyncio.run(llm.get_response_async('second', stream=False, verbose=False))
    assert answer == ('answer' if second_profile == "normal" else '')
    assert llm._last_stop_reason == second_reason


@pytest.mark.parametrize('outer_mode', ['sync', 'async'])
@pytest.mark.parametrize('inner_mode', ['sync', 'async'])
@pytest.mark.parametrize('outer_profile, expected_reason', [
    ('normal', 'completed'),
    ('max_output_tokens', 'length_truncated'),
    ('content_filter', 'content_filtered'),
])
@pytest.mark.parametrize('inner_profile', ['normal', 'refusal'])
@pytest.mark.parametrize('stream', [False, True])
def test_nested_tool_request_preserves_the_outer_responses_outcome(
    outer_mode, inner_mode, outer_profile, expected_reason, inner_profile,
    stream, monkeypatch,
):
    import asyncio
    import litellm

    llm = LLM(model='gpt-4o-mini')
    first = output_response('sdk', 'normal')
    first.output = []
    first.output.append(SimpleNamespace(
        type='function_call', id='fc_nested', call_id='call_nested',
        name='lookup', arguments='{}',
    ))
    if outer_profile != 'normal':
        first.status = 'incomplete'
        first.incomplete_details = SimpleNamespace(reason=outer_profile)
    outer_responses = iter([first, output_response('sdk', 'normal')])
    in_tool = False
    inner_answers = []

    def respond(**kwargs):
        if in_tool:
            return output_response('sdk', inner_profile)
        return next(outer_responses)

    async def arespond(**kwargs):
        return respond(**kwargs)

    def stream_response(**kwargs):
        response = respond(**kwargs)
        events = []
        if response is first:
            events.append({'type': 'response.output_item.done',
                           'output_index': 0, 'item': first.output[0]})
        else:
            events.append({'type': 'response.output_text.delta', 'delta': 'answer'})
        events.append({'type': 'response.incomplete' if response is first
                       and outer_profile != 'normal' else 'response.completed',
                       'response': response})
        return iter(events)

    async def astream_response(**kwargs):
        async def iterate():
            for event in stream_response(**kwargs):
                yield event
        return iterate()

    def execute(name, arguments, *args, **kwargs):
        nonlocal in_tool
        assert name == 'lookup'
        in_tool = True
        try:
            if inner_mode == 'async':
                answer = asyncio.run(llm.get_response_async(
                    'inner', stream=False, verbose=False))
            else:
                answer = llm.get_response('inner', stream=False, verbose=False)
            inner_answers.append(answer)
        finally:
            in_tool = False
        return 'lookup result'

    async def aexecute(name, arguments, **kwargs):
        nonlocal in_tool
        assert name == 'lookup'
        in_tool = True
        try:
            if inner_mode == 'async':
                answer = await llm.get_response_async(
                    'inner', stream=False, verbose=False)
            else:
                answer = llm.get_response('inner', stream=False, verbose=False)
            inner_answers.append(answer)
        finally:
            in_tool = False
        return 'lookup result'

    llm._call_responses_api = respond
    llm._call_responses_api_async = arespond
    monkeypatch.setattr('praisonaiagents.llm.llm.check_model_request', lambda *args: None)
    monkeypatch.setattr(litellm, 'responses', stream_response)
    monkeypatch.setattr(litellm, 'aresponses', astream_response)
    if outer_mode == 'async':
        answer = asyncio.run(llm.get_response_async(
            'outer', stream=stream, verbose=False, execute_tool_fn=aexecute))
    else:
        answer = llm.get_response(
            'outer', stream=stream, verbose=False, execute_tool_fn=execute)
    assert answer == 'answer'
    assert inner_answers == ['answer' if inner_profile == 'normal' else '']
    assert llm._last_stop_reason == expected_reason
