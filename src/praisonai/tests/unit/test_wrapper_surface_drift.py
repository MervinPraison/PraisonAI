"""Regression tests for #6281: YAML fields silently dropped before core Agent."""

import pytest

from praisonai.framework_adapters.praisonai_adapter import PraisonAIAdapter
from praisonaiagents.config.feature_configs import PlanningConfig, ToolConfig, WebConfig
from praisonaiagents.tools.retry import RetryPolicy


translate = PraisonAIAdapter._translate_tool_planning_web


def test_tool_retry_policy_dict_becomes_tool_config():
    kwargs = {}
    translate(
        {"tool_retry_policy": {"max_attempts": 5, "delay": 2.0, "backoff_factor": 3.0, "max_delay": 10}},
        kwargs, {}, "r",
    )
    tc = kwargs["tool_config"]
    assert isinstance(tc, ToolConfig)
    assert isinstance(tc.retry_policy, RetryPolicy)
    assert tc.retry_policy.max_attempts == 5
    assert tc.retry_policy.initial_delay_ms == 2000
    assert tc.retry_policy.backoff_factor == 3.0
    assert tc.retry_policy.max_delay_ms == 10000


def test_planning_tools_resolved_from_tools_dict():
    def add_memory():
        return "ok"

    kwargs = {"planning": True}
    translate({"planning_tools": ["add_memory"]}, kwargs, {"add_memory": add_memory}, "r")
    assert isinstance(kwargs["planning"], PlanningConfig)
    assert kwargs["planning"].tools == [add_memory]


def test_planning_tools_ignored_when_planning_disabled():
    kwargs = {}
    translate({"planning_tools": ["x"]}, kwargs, {"x": object()}, "r")
    assert "planning" not in kwargs


@pytest.mark.parametrize(
    "web,web_fetch,search,fetch",
    [(True, False, True, False), (None, True, False, True), (True, True, True, True)],
)
def test_web_fetch_mapped_to_web_config(web, web_fetch, search, fetch):
    kwargs = {} if web is None else {"web": web}
    translate({"web_fetch": web_fetch}, kwargs, {}, "r")
    assert isinstance(kwargs["web"], WebConfig)
    assert (kwargs["web"].search, kwargs["web"].fetch) == (search, fetch)


def test_web_fetch_false_without_web_is_noop():
    kwargs = {}
    translate({"web_fetch": False}, kwargs, {}, "r")
    assert "web" not in kwargs


def test_scheduler_fails_closed_on_dropped_approval():
    from praisonai.scheduler.yaml_loader import create_agent_from_config

    with pytest.raises(ValueError, match="approval"):
        create_agent_from_config({
            "name": "a", "role": "r", "instructions": "i",
            "approval": {"backend": "console"},
        })


def test_scheduler_forwards_llm():
    from praisonai.scheduler.yaml_loader import create_agent_from_config

    agent = create_agent_from_config({
        "name": "a", "role": "r", "instructions": "i", "llm": "gpt-4o",
    })
    assert "gpt-4o" in str(getattr(agent, "llm", ""))
