"""Tests for ScriptedModel -- the offline model double.

Each behaviour is paired with a control: a near-identical run that must NOT
show the behaviour, so a passing assertion cannot be explained by the test
setup alone (e.g. an agent that returns a constant, or a tool that runs
regardless of what was scripted).
"""

import asyncio

import pytest

from praisonaiagents import Agent
from praisonaiagents.model_harness import (
    RecordedRequest,
    ScriptedModel,
    ScriptedModelError,
    ScriptedToolCall,
    ScriptExhausted,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def no_network(monkeypatch):
    """Make every real provider entry point explode.

    Any test using this fixture proves it stayed offline: if the double leaked
    a real request, litellm or the OpenAI client would raise here.
    """
    import litellm

    def exploded(*args, **kwargs):
        raise AssertionError("a real model request escaped the test double")

    for name in ("completion", "acompletion", "responses", "aresponses"):
        monkeypatch.setattr(litellm, name, exploded, raising=False)
    monkeypatch.setattr(
        "praisonaiagents.llm.openai_client._get_openai_classes", exploded
    )
    return exploded


def make_refund_tool(calls):
    def refund(order_id: str) -> str:
        """Refund an order."""
        calls.append(order_id)
        return f"refunded {order_id}"

    return refund


# ---------------------------------------------------------------------------
# A scripted answer, with no network
# ---------------------------------------------------------------------------

def test_agent_returns_the_scripted_answer_with_no_network(no_network):
    model = ScriptedModel(["Paris."])
    agent = Agent(instructions="You are a geography bot.", llm=model)

    assert agent.start("What is the capital of France?") == "Paris."
    assert model.request_count == 1
    assert model.exhausted


def test_control_the_answer_comes_from_the_script_not_a_constant(no_network):
    """Control: a different script yields a different answer."""
    model = ScriptedModel(["Reykjavik."])
    agent = Agent(instructions="You are a geography bot.", llm=model)

    assert agent.start("What is the capital of France?") == "Reykjavik."


def test_agent_adopts_the_double_as_its_backend():
    """Agent(llm=<model instance>) must wire the object in, not stringify it."""
    model = ScriptedModel(["hi"])
    agent = Agent(instructions="bot", llm=model)

    assert agent.llm_instance is model
    assert agent.llm == "scripted/model"


def test_control_a_model_name_still_builds_a_real_backend():
    """Control: passing a name is unaffected by the instance branch."""
    agent = Agent(instructions="bot", llm="openai/gpt-4o-mini")

    assert agent.llm == "openai/gpt-4o-mini"
    assert not isinstance(agent.llm_instance, ScriptedModel)


# ---------------------------------------------------------------------------
# A scripted tool call, then the follow-up answer
# ---------------------------------------------------------------------------

def test_scripted_tool_call_is_executed_and_follow_up_is_returned(no_network):
    calls = []
    model = ScriptedModel([
        ScriptedModel.tool_call("refund", {"order_id": "A1"}),
        "Refunded order A1.",
    ])
    agent = Agent(
        instructions="Support bot.", llm=model, tools=[make_refund_tool(calls)]
    )

    assert agent.start("refund order A1") == "Refunded order A1."
    # The agent really dispatched the tool, with the scripted arguments.
    assert calls == ["A1"]
    # Two turns: the tool-call turn and the follow-up.
    assert model.request_count == 2
    # Each turn is snapshotted, not a live view of one growing list: the
    # first request predates the tool result, the second carries it.
    assert model.requests[0].tool_results == ()
    tool_results = model.requests[1].tool_results
    assert len(tool_results) == 1
    assert "refunded A1" in tool_results[0]["content"]


def test_control_an_unscripted_tool_never_runs(no_network):
    """Control: same agent and tool, but nothing scripts the call."""
    calls = []
    model = ScriptedModel(["Nothing to refund."])
    agent = Agent(
        instructions="Support bot.", llm=model, tools=[make_refund_tool(calls)]
    )

    assert agent.start("refund order A1") == "Nothing to refund."
    assert calls == []
    assert model.request_count == 1


def test_multiple_tool_calls_in_one_turn_all_run(no_network):
    calls = []
    model = ScriptedModel([
        ScriptedModel.tool_calls(
            ScriptedToolCall("refund", {"order_id": "A1"}),
            ScriptedToolCall("refund", {"order_id": "B2"}),
        ),
        "Both refunded.",
    ])
    agent = Agent(
        instructions="Support bot.", llm=model, tools=[make_refund_tool(calls)]
    )

    assert agent.start("refund A1 and B2") == "Both refunded."
    assert calls == ["A1", "B2"]


# ---------------------------------------------------------------------------
# Recorded requests
# ---------------------------------------------------------------------------

def test_recorded_request_contains_the_system_prompt_and_the_user_turn(no_network):
    calls = []
    model = ScriptedModel([
        ScriptedModel.tool_call("refund", {"order_id": "A1"}),
        "Done.",
    ])
    agent = Agent(
        instructions="You only handle refunds.",
        llm=model,
        tools=[make_refund_tool(calls)],
    )
    agent.start("refund order A1")

    first = model.requests[0]
    assert isinstance(first, RecordedRequest)
    assert "You only handle refunds." in first.system_prompt
    assert first.last_user_message == "refund order A1"
    # The tools the agent actually offered are recorded too.
    assert first.tool_names == ("refund",)
    # Full parameters are available for finer assertions.
    assert first.params["model"] == "scripted/model"
    assert first.stream is False


def test_control_the_recording_tracks_this_agent_not_a_fixed_snapshot(no_network):
    """Control: different instructions and turn produce a different recording."""
    model = ScriptedModel(["Done."])
    agent = Agent(instructions="You only handle billing.", llm=model)
    agent.start("close my account")

    first = model.requests[0]
    assert "You only handle billing." in first.system_prompt
    assert "You only handle refunds." not in first.system_prompt
    assert first.last_user_message == "close my account"
    assert first.tool_names == ()


def test_a_callable_script_entry_receives_the_request(no_network):
    model = ScriptedModel([lambda request: f"You said: {request.last_user_message}"])
    agent = Agent(instructions="Echo bot.", llm=model)

    assert agent.start("hello there") == "You said: hello there"


# ---------------------------------------------------------------------------
# Running out of script
# ---------------------------------------------------------------------------

def test_running_out_of_script_raises_a_clear_error(no_network):
    calls = []
    # One reply short: the tool result needs a follow-up answer.
    model = ScriptedModel([ScriptedModel.tool_call("refund", {"order_id": "A1"})])
    agent = Agent(
        instructions="Support bot.", llm=model, tools=[make_refund_tool(calls)]
    )

    with pytest.raises(ScriptExhausted) as excinfo:
        agent.start("refund order A1")

    message = str(excinfo.value)
    assert "ran out of scripted replies" in message
    assert "reply #2" in message  # says which reply was missing
    assert "the script holds 1" in message  # and how many it had
    assert excinfo.value.request_index == 2
    assert excinfo.value.scripted == 1


def test_control_one_more_scripted_reply_makes_the_same_run_succeed(no_network):
    calls = []
    model = ScriptedModel([
        ScriptedModel.tool_call("refund", {"order_id": "A1"}),
        "All set.",
    ])
    agent = Agent(
        instructions="Support bot.", llm=model, tools=[make_refund_tool(calls)]
    )

    assert agent.start("refund order A1") == "All set."


def test_exhaustion_is_not_swallowed_into_a_none_answer(no_network):
    """The agent's broad ``except Exception`` must not hide the empty script.

    This is why ScriptExhausted derives from BaseException: an ordinary
    exception here surfaces as ``agent.start(...) is None``, which reads like a
    bug in the agent rather than a one-line fix to the test.
    """
    model = ScriptedModel([])
    agent = Agent(instructions="bot", llm=model)

    with pytest.raises(ScriptExhausted):
        agent.start("hi")


# ---------------------------------------------------------------------------
# Async and streaming paths
# ---------------------------------------------------------------------------

def test_async_path_is_driven_by_the_same_script(no_network):
    model = ScriptedModel(["async answer"])
    agent = Agent(instructions="bot", llm=model)

    assert asyncio.run(agent.achat("hi")) == "async answer"
    assert model.request_count == 1


def test_streaming_path_is_driven_by_the_same_script(no_network):
    model = ScriptedModel(["streamed answer"])
    agent = Agent(instructions="bot", llm=model)

    chunks = list(agent.start("hi", stream=True))

    assert "".join(chunks) == "streamed answer"


def test_control_streaming_and_non_streaming_agree(no_network):
    """Control: the same script yields the same text through either path."""
    streamed = ScriptedModel(["one answer"])
    plain = ScriptedModel(["one answer"])

    assert "".join(
        Agent(instructions="bot", llm=streamed).start("hi", stream=True)
    ) == Agent(instructions="bot", llm=plain).start("hi")


# ---------------------------------------------------------------------------
# Script bookkeeping
# ---------------------------------------------------------------------------

def test_reset_rewinds_the_script_and_clears_recordings(no_network):
    model = ScriptedModel(["first"])
    agent = Agent(instructions="bot", llm=model)
    assert agent.start("hi") == "first"
    assert model.remaining == 0

    model.reset()

    assert model.remaining == 1
    assert model.requests == ()
    assert Agent(instructions="bot", llm=model).start("hi") == "first"


def test_control_without_reset_the_script_stays_consumed(no_network):
    model = ScriptedModel(["first"])
    assert Agent(instructions="bot", llm=model).start("hi") == "first"

    with pytest.raises(ScriptExhausted):
        Agent(instructions="bot", llm=model).start("hi again")


def test_unusable_script_entry_is_rejected_at_the_scripted_model_line(no_network):
    """A typo in the script fails where it was written, not turns later."""
    with pytest.raises(TypeError) as excinfo:
        ScriptedModel(["fine", object()])

    assert "Script entry #2" in str(excinfo.value)


def test_control_a_valid_script_of_the_same_shape_is_accepted(no_network):
    model = ScriptedModel(["fine", "also fine"])

    assert model.remaining == 2


def test_a_callable_returning_garbage_is_not_swallowed(no_network):
    """Only checkable at run time, so it must dodge the loop's except Exception."""
    model = ScriptedModel([lambda request: object()])
    agent = Agent(instructions="bot", llm=model)

    with pytest.raises(ScriptedModelError, match="Script entry #1"):
        agent.start("hi")


class TestEveryDocumentedBackendProtocolIsAdopted:
    """Agent(llm=<backend object>) must adopt the object, whichever protocol it implements.

    The original fix duck-typed on `get_response` alone. Review pointed out that
    llm/protocols.py also documents LLMProviderProtocol (`chat`/`achat`) and
    UnifiedLLMProtocol (`chat_completion`/`achat_completion`); backends
    implementing those still fell through to the plain OpenAI branch, where the
    object became the model identifier and the turn went to the wrong backend.
    """

    @staticmethod
    def _agent(backend):
        from praisonaiagents import Agent
        return Agent(instructions="t", llm=backend)

    def test_get_response_backend_is_adopted(self):
        class B:
            model = "custom/a"
            def get_response(self, *a, **k): return "x"
        agent = self._agent(B())
        assert agent._using_custom_llm is True
        assert agent.llm == "custom/a"

    def test_chat_protocol_backend_is_adopted(self):
        class B:
            model = "custom/b"
            def chat(self, *a, **k): return "x"
        agent = self._agent(B())
        assert agent._using_custom_llm is True
        assert agent.llm == "custom/b"

    def test_chat_completion_protocol_backend_is_adopted(self):
        class B:
            model = "custom/c"
            def chat_completion(self, *a, **k): return "x"
            async def achat_completion(self, *a, **k): return "x"
        agent = self._agent(B())
        assert agent._using_custom_llm is True
        assert agent.llm == "custom/c"

    def test_control_a_plain_object_is_not_adopted(self):
        """Control: adoption must be earned by implementing a backend surface."""
        class NotABackend:
            pass
        agent = self._agent(NotABackend())
        assert agent._using_custom_llm is False

    def test_control_a_string_llm_is_unaffected(self):
        from praisonaiagents import Agent
        agent = Agent(instructions="t", llm="gpt-4o-mini")
        assert agent.llm == "gpt-4o-mini"
