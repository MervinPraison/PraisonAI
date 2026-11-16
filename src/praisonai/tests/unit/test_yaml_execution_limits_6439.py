"""agents.yaml execution limits reach core Agent via ExecutionConfig (#6439)."""
import pytest

pytest.importorskip("praisonaiagents")

from praisonai.framework_adapters.praisonai_adapter import PraisonAIAdapter
from praisonaiagents.config.feature_configs import ExecutionConfig


def _build_agent(details):
    adapter = PraisonAIAdapter.__new__(PraisonAIAdapter)
    adapter._format_template = lambda v, topic="": v
    config = {"roles": {"a": {"role": "A", "goal": "g", "backstory": "b",
                              "tools": [], **details}}}
    agents, _ = adapter._build_agents_and_tasks(
        config, "topic", {}, None, None, "gpt-4o-mini",
    )
    return agents["a"] if isinstance(agents, dict) else agents[0]


def test_max_execution_time_reaches_agent():
    agent = _build_agent({"max_execution_time": 30})
    assert agent.max_execution_time == 30


def test_omitted_limits_keep_core_defaults():
    agent = _build_agent({})
    default = ExecutionConfig()
    assert agent.max_execution_time == default.max_execution_time
    assert agent.max_retry_limit == default.max_retry_limit


def test_limits_merge_with_execution_mapping():
    kwargs = {}
    PraisonAIAdapter._translate_execution(
        {"max_iter": 7, "execution": {"max_rpm": 5, "max_iter": 99}}, kwargs
    )
    cfg = kwargs["execution"]
    assert isinstance(cfg, ExecutionConfig)
    assert (cfg.max_iter, cfg.max_rpm) == (7, 5)


def test_limits_merge_with_execution_config_and_preset():
    kwargs = {}
    PraisonAIAdapter._translate_execution(
        {"max_retry_limit": 4, "execution": ExecutionConfig(max_rpm=3)}, kwargs
    )
    assert (kwargs["execution"].max_retry_limit, kwargs["execution"].max_rpm) == (4, 3)

    kwargs = {}
    PraisonAIAdapter._translate_execution(
        {"max_execution_time": 12, "execution": "fast"}, kwargs
    )
    assert kwargs["execution"].max_execution_time == 12
    assert kwargs["execution"].max_iter == 10  # from the "fast" preset


def test_no_limits_forwards_execution_as_is():
    kwargs = {}
    PraisonAIAdapter._translate_execution({"execution": "fast"}, kwargs)
    assert kwargs["execution"] == "fast"
    kwargs = {}
    PraisonAIAdapter._translate_execution({}, kwargs)
    assert "execution" not in kwargs
