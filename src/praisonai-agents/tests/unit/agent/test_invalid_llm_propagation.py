"""An invalid model must raise, not return ``None`` (#5956).

Covers the default OpenAI client path and the litellm-routed path
(``openai/<model>``), sync and async, streaming and not. Provider calls are
patched to raise a local 404 stub, so no network or provider SDK error class is
needed. Auth errors keep today's behaviour (``None``).
"""

import asyncio
from unittest import mock

import pytest

from praisonaiagents import Agent

_COMPLETIONS = "openai.resources.chat.completions.Completions.create"
_ASYNC_COMPLETIONS = "openai.resources.chat.completions.AsyncCompletions.create"


class _StubNotFound(Exception):
    """Shape of openai/litellm ``NotFoundError``: only ``status_code`` matters."""

    status_code = 404


class _StubAuth(Exception):
    status_code = 401


def _raiser(exc_type, text):
    def sync(*_a, **_k):
        raise exc_type(text)

    async def async_(*_a, **_k):
        raise exc_type(text)

    return sync, async_


def _call(agent, method, stream):
    result = getattr(agent, method)("hi", stream=stream)
    if asyncio.iscoroutine(result):
        result = asyncio.run(result)
    if hasattr(result, "__next__"):
        result = list(result)
    return result


METHODS = ["start", "run", "chat", "astart", "arun", "achat"]


@pytest.fixture(autouse=True)
def _dummy_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy")


@pytest.fixture
def openai_404():
    sync, async_ = _raiser(_StubNotFound, "Error code: 404 - model `no-such-model` does not exist")
    with mock.patch(_COMPLETIONS, sync), mock.patch(_ASYNC_COMPLETIONS, async_):
        yield


@pytest.fixture
def litellm_404():
    litellm = pytest.importorskip("litellm")
    sync, async_ = _raiser(_StubNotFound, "Error code: 404 - model `no-such-model` does not exist")
    with mock.patch.object(litellm, "completion", sync), mock.patch.object(litellm, "acompletion", async_):
        yield


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("method", METHODS)
def test_default_openai_path_raises_on_invalid_model(openai_404, method, stream):
    agent = Agent(name="t", llm="no-such-model", output="silent")
    with pytest.raises(Exception, match="404"):
        _call(agent, method, stream)
    assert agent.chat_history == []  # failed turn rolled back


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("method", METHODS)
def test_litellm_path_raises_on_invalid_model(litellm_404, method, stream):
    agent = Agent(name="t", llm="openai/no-such-model", output="silent")
    with pytest.raises(Exception, match="404"):
        _call(agent, method, stream)
    assert agent.chat_history == []


@pytest.mark.parametrize("method", ["chat", "achat"])
def test_auth_error_keeps_returning_none(method):
    sync, async_ = _raiser(_StubAuth, "Error code: 401 - invalid api key")
    with mock.patch(_COMPLETIONS, sync), mock.patch(_ASYNC_COMPLETIONS, async_):
        agent = Agent(name="t", llm="no-such-model", output="silent")
        assert _call(agent, method, False) is None
