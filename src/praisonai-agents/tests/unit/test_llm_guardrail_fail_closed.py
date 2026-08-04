"""Regression tests for LLMGuardrail fail-closed behavior on ambiguous replies.

Guards against the two entry points (``__call__`` and ``_llm_validate``)
diverging again: both MUST fail closed (return False) when the validation LLM
returns a reply that is neither a clean PASS nor FAIL. See issue #3573 (Gap 1).
"""

from praisonaiagents.guardrails.llm_guardrail import LLMGuardrail


class _AmbiguousLLM:
    """Callable LLM stub returning a reply that is neither PASS nor FAIL."""

    def __init__(self, reply):
        self.reply = reply

    def __call__(self, prompt, **kwargs):
        return self.reply


def test_call_fails_closed_on_ambiguous_response():
    guardrail = LLMGuardrail(
        description="output must not contain PII",
        llm=_AmbiguousLLM("```\nPASS\n```"),
    )
    is_valid, _ = guardrail("some task output")
    assert is_valid is False


def test_call_fails_closed_on_refusal():
    guardrail = LLMGuardrail(
        description="must be safe",
        llm=_AmbiguousLLM("I cannot help with that."),
    )
    is_valid, _ = guardrail("some task output")
    assert is_valid is False


def test_llm_validate_fails_closed_on_ambiguous_response():
    guardrail = LLMGuardrail(
        description="must be safe",
        llm=_AmbiguousLLM("maybe?"),
    )
    is_valid, _ = guardrail._llm_validate("content", "must be safe")
    assert is_valid is False


def test_both_entry_points_agree_on_ambiguous_reply():
    reply = "thinking... the answer is unclear"
    call_guard = LLMGuardrail(description="d", llm=_AmbiguousLLM(reply))
    validate_guard = LLMGuardrail(description="d", llm=_AmbiguousLLM(reply))
    call_valid, _ = call_guard("output")
    validate_valid, _ = validate_guard._llm_validate("content", "d")
    assert call_valid is validate_valid is False


def test_call_still_passes_clean_pass():
    guardrail = LLMGuardrail(description="d", llm=_AmbiguousLLM("PASS"))
    is_valid, _ = guardrail("output")
    assert is_valid is True


def test_call_still_fails_clean_fail():
    guardrail = LLMGuardrail(description="d", llm=_AmbiguousLLM("FAIL: bad"))
    is_valid, _ = guardrail("output")
    assert is_valid is False


class _GetResponseLLM:
    """Stub mirroring the SDK's own LLM.get_response interface (issue #3631)."""

    def __init__(self, reply):
        self.reply = reply

    def get_response(self, prompt, verbose=True, markdown=True, stream=True, **kwargs):
        return self.reply


def test_llm_validate_reaches_get_response_interface():
    """Regression: an LLM exposing only get_response must be validated,
    not silently rejected as an "Invalid LLM instance"."""
    guardrail = LLMGuardrail(description="d", llm=_GetResponseLLM("PASS"))
    is_valid, result = guardrail._llm_validate("content", "d")
    assert is_valid is True
    assert result == "content"


def test_get_response_llm_clean_fail():
    guardrail = LLMGuardrail(description="d", llm=_GetResponseLLM("FAIL: bad"))
    is_valid, _ = guardrail._llm_validate("content", "d")
    assert is_valid is False
