"""G-19: the output= config resolution of Agent.__init__ as a pure function.

Expected values were measured on main before the move. Reading the config's
fields and enabling the process-wide output modes stay in Agent.__init__.
"""
import pytest

from praisonaiagents import Agent
from praisonaiagents.config.agent_init import _is_file_path, resolve_agent_output
from praisonaiagents.config.feature_configs import OutputConfig


def _shape(cfg):
    return cfg.verbose, cfg.markdown, cfg.output_file


@pytest.mark.parametrize("value, env, expected", [
    (None, "", ((False, False, None), False)),
    (None, "verbose", ((True, True, None), False)),
    (None, "not-a-preset", ((False, False, None), False)),
    ("verbose", "", ((True, True, None), True)),
    ("VERBOSE", "", ((True, True, None), True)),
    ("out/file.txt", "", ((False, False, "out/file.txt"), True)),
    ("report.md", "", ((False, False, "report.md"), True)),
    ({"verbose": True}, "", ((True, False, None), True)),
])
def test_resolve_agent_output(value, env, expected):
    cfg, explicit = resolve_agent_output(value, env)
    assert (_shape(cfg), explicit) == expected


def test_output_config_passes_through():
    oc = OutputConfig(markdown=True)
    assert resolve_agent_output(oc, "") == (oc, True)


@pytest.mark.parametrize("value, expected", [
    ("a/b", True), ("a\\b", True), ("x.JSON", True), ("notes.md", True),
    ("verbose", False), ("silent", False),
])
def test_is_file_path(value, expected):
    assert _is_file_path(value) is expected


@pytest.mark.parametrize("value", [None, "verbose", "out/file.txt", OutputConfig(markdown=True),
                                   {"verbose": True}])
def test_agent_stores_what_the_resolver_returns(monkeypatch, value):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    agent = Agent(name="a", instructions="x", output=value)
    cfg, explicit = resolve_agent_output(value, Agent._get_env_output_mode())
    assert agent._has_explicit_output_config is explicit
    assert (agent.verbose, agent.markdown, agent._output_file) == _shape(cfg)
