"""reasoning_effort must reach the provider on the Responses API path too.

OpenAI reasoning models (o1/o3/o4, gpt-5 on the native client) are sent to the
Responses API by default. That API takes the level as
``reasoning: {"effort": ...}``; neither Responses request builder applied the
unified ``reasoning_effort`` (Issue #4452), so ``Agent(llm="o4-mini",
reasoning_effort="high")`` produced a request without any effort on the
default, non-streaming path. These tests assert on what the transport receives.
"""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

from praisonaiagents import Agent
from praisonaiagents.llm.llm import LLM
from praisonaiagents.llm.openai_client import OpenAIClient


@pytest.fixture(autouse=True)
def isolate_responses_endpoint(monkeypatch):
    """The Responses path is only taken without a custom endpoint."""
    monkeypatch.delenv('OPENAI_API_BASE', raising=False)
    monkeypatch.delenv('OPENAI_BASE_URL', raising=False)


def _response(text='ok'):
    return {'status': 'completed', 'output': [
        {'type': 'message', 'content': [{'type': 'output_text', 'text': text}]}]}


MESSAGES = [{'role': 'user', 'content': 'question'}]


class TestLLMResponsesParams:

    @pytest.mark.parametrize('model', ['o4-mini', 'openai/o3', 'azure/o1'])
    def test_instance_effort_becomes_reasoning_effort_object(self, model):
        params = LLM(model=model, reasoning_effort='high')._build_responses_params(MESSAGES)
        assert params['reasoning'] == {'effort': 'high'}
        assert 'reasoning_effort' not in params

    def test_per_call_effort_overrides_instance(self):
        llm = LLM(model='o4-mini', reasoning_effort='low')
        params = llm._build_responses_params(MESSAGES, reasoning_effort='high')
        assert params['reasoning'] == {'effort': 'high'}
        assert 'reasoning_effort' not in params

    @pytest.mark.parametrize('effort', [None, 'off'])
    def test_unset_or_off_sends_nothing(self, effort):
        params = LLM(model='o4-mini', reasoning_effort=effort)._build_responses_params(MESSAGES)
        assert 'reasoning' not in params

    def test_model_without_reasoning_control_is_untouched(self):
        params = LLM(model='gpt-4o-mini', reasoning_effort='high')._build_responses_params(MESSAGES)
        assert 'reasoning' not in params
        assert 'reasoning_effort' not in params

    def test_explicit_reasoning_object_is_kept(self):
        llm = LLM(model='o4-mini', reasoning_effort='high')
        explicit = {'effort': 'low', 'summary': 'auto'}
        params = llm._build_responses_params(MESSAGES, reasoning=explicit)
        assert params['reasoning'] == explicit

    def test_public_get_response_sends_effort(self):
        llm = LLM(model='o4-mini', reasoning_effort='high')
        requests = []

        def respond(**kwargs):
            requests.append(kwargs)
            return _response()

        llm._call_responses_api = respond
        assert llm.get_response('question', stream=False, verbose=False) == 'ok'
        assert requests[0]['reasoning'] == {'effort': 'high'}


class TestOpenAIClientResponsesInput:

    def test_reasoning_effort_kwarg_becomes_reasoning_object(self):
        client = OpenAIClient.__new__(OpenAIClient)
        params = client._build_responses_input(MESSAGES, 'o4-mini', None, None, reasoning_effort='high')
        assert params['reasoning'] == {'effort': 'high'}
        assert 'reasoning_effort' not in params

    def test_no_effort_no_reasoning_object(self):
        client = OpenAIClient.__new__(OpenAIClient)
        params = client._build_responses_input(MESSAGES, 'o4-mini', None, None)
        assert 'reasoning' not in params


def _agent_request(model, **agent_kwargs):
    """Drive a real Agent on the native OpenAI client, faking only responses.create."""
    requests = []

    def respond(**kwargs):
        requests.append(kwargs)
        return _response()

    async def arespond(**kwargs):
        return respond(**kwargs)

    client = OpenAIClient(api_key='sk-test-not-real')
    client._sync_client = SimpleNamespace(responses=SimpleNamespace(create=respond))
    client._async_client = SimpleNamespace(responses=SimpleNamespace(create=arespond))
    agent = Agent(name='t', instructions='x', llm=model, **agent_kwargs)
    agent._Agent__openai_client = client
    assert agent.start('hi') == 'ok'
    assert requests, 'no Responses API request was made'
    return requests[-1]


class TestAgentNativeOpenAIPath:

    def test_reasoning_model_gets_effort(self):
        assert _agent_request('o4-mini', reasoning_effort='high')['reasoning'] == {'effort': 'high'}

    def test_unset_effort_sends_nothing(self):
        assert 'reasoning' not in _agent_request('o4-mini')

    def test_model_without_reasoning_control_is_untouched(self):
        assert 'reasoning' not in _agent_request('gpt-4o-mini', reasoning_effort='high')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
