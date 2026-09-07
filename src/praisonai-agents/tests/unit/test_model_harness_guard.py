"""Tests for the global "no real model calls" guard.

Each block pairs a blocked run with a control run that is identical except for
the guard, so a passing assertion cannot be explained by the request failing
for some unrelated reason (a missing key, an unreachable host).
"""

import asyncio

import pytest

from praisonaiagents import Agent
from praisonaiagents.model_harness import (
    ModelRequestBlocked,
    ScriptedModel,
    allow_model_requests,
    model_requests_allowed,
    no_model_requests,
)
from praisonaiagents.llm.llm import LLM


@pytest.fixture(autouse=True)
def restore_guard():
    """Never leak the global setting into another test."""
    previous = model_requests_allowed()
    try:
        yield
    finally:
        allow_model_requests(previous)


@pytest.fixture
def litellm_sentinel(monkeypatch):
    """Replace litellm's request functions with a recorder.

    Lets the control runs prove a request *would* have gone out, without one
    actually going out.
    """
    import litellm

    seen = []

    def record(**kwargs):
        seen.append(kwargs)
        from litellm import Choices, Message, ModelResponse

        return ModelResponse(
            id="sentinel",
            model=kwargs.get("model", "sentinel"),
            choices=[
                Choices(
                    finish_reason="stop",
                    index=0,
                    message=Message(role="assistant", content="sentinel reply"),
                )
            ],
        )

    monkeypatch.setattr(litellm, "completion", record)
    monkeypatch.setattr(litellm, "responses", record)
    return seen


@pytest.fixture
def openai_sentinel(monkeypatch):
    """Make OpenAI client construction observable without building one."""
    built = []

    def classes():
        built.append(True)
        raise RuntimeError("stop before any network I/O")

    monkeypatch.setattr(
        "praisonaiagents.llm.openai_client._get_openai_classes", classes
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    return built


# ---------------------------------------------------------------------------
# The LiteLLM path
# ---------------------------------------------------------------------------

def test_guard_blocks_a_litellm_request_and_names_the_call_site(litellm_sentinel):
    allow_model_requests(False)
    model = LLM(model="openai/gpt-4o-mini")

    with pytest.raises(ModelRequestBlocked) as excinfo:
        model.get_response("hi", verbose=False)  # the offending call site

    error = excinfo.value
    assert litellm_sentinel == []  # nothing reached litellm
    assert error.model == "openai/gpt-4o-mini"
    assert error.provider in ("litellm.completion", "litellm.responses")
    # The call site is this test file and this test, not an internal frame.
    assert __file__ in error.call_site
    assert "test_guard_blocks_a_litellm_request_and_names_the_call_site" in error.call_site
    assert "praisonaiagents/llm" not in error.call_site
    assert "allow_model_requests" in str(error)


def test_control_the_same_litellm_request_goes_through_when_allowed(litellm_sentinel):
    allow_model_requests(True)
    model = LLM(model="openai/gpt-4o-mini")

    model.get_response("hi", verbose=False)

    # The same call that was blocked above now reaches litellm.
    assert len(litellm_sentinel) == 1
    assert litellm_sentinel[0]["model"] == "openai/gpt-4o-mini"


def test_guard_blocks_the_async_litellm_path(litellm_sentinel):
    allow_model_requests(False)
    model = LLM(model="openai/gpt-4o-mini")

    with pytest.raises(ModelRequestBlocked):
        asyncio.run(model.get_response_async("hi", verbose=False))


# ---------------------------------------------------------------------------
# The OpenAI-native path
# ---------------------------------------------------------------------------

def test_guard_blocks_the_openai_native_path(openai_sentinel):
    allow_model_requests(False)
    agent = Agent(instructions="bot", llm="gpt-4o-mini")

    with pytest.raises(ModelRequestBlocked) as excinfo:
        agent.chat("hi")  # the offending call site

    assert openai_sentinel == []  # no client was even constructed
    assert excinfo.value.provider == "openai.chat.completions"
    assert __file__ in excinfo.value.call_site
    assert "test_guard_blocks_the_openai_native_path" in excinfo.value.call_site


def test_control_the_openai_native_path_builds_its_client_when_allowed(openai_sentinel):
    allow_model_requests(True)
    agent = Agent(instructions="bot", llm="gpt-4o-mini")

    agent.chat("hi")  # RuntimeError from the sentinel is handled by the agent

    assert openai_sentinel  # the guard let it get as far as the client


# ---------------------------------------------------------------------------
# Scripted models keep working while the guard is on
# ---------------------------------------------------------------------------

def test_a_scripted_model_answers_while_requests_are_blocked(litellm_sentinel):
    allow_model_requests(False)
    model = ScriptedModel(["scripted answer"])

    assert Agent(instructions="bot", llm=model).start("hi") == "scripted answer"
    assert litellm_sentinel == []


def test_control_an_unscripted_agent_under_the_same_guard_is_blocked(litellm_sentinel):
    allow_model_requests(False)
    agent = Agent(instructions="bot", llm="openai/gpt-4o-mini")

    with pytest.raises(ModelRequestBlocked):
        agent.chat("hi")


# ---------------------------------------------------------------------------
# The switch itself
# ---------------------------------------------------------------------------

def test_no_model_requests_blocks_then_restores_the_previous_setting():
    allow_model_requests(True)

    with no_model_requests():
        assert model_requests_allowed() is False

    assert model_requests_allowed() is True


def test_control_no_model_requests_restores_a_blocked_setting_too():
    allow_model_requests(False)

    with no_model_requests():
        assert model_requests_allowed() is False

    assert model_requests_allowed() is False


def test_overlapping_no_model_requests_scopes_stay_blocked_until_all_exit():
    """Two scopes with independent lifetimes must not re-enable early.

    The inner scope exiting first must not restore ``allowed`` while the outer
    scope is still open -- the failure mode a save/restore snapshot has.
    """
    allow_model_requests(True)

    outer = no_model_requests()
    inner = no_model_requests()
    outer.__enter__()
    inner.__enter__()
    assert model_requests_allowed() is False

    # Inner exits first; the outer scope is still open, so requests stay blocked.
    inner.__exit__(None, None, None)
    assert model_requests_allowed() is False

    outer.__exit__(None, None, None)
    assert model_requests_allowed() is True


def test_no_model_requests_reblocks_even_when_globally_allowed():
    """A block scope must win over a True global flag for its duration."""
    allow_model_requests(True)
    with no_model_requests():
        assert model_requests_allowed() is False
    assert model_requests_allowed() is True


def test_blocked_error_is_not_swallowed_by_the_agents_error_handling(litellm_sentinel):
    """The agent turns most failures into a None answer; this must escape that."""
    allow_model_requests(False)
    agent = Agent(instructions="bot", llm="openai/gpt-4o-mini")

    with pytest.raises(ModelRequestBlocked):
        agent.start("hi")


def test_control_an_ordinary_provider_failure_is_still_handled(monkeypatch):
    """Control: a normal exception keeps the agent's existing behaviour."""
    import litellm

    def boom(**kwargs):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(litellm, "completion", boom)
    monkeypatch.setattr(litellm, "responses", boom)
    allow_model_requests(True)
    agent = Agent(instructions="bot", llm="openai/gpt-4o-mini")

    assert agent.start("hi") is None  # swallowed, as it always was
