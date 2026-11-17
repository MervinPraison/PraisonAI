"""G-19: the hooks= block of Agent.__init__ as a pure function.

Expected values were measured on main before the move, by building an Agent
for each input shape.
"""
import pytest

from praisonaiagents import Agent
from praisonaiagents.config.agent_init import resolve_agent_hooks
from praisonaiagents.config.feature_configs import HooksConfig
from praisonaiagents.hooks import HookRegistry


def mw(*a, **k):
    pass


def step(*a, **k):
    pass


def tc(*a, **k):
    pass


def _names(hooks):
    return [getattr(h, "__name__", type(h).__name__) for h in hooks]


def test_none_and_lists():
    assert resolve_agent_hooks(None) == (None, [], None, None)
    empty = []
    assert resolve_agent_hooks(empty)[0] is empty
    config, hooks, cb, reg = resolve_agent_hooks([mw])
    assert config == [mw] and _names(hooks) == ["mw"] and cb is None and reg is None


def test_hooks_config():
    hc = HooksConfig()
    assert resolve_agent_hooks(hc) == (hc, [], None, None)

    hc = HooksConfig(on_step=step)
    config, hooks, cb, _ = resolve_agent_hooks(hc)
    assert config is hc and cb is step and _names(hooks) == ["step"]

    hc = HooksConfig(on_tool_call=tc, middleware=[mw])
    config, hooks, cb, _ = resolve_agent_hooks(hc)
    assert cb is None and _names(hooks) == ["mw", "tc"]
    assert hc.middleware == [mw], "the caller's middleware list must not be mutated"


def test_dict_and_bare_registry():
    config, hooks, cb, _ = resolve_agent_hooks({"on_step": step})
    assert isinstance(config, HooksConfig) and cb is step and _names(hooks) == ["step"]
    assert resolve_agent_hooks(HookRegistry()) == (None, [], None, None)


@pytest.mark.parametrize("value", [
    None, [], [mw], HooksConfig(on_step=step),
    HooksConfig(on_tool_call=tc, middleware=[mw]), {"on_step": step}, HookRegistry(),
])
def test_agent_stores_what_the_resolver_returns(monkeypatch, value):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    agent = Agent(name="a", instructions="x", hooks=value)
    config, hooks, cb, reg = resolve_agent_hooks(value)
    assert _names(agent._hooks) == _names(hooks)
    assert agent.step_callback is cb
    assert type(agent._hooks_config) is type(config)
    assert agent._hooks_registry_param is (reg if reg is not None else value)
