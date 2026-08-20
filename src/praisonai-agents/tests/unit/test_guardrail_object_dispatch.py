"""Agent(guardrails=...) must never silently discard a validator.

A class-based validator conforming to GuardrailProtocol is not ``callable()``, so it
used to fall past every dispatch branch and be dropped with no exception or warning.
"""
import pytest

from praisonaiagents import Agent
from praisonaiagents.config.feature_configs import GuardrailConfig
from praisonaiagents.guardrails import GuardrailChain


class ProfanityFilter:
    """Exact shape documented in guardrails/protocols.py's GuardrailProtocol docstring."""

    def validate_input(self, content, **kwargs):
        if "badword" in content.lower():
            return False, "Content contains inappropriate language"
        return True, content

    def validate_output(self, content, **kwargs):
        return self.validate_input(content, **kwargs)

    def validate_tool_call(self, tool_name, arguments, **kwargs):
        return (False, arguments) if tool_name == "rm" else (True, arguments)


class UpperCaser:
    def validate_output(self, content, **kwargs):
        return True, content.upper()


def fn_guard(task_output):
    return True, task_output


def _agent(guardrails):
    return Agent(name="T", instructions="test", llm="gpt-4o-mini", guardrails=guardrails)


class TestGuardrailObjectAccepted:
    def test_single_object_is_not_discarded(self):
        a = _agent(ProfanityFilter())
        assert a._guardrail_fn is not None, "class-based guardrail was silently dropped"
        assert isinstance(a._guardrail_fn, GuardrailChain)

    def test_single_object_gates_input_both_ways(self):
        a = _agent(ProfanityFilter())
        ok, _r, error = a._validate_input_with_guardrail("this has a badword in it")
        assert ok is False and "inappropriate language" in error
        assert a._validate_input_with_guardrail("hello") == (True, "hello", None)

    def test_single_object_blocks_bad_output(self):
        a = _agent(ProfanityFilter())
        ok, _r, error = a._validate_with_guardrail("response with badword")
        assert ok is False and error

    def test_list_of_objects_is_chained_in_order(self):
        a = _agent([ProfanityFilter(), UpperCaser()])
        assert isinstance(a._guardrail_fn, GuardrailChain)
        assert [type(g).__name__ for g in a._guardrail_fn.guardrails] == [
            "ProfanityFilter",
            "UpperCaser",
        ]
        assert a._validate_input_with_guardrail("badword")[0] is False

    def test_object_tool_call_guardrail_is_wired(self):
        a = _agent(ProfanityFilter())
        assert a._tool_call_guardrails, "_tool_call_guardrails was never assigned"
        denied = a._check_tool_policy_and_guardrails("rm", {"path": "/"})
        assert isinstance(denied, dict) and denied.get("guardrail_denied") is True
        assert a._check_tool_policy_and_guardrails("ls", {"p": "/"}) == (None, {"p": "/"})


class TestUnsupportedGuardrailRaises:
    @pytest.mark.parametrize(
        "value",
        [123, 3.5, object(), [fn_guard], (fn_guard,), ProfanityFilter],
        ids=["int", "float", "object", "list_of_callable", "tuple_of_callable", "class"],
    )
    def test_unsupported_value_raises_typeerror(self, value):
        with pytest.raises(TypeError, match="not a supported guardrail"):
            _agent(value)

    def test_mixed_list_raises_typeerror(self):
        with pytest.raises(TypeError, match="may not mix guardrail objects"):
            _agent([ProfanityFilter(), fn_guard])


class TestExistingShapesUnchanged:
    def test_none_false_and_true(self):
        assert _agent(None)._guardrail_fn is None
        assert _agent(False)._guardrail_fn is None
        assert _agent(True)._guardrail_fn is None

    def test_plain_callable_passthrough(self):
        a = _agent(fn_guard)
        assert a._guardrail_fn is fn_guard
        assert a._tool_call_guardrails == []

    def test_string_stays_an_llm_output_guardrail(self):
        a = _agent("Ensure the answer is polite")
        assert type(a._guardrail_fn).__name__ == "LLMGuardrail"
        assert a._guardrail_fn._praison_output_only is True
        # Must NOT reach the tool-call hot path: that would fire an extra LLM
        # request before every tool call.
        assert a._tool_call_guardrails == []

    def test_guardrail_config_and_preset_list(self):
        a = _agent(GuardrailConfig(validator=fn_guard, max_retries=7))
        assert a._guardrail_fn is fn_guard and a.max_guardrail_retries == 7
        assert _agent(["strict"]).max_guardrail_retries == 5

    def test_guardrail_chain_still_passthrough(self):
        chain = GuardrailChain([ProfanityFilter()])
        assert _agent(chain)._guardrail_fn is chain

    def test_policy_strings_still_raise_valueerror(self):
        with pytest.raises(ValueError, match="not enforced"):
            _agent(["policy:strict"])
