"""G-19: the execution= config resolution of Agent.__init__ as a pure function.

Expected values were measured on main before the move. Reading the config's
fields into Agent attributes stays in Agent.__init__.
"""
import pytest

from praisonaiagents import Agent
from praisonaiagents.config.agent_init import resolve_agent_execution
from praisonaiagents.config.feature_configs import ExecutionConfig


def _limits(config):
    return (config.max_iter, config.max_rpm, config.max_execution_time, config.max_retry_limit)


@pytest.mark.parametrize("value, limits", [
    (None, (20, None, None, 2)),
    ("fast", (10, None, None, 1)),
    ("FAST", (10, None, None, 1)),
    ({"max_iter": 7, "max_rpm": 9}, (7, 9, None, 2)),
    (True, (20, None, None, 2)),
])
def test_resolve_agent_execution(value, limits):
    config = resolve_agent_execution(value)
    assert isinstance(config, ExecutionConfig)
    assert _limits(config) == limits


def test_execution_config_passes_through():
    ec = ExecutionConfig(max_iter=5)
    assert resolve_agent_execution(ec) is ec


@pytest.mark.parametrize("value", [None, ExecutionConfig(max_iter=5), "fast", "FAST",
                                   {"max_iter": 7, "max_rpm": 9}, False, True])
def test_agent_limits_match_the_resolver(monkeypatch, value):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    agent = Agent(name="a", instructions="x", execution=value)
    config = resolve_agent_execution(value) or ExecutionConfig()
    assert (agent.max_iter, agent.max_rpm, agent.max_execution_time,
            agent.max_retry_limit) == _limits(config)
