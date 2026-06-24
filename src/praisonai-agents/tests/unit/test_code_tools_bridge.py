"""Tests for code-execution-with-tools (code mode) bridge.

Verifies that model-generated code can call registered tools through the
ToolProxy bridge, honouring the allow-list and the approval framework, and
that disallowed/unregistered tools are rejected.
"""

import pytest

from praisonaiagents.tools.registry import ToolRegistry
from praisonaiagents.tools.tool_proxy import ToolProxy, build_tool_namespace
from praisonaiagents.tools.python_tools import execute_code_with_tools


@pytest.fixture
def registry():
    reg = ToolRegistry()

    def fetch(url):
        return {"a": 1, "b": 2, "c": 3}[url]

    def double(x):
        return x * 2

    reg.register(fetch, name="fetch")
    reg.register(double, name="double")
    return reg


def test_proxy_calls_allowed_tool(registry):
    proxy = ToolProxy(["fetch"], registry=registry)
    assert proxy.fetch(url="a") == 1


def test_proxy_rejects_disallowed_tool(registry):
    proxy = ToolProxy(["fetch"], registry=registry)
    with pytest.raises(PermissionError):
        proxy.double(x=2)


def test_proxy_rejects_unregistered_tool(registry):
    proxy = ToolProxy(["ghost"], registry=registry)
    with pytest.raises(NameError):
        proxy.ghost()


def test_proxy_is_read_only(registry):
    proxy = ToolProxy(["fetch"], registry=registry)
    with pytest.raises(AttributeError):
        proxy.fetch = lambda **kw: None


def test_build_tool_namespace_skips_unregistered(registry):
    ns = build_tool_namespace(["fetch", "ghost"], registry=registry)
    assert "fetch" in ns
    assert "ghost" not in ns


def test_multi_step_pipeline_in_one_call(registry):
    code = (
        "vals = [fetch(u) for u in ['a', 'b', 'c']]\n"
        "best = max(double(v) for v in vals)\n"
        "best\n"
    )
    result = execute_code_with_tools(
        code, allowed_tools=["fetch", "double"], registry=registry
    )
    assert result["success"] is True
    assert result["result"] == 6


def test_positional_and_keyword_args(registry):
    code = "fetch('a')\n"
    result = execute_code_with_tools(
        code, allowed_tools=["fetch"], registry=registry
    )
    assert result["success"] is True
    assert result["result"] == 1


def test_tools_namespace_form(registry):
    code = "tools.fetch(url='b')\n"
    result = execute_code_with_tools(
        code, allowed_tools=["fetch"], registry=registry
    )
    assert result["success"] is True
    assert result["result"] == 2


def test_disallowed_tool_from_code_fails(registry):
    code = "print(double(x=1))\n"
    result = execute_code_with_tools(
        code, allowed_tools=["fetch"], registry=registry
    )
    assert result["success"] is False


def test_no_tools_when_empty_allowlist(registry):
    code = "print(fetch(url='a'))\n"
    result = execute_code_with_tools(code, allowed_tools=[], registry=registry)
    assert result["success"] is False


def test_imports_still_blocked(registry):
    code = "import os\nprint(os.getcwd())\n"
    result = execute_code_with_tools(
        code, allowed_tools=["fetch"], registry=registry
    )
    assert result["success"] is False


def test_approval_gate_denies(registry):
    from praisonaiagents.approval import (
        add_approval_requirement,
        remove_approval_requirement,
        set_approval_callback,
        ApprovalDecision,
    )

    add_approval_requirement("fetch", "high")
    set_approval_callback(
        lambda function_name, arguments, risk_level: ApprovalDecision(
            approved=False, reason="denied by test"
        )
    )
    try:
        proxy = ToolProxy(["fetch"], registry=registry)
        with pytest.raises(PermissionError):
            proxy.fetch(url="a")
    finally:
        set_approval_callback(None)
        remove_approval_requirement("fetch")


def test_registry_not_exposed_via_attribute(registry):
    proxy = ToolProxy(["fetch"], registry=registry)
    with pytest.raises(AttributeError):
        _ = proxy._registry
    with pytest.raises(AttributeError):
        _ = proxy._allowed


def test_registry_bypass_blocked_from_code(registry):
    code = "r = tools._registry\nr.get('double')()\n"
    result = execute_code_with_tools(
        code, allowed_tools=["fetch"], registry=registry
    )
    assert result["success"] is False


def test_reserved_tools_name_rejected(registry):
    with pytest.raises(ValueError):
        execute_code_with_tools(
            "1\n", allowed_tools=["tools"], registry=registry
        )


def test_positional_args_visible_to_approval(registry):
    from praisonaiagents.approval import (
        add_approval_requirement,
        remove_approval_requirement,
        set_approval_callback,
        ApprovalDecision,
    )

    seen = {}

    def _cb(function_name, arguments, risk_level):
        seen["args"] = dict(arguments)
        return ApprovalDecision(approved=True, reason="ok")

    add_approval_requirement("fetch", "high")
    set_approval_callback(_cb)
    try:
        proxy = ToolProxy(["fetch"], registry=registry)
        assert proxy.fetch("a") == 1
        assert seen["args"].get("url") == "a"
    finally:
        set_approval_callback(None)
        remove_approval_requirement("fetch")


def test_execution_config_flags():
    from praisonaiagents.config.feature_configs import ExecutionConfig

    cfg = ExecutionConfig(code_tools=True, code_tools_allow=["fetch"])
    assert cfg.code_tools is True
    assert cfg.code_tools_allow == ["fetch"]
    d = cfg.to_dict()
    assert d["code_tools"] is True
    assert d["code_tools_allow"] == ["fetch"]
    restored = ExecutionConfig.from_dict(d)
    assert restored.code_tools is True
    assert restored.code_tools_allow == ["fetch"]
