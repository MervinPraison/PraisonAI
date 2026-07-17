"""Tests that the LLM retry loop honours the configured RetryBackoffConfig.

Verifies the retry depth is driven by ``RetryBackoffConfig.max_retries`` rather
than a hardcoded limit, while preserving the previous default when no retry
config is set.
"""

from praisonaiagents import Agent
from praisonaiagents.agent.retry_utils import RetryBackoffConfig


def test_default_retry_enabled_for_native_path():
    """A default Agent retries transient errors, matching the LiteLLM path.

    Previously the native path had ``_retry_config is None`` (no retry). The
    default now applies ``RetryBackoffConfig()`` (max_retries=3) so both LLM
    paths share the same default resilience.
    """
    agent = Agent(name="test", instructions="Be helpful")
    assert isinstance(agent._retry_config, RetryBackoffConfig)
    assert agent._max_retry_depth() == RetryBackoffConfig().max_retries


def test_retry_false_disables_retries():
    """retry=False opts out entirely (no retry config)."""
    agent = Agent(name="test", instructions="Be helpful", retry=False)
    assert agent._retry_config is None
    assert agent._max_retry_depth() == 2


def test_retry_depth_from_config_object():
    """max_retries from a RetryBackoffConfig drives the retry depth."""
    agent = Agent(
        name="test",
        instructions="Be helpful",
        retry=RetryBackoffConfig(max_retries=5),
    )
    assert agent._max_retry_depth() == 5


def test_retry_depth_from_config_dict():
    """A dict retry config is honoured too."""
    agent = Agent(
        name="test",
        instructions="Be helpful",
        retry={"max_retries": 4},
    )
    assert agent._max_retry_depth() == 4


def test_retry_depth_true_uses_config_default():
    """retry=True yields the RetryBackoffConfig default (3)."""
    agent = Agent(name="test", instructions="Be helpful", retry=True)
    assert agent._max_retry_depth() == RetryBackoffConfig().max_retries


def test_retry_depth_zero_is_respected():
    """A configured max_retries of 0 disables retries (not treated as unset)."""
    agent = Agent(
        name="test",
        instructions="Be helpful",
        retry=RetryBackoffConfig(max_retries=0),
    )
    assert agent._max_retry_depth() == 0
