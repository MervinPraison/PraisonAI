"""G-19: the guardrails= block of Agent.__init__ as a pure function.

Expected values were measured on main before the move, including every
fail-loud check (a guardrail that would never run must raise, not be dropped).
"""
import pytest

from praisonaiagents import Agent
from praisonaiagents.config.agent_init import resolve_agent_guardrails
from praisonaiagents.config.feature_configs import GuardrailConfig
from praisonaiagents.guardrails import GuardrailChain


def check(output):
    return True, output


class _Obj:
    def validate_output(self, output):
        return True, output


def _r(value):
    return resolve_agent_guardrails(value, None, 3)


@pytest.fixture(autouse=True)
def _no_config_defaults(monkeypatch):
    monkeypatch.setattr("praisonaiagents.config.loader.apply_config_defaults",
                        lambda name, value, cls: value)


@pytest.mark.parametrize("value", [None, False, []])
def test_no_guardrails(value):
    config, guardrail, retries = _r(value)
    assert config is None and guardrail is None and retries == 3


def test_callable_string_and_config():
    assert _r(check) == (check, check, 3)
    assert _r("Must be polite") == ("Must be polite", "Must be polite", 3)
    gc = GuardrailConfig(validator=check, max_retries=5)
    assert _r(gc) == (gc, check, 5)
    gc = GuardrailConfig(llm_validator="Be nice")
    assert _r(gc)[1:] == ("Be nice", 3)


def test_guardrail_objects_become_a_chain():
    config, guardrail, _ = _r(_Obj())
    assert isinstance(config, GuardrailChain) and guardrail is config
    config, _, _ = _r([_Obj(), _Obj()])
    assert isinstance(config, GuardrailChain)


@pytest.mark.parametrize("value, error", [
    (["policy:strict"], ValueError),
    ([_Obj(), 42], TypeError),
    (GuardrailConfig(on_fail="skip"), ValueError),
    (42, TypeError),
])
def test_fail_loud(value, error):
    with pytest.raises(error):
        _r(value)


def test_policy_fields_fail_loud():
    gc = GuardrailConfig()
    gc.policy = "strict"
    with pytest.raises(ValueError, match="not enforced"):
        _r(gc)


def test_config_default_applies_only_when_not_given(monkeypatch):
    monkeypatch.setattr("praisonaiagents.config.loader.apply_config_defaults",
                        lambda name, value, cls: GuardrailConfig(validator=check) if value is None else value)
    assert _r(None)[1] is check
    assert _r(False)[0] is None


@pytest.mark.parametrize("value", [None, check, "Must be polite", GuardrailConfig(validator=check, max_retries=5)])
def test_agent_stores_what_the_resolver_returns(monkeypatch, value):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    agent = Agent(name="a", instructions="x", guardrails=value)
    config, guardrail, retries = _r(value)
    assert agent._guardrails_config is config
    assert (agent.guardrail, agent.max_guardrail_retries) == (guardrail, retries)
