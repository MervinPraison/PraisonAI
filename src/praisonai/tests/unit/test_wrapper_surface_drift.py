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


def test_tool_retry_policy_omitted_max_delay_uses_schema_default():
    # delay > 30s is schema-valid; the fallback must match the schema's 60s.
    kwargs = {}
    translate({"tool_retry_policy": {"delay": 45}}, kwargs, {}, "r")
    assert kwargs["tool_config"].retry_policy.max_delay_ms == 60000


def test_planning_tools_included_in_yaml_tool_discovery():
    from praisonai_code.tool_resolver import _yaml_tool_names

    cfg = {"roles": {"r": {"tools": ["a"], "planning_tools": ["plan_only"]}}}
    assert _yaml_tool_names(cfg) == {"a", "plan_only"}


def test_tool_retry_policy_delay_above_default_cap_is_clamped():
    kwargs = {}
    translate({"tool_retry_policy": {"delay": 120}}, kwargs, {}, "r")
    rp = kwargs["tool_config"].retry_policy
    assert rp.initial_delay_ms == 120000
    assert rp.max_delay_ms >= rp.initial_delay_ms


def test_tool_retry_policy_retry_on_forwarded():
    kwargs = {}
    translate({"tool_retry_policy": {"retry_on": ["timeout"]}}, kwargs, {}, "r")
    assert kwargs["tool_config"].retry_policy.retry_on == {"timeout"}


def test_cli_retry_on_survives_schema_round_trip():
    from praisonai.config.schema import AgentConfig

    cfg = AgentConfig(
        role="r", goal="g", backstory="b",
        tool_retry_policy=RetryPolicy(max_attempts=2, retry_on={"rate_limit"}),
    )
    kwargs = {}
    translate({"tool_retry_policy": cfg.tool_retry_policy}, kwargs, {}, "r")
    assert kwargs["tool_config"].retry_policy.retry_on == {"rate_limit"}


def test_planning_tools_merge_keeps_existing_planning_dict():
    tool = object()
    kwargs = {"planning": {"llm": "x", "auto_approve": True}}
    translate({"planning_tools": ["t"]}, kwargs, {"t": tool}, "r")
    assert kwargs["planning"] == {"llm": "x", "auto_approve": True, "tools": [tool]}
