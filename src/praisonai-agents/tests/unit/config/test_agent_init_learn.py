"""G-19: the learn= block of Agent.__init__ as a pure function.

Expected values were measured on main before the move.
"""
import pytest

from praisonaiagents import Agent
from praisonaiagents.config.agent_init import resolve_agent_learn
from praisonaiagents.config.feature_configs import LearnConfig, MemoryConfig


def _shape(cfg):
    return None if cfg is None else (cfg.mode.name, cfg.nudge_interval, cfg.nudge_min_tool_iters)


@pytest.mark.parametrize("learn, expected", [
    (None, None),
    (False, None),
    (True, ("AGENTIC", 10, 0)),
    (LearnConfig(), ("DISABLED", 0, 3)),
    ({"nudge_interval": 3}, ("DISABLED", 3, 3)),
    (" AGENTIC ", ("AGENTIC", 0, 3)),
    ("propose", ("PROPOSE", 0, 3)),
    ("disabled", None),
    ("bogus", None),
    (42, None),
])
def test_top_level_learn(learn, expected):
    cfg, _memory, _auto = resolve_agent_learn(learn, None, "keep", None)
    assert _shape(cfg) == expected


def test_learn_config_passes_through():
    lc = LearnConfig()
    assert resolve_agent_learn(lc, None, "keep", None)[0] is lc


def test_memory_learn_fallback():
    assert _shape(resolve_agent_learn(None, MemoryConfig(learn=True), "keep", None)[0]) == ("AGENTIC", 0, 3)
    assert _shape(resolve_agent_learn(None, MemoryConfig(learn={"nudge_interval": 4}), "keep", None)[0]) == ("DISABLED", 4, 3)
    # Top-level learn= wins over memory.learn.
    assert resolve_agent_learn(False, MemoryConfig(learn=True), "keep", None)[0] is None


def test_memory_and_auto_memory():
    cfg, memory, auto = resolve_agent_learn(True, None, None, None)
    assert memory == {"learn": cfg.to_dict()} and auto is True
    given = {"provider": "file"}
    cfg, memory, _ = resolve_agent_learn(True, None, given, None)
    assert memory is given and given["learn"] == cfg.to_dict()
    # An explicit auto_memory wins; other memory values are left alone.
    assert resolve_agent_learn(True, None, "keep", False)[1:] == ("keep", False)
    assert resolve_agent_learn("agentic", None, None, None)[2] is None


@pytest.mark.parametrize("learn", [None, False, "disabled", 42])
def test_agent_stores_what_the_resolver_returns(monkeypatch, learn):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    agent = Agent(name="a", instructions="x", learn=learn)
    assert _shape(agent._learn_config) == _shape(resolve_agent_learn(learn, None, None, None)[0])
