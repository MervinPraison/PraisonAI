"""Agent(auth=...) must reach the LLM on every construction branch.

Regression tests for the bug where `auth=` was forwarded into llm_config on the
provider/model, dict and base_url branches but dropped by the final `else`, and
where `self.auth` was never assigned so clone_for_channel() lost it entirely.
"""
import pytest
from unittest.mock import patch

from praisonaiagents import Agent
from praisonaiagents.auth.subscription.protocols import (
    AuthError,
    SubscriptionCredentials,
)

FAKE_CREDS = SubscriptionCredentials(
    api_key="sk-ant-oat-fake",
    base_url="https://api.anthropic.com",
    headers={"x-app": "cli"},
    auth_scheme="bearer",
    source="unit-test",
)


@pytest.fixture
def resolved():
    with patch(
        "praisonaiagents.auth.resolve_subscription_credentials",
        return_value=FAKE_CREDS,
    ) as m:
        yield m


@pytest.mark.parametrize(
    "kwargs",
    [
        {"llm": "claude-sonnet-4-5"},          # bare name -> final `else` branch
        {"llm": "anthropic/claude-sonnet-4-5"},  # provider/model branch
        {"llm": {"model": "anthropic/claude-sonnet-4-5"}},  # dict branch
        {"llm": "llama3.2", "base_url": "http://localhost:11434"},  # base_url branch
        {},                                     # no model at all
    ],
)
def test_auth_reaches_the_llm_on_every_branch(resolved, kwargs):
    agent = Agent(name="t", auth="claude-code", **kwargs)
    assert agent.auth == "claude-code"
    assert agent.llm_instance is not None, "auth= must force an LLM instance"
    assert agent.llm_instance._auth_provider_id == "claude-code"


def test_auth_survives_clone_for_channel(resolved):
    agent = Agent(name="t", llm="anthropic/claude-sonnet-4-5", auth="claude-code")
    assert agent.clone_for_channel().auth == "claude-code"


def test_bare_auth_does_not_default_to_an_openai_model(resolved):
    # A claude-code seat only works against api.anthropic.com; defaulting to
    # gpt-4o-mini would ship the OAuth token to the wrong vendor.
    assert Agent(name="t", auth="claude-code").llm.startswith("anthropic/")


def test_unknown_provider_raises_from_the_constructor():
    with pytest.raises(AuthError) as exc:
        Agent(name="t", llm="gpt-4o-mini", auth="nonexistent-provider")
    assert "Unknown subscription provider" in str(exc.value)


def test_no_auth_keeps_the_plain_openai_path():
    agent = Agent(name="t", llm="gpt-4o-mini")
    assert agent.auth is None
    assert agent.llm_instance is None


def test_responses_api_params_carry_subscription_credentials(resolved):
    from praisonaiagents.llm.llm import LLM

    llm = LLM(model="gpt-4o", auth="claude-code")
    assert llm._supports_responses_api()
    params = llm._build_responses_params([{"role": "user", "content": "hi"}])
    assert params["api_key"] == "sk-ant-oat-fake"
    assert params["base_url"] == "https://api.anthropic.com"
    assert params["extra_headers"]["x-app"] == "cli"
