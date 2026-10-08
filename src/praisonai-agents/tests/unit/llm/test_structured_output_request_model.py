"""Native structured output follows the model in the outgoing request."""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from praisonaiagents.llm.llm import LLM


class Answer(BaseModel):
    answer: str


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['sync', 'async'])
@pytest.mark.parametrize('schema_kind', ['pydantic', 'dict'])
@pytest.mark.parametrize('configured,requested,format_kind', [
    ('gpt-4o-mini', 'gemini/gemini-2.5-flash', 'gemini'),
    ('gemini/gemini-2.5-flash', 'gpt-4o-mini', 'openai'),
    ('gpt-3.5-turbo', 'gpt-4o-mini', 'openai'),
    ('gpt-4o-mini', 'gpt-3.5-turbo', None),
    ('gpt-4o-mini', 'gpt-4o-mini', 'openai'),
    ('gemini/gemini-2.5-flash', 'gemini/gemini-2.5-flash', 'gemini'),
])
async def test_public_structured_output_uses_request_model(mode, schema_kind, configured, requested, format_kind):
    llm = LLM(model=configured)
    requests = []

    def complete(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"answer":"ok"}'))])

    async def acomplete(**kwargs):
        return complete(**kwargs)

    llm._completion_with_retry = complete
    llm._acompletion_with_retry = acomplete
    schema = Answer if schema_kind == 'pydantic' else Answer.model_json_schema()
    output = {'output_pydantic': schema} if schema_kind == 'pydantic' else {'output_json': schema}
    kwargs = dict(model=requested, stream=False, verbose=False, **output)
    answer = llm.response('question', **kwargs) if mode == 'sync' else await llm.aresponse('question', **kwargs)
    assert answer == '{"answer":"ok"}'
    assert len(requests) == 1
    request = requests[0]
    assert request['model'] == requested
    assert 'output_json' not in request and 'output_pydantic' not in request
    if format_kind == 'gemini':
        assert 'response_format' not in request
        assert request['response_mime_type'] == 'application/json'
        assert request['response_schema'] == Answer.model_json_schema()
    elif format_kind == 'openai':
        assert 'response_schema' not in request
        assert 'response_mime_type' not in request
        assert request['response_format']['json_schema']['schema'] == Answer.model_json_schema()
    else:
        assert all(name not in request for name in ('response_format', 'response_schema', 'response_mime_type'))


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['sync', 'async'])
@pytest.mark.parametrize('schema_kind', ['pydantic', 'dict'])
@pytest.mark.parametrize('configured,requested,has_schema', [
    ('gpt-4-turbo', 'gpt-4o-mini', True),
    ('gpt-4o-mini', 'gpt-4-turbo', False),
    ('gpt-4o-mini', 'gpt-4o-mini', True),
    ('gpt-4-turbo', 'gpt-4-turbo', False),
])
async def test_public_responses_schema_uses_request_model(mode, schema_kind, configured, requested, has_schema):
    llm = LLM(model=configured)
    requests = []

    def respond(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(output=[{'type': 'message', 'content': [{'type': 'output_text', 'text': '{"answer":"ok"}'}]}])

    async def arespond(**kwargs):
        return respond(**kwargs)

    llm._call_responses_api = respond
    llm._call_responses_api_async = arespond
    schema = Answer if schema_kind == 'pydantic' else Answer.model_json_schema()
    output = {'output_pydantic': schema} if schema_kind == 'pydantic' else {'output_json': schema}
    kwargs = dict(model=requested, stream=False, verbose=False, **output)
    answer = llm.get_response('question', **kwargs) if mode == 'sync' else await llm.get_response_async('question', **kwargs)
    assert answer == '{"answer":"ok"}'
    assert len(requests) == 1
    request = requests[0]
    assert request['model'] == requested
    if has_schema:
        assert request['text']['format']['schema'] == Answer.model_json_schema()
        assert request['text']['format']['type'] == 'json_schema'
        assert request['text']['format']['strict'] is True
    else:
        assert 'text' not in request
