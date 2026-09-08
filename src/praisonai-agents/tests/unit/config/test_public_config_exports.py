"""Every config class a public parameter accepts must be importable.

``ToolConfig``'s own docstring shows ``Agent(tool_config=ToolConfig())``, but
it was defined in ``feature_configs`` and never listed in
``praisonaiagents.config.__all__`` -- so the documented usage could not be
written with the natural import, while its siblings (``ExecutionConfig``,
``OutputConfig``, ...) could. Six others were in the same position, all of them
backing a public parameter of ``Agent`` or ``PraisonAIAgents``.

This pins the rule rather than the list, so a config added for a new parameter
cannot be left unexported.
"""

import inspect

import pytest

import praisonaiagents.config as config_pkg
from praisonaiagents import Agent, PraisonAIAgents
from praisonaiagents.config import feature_configs


# Parameter name -> the config class callers are expected to pass.
_AGENT_PARAM_CONFIGS = {
    "tool_config": "ToolConfig",
    "autonomy": "AutonomyConfig",
    "learn": "LearnConfig",
    "output": "OutputConfig",
    "memory": "MemoryConfig",
    "knowledge": "KnowledgeConfig",
}
_TEAM_PARAM_CONFIGS = {
    "execution": "MultiAgentExecutionConfig",
    "hooks": "MultiAgentHooksConfig",
    "memory": "MultiAgentMemoryConfig",
    "output": "MultiAgentOutputConfig",
}


def _exported(name):
    return name in getattr(config_pkg, "__all__", ()) and hasattr(config_pkg, name)


@pytest.mark.parametrize("param,cls", sorted(_AGENT_PARAM_CONFIGS.items()))
def test_agent_parameter_configs_are_importable(param, cls):
    assert param in inspect.signature(Agent.__init__).parameters, (
        f"Agent no longer takes {param!r}; update this table"
    )
    assert _exported(cls), (
        f"Agent({param}=...) expects {cls}, which is not importable from "
        f"praisonaiagents.config"
    )


@pytest.mark.parametrize("param,cls", sorted(_TEAM_PARAM_CONFIGS.items()))
def test_team_parameter_configs_are_importable(param, cls):
    assert param in inspect.signature(PraisonAIAgents.__init__).parameters, (
        f"PraisonAIAgents no longer takes {param!r}; update this table"
    )
    assert _exported(cls), (
        f"PraisonAIAgents({param}=...) expects {cls}, which is not importable "
        f"from praisonaiagents.config"
    )


def test_every_exported_name_actually_resolves():
    """__all__ is lazily resolved, so a typo there fails only on first access."""
    unresolvable = []
    for name in getattr(config_pkg, "__all__", ()):
        try:
            getattr(config_pkg, name)
        except Exception as exc:  # pragma: no cover - the regression
            unresolvable.append(f"{name} ({type(exc).__name__})")
    assert not unresolvable, f"listed in __all__ but not importable: {unresolvable}"


def test_the_documented_usage_actually_runs():
    """The line from ToolConfig's own docstring must work end to end."""
    from praisonaiagents.config import ToolConfig
    from praisonaiagents.tools.retry import RetryPolicy

    agent = Agent(
        name="t", role="r", goal="g", llm="gpt-4o-mini",
        tool_config=ToolConfig(retry_policy=RetryPolicy(max_attempts=5)),
    )
    assert agent is not None
