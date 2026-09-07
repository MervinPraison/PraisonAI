"""A rejected answer must be corrected *inside* the same run.

A guardrail could already say "no, because X", but that reason only ever reached
the model as a brand-new one-message request - original prompt plus a note -
with the system prompt, context and the rejected answer itself all thrown away.
These tests pin the in-run correction loop:

  * a validator that rejects once costs exactly two model calls and returns the
    corrected answer (control: a passing validator costs exactly one);
  * the rejection text is in the second request, appended to the *same*
    conversation after the rejected assistant turn (control: it appears nowhere
    in the first request, and nowhere at all when validation passes);
  * a validator that always rejects stops at ``max_guardrail_retries`` with an
    error naming the bound and the last reason (control: the identical setup
    with a satisfiable validator succeeds within the same bound).

Everything runs against a stubbed OpenAI transport - no network.
"""
import asyncio
import json
import types

import pytest

from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import (
    ExecutionConfig,
    GuardrailConfig,
    OutputConfig,
)
from praisonaiagents.guardrails import GuardrailRetry
from praisonaiagents.llm.openai_client import OpenAIClient

CALL_CAP = 25  # generous: a bounded loop uses <10


class _CallCap(BaseException):
    """BaseException so the agent's own `except Exception` cannot swallow it."""


class _Msg:
    role = "assistant"
    refusal = None
    parsed = None
    tool_calls = None
    reasoning_content = None

    def __init__(self, content):
        self.content = content

    def model_dump(self):
        return {"role": "assistant", "content": self.content}


class _Usage:
    prompt_tokens = 10
    completion_tokens = 5
    total_tokens = 15
    completion_tokens_details = None
    prompt_tokens_details = None

    def model_dump(self):
        return {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


class _Resp:
    id = "chatcmpl-test"
    created = 0
    object = "chat.completion"
    model = "gpt-4o-mini"

    def __init__(self, msg):
        self.choices = [types.SimpleNamespace(message=msg, finish_reason="stop",
                                              index=0, delta=None)]
        self.usage = _Usage()


class _Transport:
    """Scripted answers, recording every request's message list."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.requests = []  # one entry per model call: the messages sent

    @property
    def calls(self):
        return len(self.requests)

    def create(self, **kwargs):
        self.requests.append([dict(m) for m in kwargs.get("messages", [])])
        if self.calls > CALL_CAP:
            raise _CallCap(f"exceeded {CALL_CAP} LLM calls -- loop is unbounded")
        idx = min(self.calls - 1, len(self.answers) - 1)
        return _Resp(_Msg(self.answers[idx]))

    async def acreate(self, **kwargs):
        return self.create(**kwargs)

    def text_of(self, request_index):
        """All text sent in one request, flattened for substring assertions."""
        return json.dumps(self.requests[request_index])


def _agent(answers, guardrail, max_retries=3):
    t = _Transport(answers)
    agent = Agent(
        name="V",
        instructions="answer the question",
        llm="gpt-4o-mini",
        # max_retries is the package's existing "how many times may output
        # validation retry" knob; no competing setting was added.
        guardrails=GuardrailConfig(validator=guardrail, max_retries=max_retries),
        # Keep the guardrail backoff off the wall clock; must stay > 0.
        execution=ExecutionConfig(retry_initial_delay=0.001, retry_jitter=0.0),
        # Non-streaming so the stub can answer with a plain completion object.
        output=OutputConfig(stream=False),
    )

    client = OpenAIClient(api_key="sk-not-a-real-key")
    client._sync_client = types.SimpleNamespace(
        chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(name="create", create=t.create)),
        beta=types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=types.SimpleNamespace(parse=None))),
        responses=None)
    client._async_client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=t.acreate)),
        beta=types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=types.SimpleNamespace(parse=None))),
        responses=None)
    agent._Agent__openai_client = client
    agent._unified_dispatcher = None
    return agent, t


# --- validators -------------------------------------------------------------

POSTCODE_REASON = "the postcode must be in the customer's country"


def rejects_first_answer(output):
    """Accepts anything that is not the known-bad first answer."""
    if "10001" in output.raw:
        return False, POSTCODE_REASON
    return True, output


def raises_on_first_answer(output):
    """Same rule, expressed by raising instead of returning a tuple."""
    if "10001" in output.raw:
        raise GuardrailRetry(POSTCODE_REASON)
    return True, output


def always_rejects(output):
    return False, POSTCODE_REASON


def always_passes(output):
    return True, output


class TestRejectThenAccept:
    """One rejection, one correction, inside a single run."""

    def test_two_model_calls_and_the_corrected_answer(self):
        agent, t = _agent(["10001", "SW1A 1AA"], rejects_first_answer)
        result = agent.chat("what is the postcode?", stream=False)
        assert t.calls == 2, f"expected 1 retry, got {t.calls} model calls"
        assert result == "SW1A 1AA"

    def test_control_passing_validator_costs_one_call(self):
        agent, t = _agent(["SW1A 1AA", "SHOULD NOT BE REACHED"], always_passes)
        result = agent.chat("what is the postcode?", stream=False)
        assert t.calls == 1, f"a passing validator must not retry (got {t.calls})"
        assert result == "SW1A 1AA"

    def test_retry_is_counted(self):
        agent, t = _agent(["10001", "SW1A 1AA"], rejects_first_answer)
        agent.chat("what is the postcode?", stream=False)
        assert agent.guardrail_retry_count == 1
        assert agent.last_guardrail_error == POSTCODE_REASON

    def test_control_no_retry_is_counted_when_validation_passes(self):
        agent, _t = _agent(["SW1A 1AA"], always_passes)
        agent.chat("what is the postcode?", stream=False)
        assert agent.guardrail_retry_count == 0
        assert agent.last_guardrail_error is None

    def test_guardrail_retry_exception_is_equivalent_to_a_false_tuple(self):
        agent, t = _agent(["10001", "SW1A 1AA"], raises_on_first_answer)
        result = agent.chat("what is the postcode?", stream=False)
        assert t.calls == 2
        assert result == "SW1A 1AA"

    def test_async_path_also_corrects_in_run(self):
        agent, t = _agent(["10001", "SW1A 1AA"], rejects_first_answer)
        result = asyncio.run(agent.achat("what is the postcode?", stream=False))
        assert t.calls == 2, f"expected 1 retry, got {t.calls} model calls"
        assert result == "SW1A 1AA"


class TestRetriesAreObservable:
    """A retry must be visible to whoever is watching the run."""

    def _retry_events(self, agent):
        from praisonaiagents.streaming.events import StreamEventType
        seen = []
        agent.stream_emitter.add_callback(
            lambda e: seen.append(e) if e.type is StreamEventType.RETRY else None)
        return seen

    def test_retry_is_announced_on_the_stream(self):
        agent, _t = _agent(["10001", "SW1A 1AA"], rejects_first_answer)
        seen = self._retry_events(agent)
        agent.chat("what is the postcode?", stream=False)
        assert len(seen) == 1, f"expected 1 RETRY event, got {len(seen)}"
        event = seen[0]
        assert POSTCODE_REASON in event.metadata["reason"]
        assert event.metadata["attempt"] == 1
        assert event.metadata["max_attempts"] == 3

    def test_control_no_retry_event_when_validation_passes(self):
        agent, _t = _agent(["SW1A 1AA"], always_passes)
        seen = self._retry_events(agent)
        agent.chat("what is the postcode?", stream=False)
        assert seen == []


class TestFeedbackReachesTheModel:
    """The reason must be in the next request, not merely logged."""

    def test_rejection_reason_is_in_the_second_request(self):
        agent, t = _agent(["10001", "SW1A 1AA"], rejects_first_answer)
        agent.chat("what is the postcode?", stream=False)
        assert t.calls == 2
        assert POSTCODE_REASON not in t.text_of(0), \
            "the reason cannot be known before the first answer exists"
        assert POSTCODE_REASON in t.text_of(1), \
            "the validator's reason never reached the model"

    def test_retry_continues_the_same_conversation(self):
        agent, t = _agent(["10001", "SW1A 1AA"], rejects_first_answer)
        agent.chat("what is the postcode?", stream=False)
        first, second = t.requests[0], t.requests[1]

        # The whole original conversation is still there ...
        assert second[:len(first)] == first, \
            "retry restarted the conversation instead of continuing it"
        # ... followed by the rejected answer and the reason as a user turn.
        assert second[len(first)] == {"role": "assistant", "content": "10001"}
        assert second[len(first) + 1]["role"] == "user"
        assert POSTCODE_REASON in second[len(first) + 1]["content"]

    def test_control_no_feedback_text_when_validation_passes(self):
        agent, t = _agent(["SW1A 1AA"], always_passes)
        agent.chat("what is the postcode?", stream=False)
        assert t.calls == 1
        assert "failed validation" not in t.text_of(0)
        assert POSTCODE_REASON not in t.text_of(0)


class TestAlwaysFailingValidatorIsBounded:
    """A validator that never passes must stop, loudly."""

    def test_stops_at_the_bound_with_a_clear_error(self):
        agent, t = _agent(["10001"], always_rejects, max_retries=2)
        try:
            result = agent.chat("what is the postcode?", stream=False)
        except _CallCap as exc:
            pytest.fail(str(exc))

        # chat() reports guardrail exhaustion by returning None after rolling
        # back history; the reason is on the agent for the caller to read.
        assert result is None
        assert agent.guardrail_retry_count == 2, \
            f"must retry exactly max_guardrail_retries times, got {agent.guardrail_retry_count}"
        assert t.calls == 1 + 2, f"1 initial call + 2 retries, got {t.calls}"
        assert agent.last_guardrail_error == POSTCODE_REASON

    def test_the_bound_is_reported_by_the_raising_layer(self):
        agent, _t = _agent(["10001"], always_rejects, max_retries=2)
        with pytest.raises(Exception) as excinfo:
            agent._apply_guardrail_with_retry(
                "10001", "what is the postcode?",
                messages=[{"role": "user", "content": "what is the postcode?"}],
            )
        message = str(excinfo.value)
        assert "after 2 retries" in message, message
        assert POSTCODE_REASON in message, message

    def test_control_same_setup_succeeds_within_the_bound(self):
        agent, t = _agent(["10001", "10001", "SW1A 1AA"], rejects_first_answer,
                          max_retries=2)
        result = agent.chat("what is the postcode?", stream=False)
        assert result == "SW1A 1AA"
        assert t.calls == 3
        assert agent.guardrail_retry_count == 2

    def test_max_retries_zero_never_retries(self):
        agent, t = _agent(["10001", "SW1A 1AA"], rejects_first_answer, max_retries=0)
        result = agent.chat("what is the postcode?", stream=False)
        assert result is None
        assert t.calls == 1, f"max_guardrail_retries=0 must not call the model again (got {t.calls})"
        assert agent.guardrail_retry_count == 0


class TestFallbackWithoutAConversation:
    """Callers that cannot hand over a message list keep the old behaviour."""

    def test_reason_still_reaches_the_model_via_the_prompt(self):
        # The rejected answer is supplied directly, so the transport's first
        # call *is* the retry.
        agent, t = _agent(["SW1A 1AA"], rejects_first_answer)
        result = agent._apply_guardrail_with_retry("10001", "what is the postcode?")
        assert result == "SW1A 1AA"
        assert t.calls == 1  # the initial answer was supplied, not fetched
        assert POSTCODE_REASON in t.text_of(0)
        assert "what is the postcode?" in t.text_of(0)
