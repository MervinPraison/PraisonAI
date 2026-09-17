"""Tests for code-execution-with-tools (code mode) bridge.

Verifies that model-generated code can call registered tools through the
ToolProxy bridge, honouring the allow-list and the approval framework, and
that disallowed/unregistered tools are rejected.
"""

import pytest

from praisonaiagents.tools.registry import ToolRegistry
from praisonaiagents.tools.tool_proxy import (
    ToolProxy,
    build_tool_namespace,
    CodeToolBridge,
    serve_tool_call,
)
from praisonaiagents.tools.python_tools import execute_code_with_tools


@pytest.fixture(autouse=True)
def _clean_approval_context():
    """Every test here starts with nothing pre-approved.

    Approvals are remembered in a contextvar so a granted tool is not re-asked.
    That is correct behaviour and fatal for these tests: an approval left by an
    earlier test made a denial test see an already-approved tool and not raise
    (DID NOT RAISE PermissionError), and made the every-call gate test count one
    callback invocation instead of two. Both passed alone and failed under a
    random seed.
    """
    from praisonaiagents.approval import clear_approval_context

    clear_approval_context()
    yield
    clear_approval_context()


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


def test_init_reinitialization_bypass_blocked(registry):
    # Sandboxed code must not be able to call tools.__init__([...]) to re-bind
    # the proxy's allow-list/registry and reach a disallowed tool.
    code = (
        "tools.__init__(['double'])\n"
        "tools.double(x=2)\n"
    )
    result = execute_code_with_tools(
        code, allowed_tools=["fetch"], registry=registry
    )
    assert result["success"] is False


def test_init_not_exposed_on_proxy(registry):
    proxy = ToolProxy(["fetch"], registry=registry)
    # __init__ access is treated as a tool-name lookup and rejected, not the
    # bound initializer.
    with pytest.raises((AttributeError, PermissionError, NameError)):
        proxy.__init__(["double"])


def test_approval_gate_required_for_every_call(registry):
    # In code mode a first approval must NOT silently unlock later calls to the
    # same tool. The approval callback must fire for every invocation.
    from praisonaiagents.approval import (
        add_approval_requirement,
        remove_approval_requirement,
        set_approval_callback,
        clear_approval_context,
        ApprovalDecision,
    )

    # The registry remembers approvals for the life of the process, so a grant
    # from an earlier test in the same run satisfied one of the two calls below
    # and this counted 1. The precondition of "every call is gated" is that
    # nothing is pre-approved, so establish it rather than inherit it.
    from praisonaiagents.approval import get_approval_registry
    get_approval_registry().clear_approved()

    calls = {"count": 0}

    def _cb(function_name, arguments, risk_level):
        calls["count"] += 1
        return ApprovalDecision(approved=True, reason="ok")

    add_approval_requirement("fetch", "high")
    set_approval_callback(_cb)
    try:
        proxy = ToolProxy(["fetch"], registry=registry)
        proxy.fetch(url="a")
        proxy.fetch(url="b")
        assert calls["count"] == 2
    finally:
        set_approval_callback(None)
        remove_approval_requirement("fetch")
        clear_approval_context()


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


# ---------------------------------------------------------------------------
# Isolated (bridged) tool-calling path — CodeToolBridge + serve_tool_call
# ---------------------------------------------------------------------------


class _RecordingBridge:
    """Minimal CodeToolBridge that services calls via serve_tool_call.

    Stands in for a real sandbox transport (subprocess/Docker): instead of
    crossing a process boundary it invokes serve_tool_call directly, which is
    exactly what a transport's parent-side handler must do. Critically, it uses
    ONLY the caller-supplied invocation policy forwarded to ``run_code`` — it
    keeps no allow-list/registry of its own — so the test proves the caller's
    policy (not a bridge default) governs the isolated call.
    """

    def __init__(self):
        self.ran = None
        self.seen = None

    def run_code(
        self,
        code,
        *,
        allowed_tools=(),
        registry=None,
        timeout=30,
        max_output_size=10000,
    ):
        self.ran = code
        self.seen = {
            "allowed_tools": list(allowed_tools),
            "registry": registry,
            "timeout": timeout,
            "max_output_size": max_output_size,
        }
        # Emulate one tool call the "child" would have marshalled across, gated
        # by the caller's forwarded policy — never a bridge-owned default.
        value = serve_tool_call(
            "fetch", ["a"], {}, allowed=allowed_tools, registry=registry
        )
        return {
            "result": value,
            "stdout": str(value),
            "stderr": "",
            "success": True,
        }


def test_bridge_satisfies_protocol(registry):
    bridge = _RecordingBridge()
    assert isinstance(bridge, CodeToolBridge)


def test_execute_with_tools_dispatches_to_bridge(registry):
    bridge = _RecordingBridge()
    result = execute_code_with_tools(
        "print(fetch('a'))",
        allowed_tools=["fetch"],
        registry=registry,
        bridge=bridge,
    )
    assert bridge.ran == "print(fetch('a'))"
    assert result["success"] is True
    assert result["result"] == 1


def test_bridge_receives_caller_invocation_policy_and_limits(registry):
    # The caller's allow-list, registry and limits must cross the isolation
    # boundary so the transport gates tool calls by exactly what THIS caller
    # authorised — not a bridge-owned default. Regression guard for a bridge
    # that would otherwise service calls under a broader/weaker policy.
    bridge = _RecordingBridge()
    execute_code_with_tools(
        "fetch('a')",
        allowed_tools=["fetch"],
        registry=registry,
        timeout=7,
        max_output_size=123,
        bridge=bridge,
    )
    assert bridge.seen["allowed_tools"] == ["fetch"]
    assert bridge.seen["registry"] is registry
    assert bridge.seen["timeout"] == 7
    assert bridge.seen["max_output_size"] == 123


def test_bridge_enforces_forwarded_allowlist(registry):
    # A tool NOT on the caller's forwarded allow-list must be rejected by the
    # parent-side gate even though the bridge itself imposes no policy.
    class _CallsDisallowed(_RecordingBridge):
        def run_code(self, code, *, allowed_tools=(), registry=None,
                     timeout=30, max_output_size=10000):
            serve_tool_call(
                "double", [2], {}, allowed=allowed_tools, registry=registry
            )
            return {"result": None, "stdout": "", "stderr": "", "success": True}

    bridge = _CallsDisallowed()
    with pytest.raises(PermissionError):
        execute_code_with_tools(
            "double(2)",
            allowed_tools=["fetch"],
            registry=registry,
            bridge=bridge,
        )


def test_bridge_none_uses_in_process_path(registry):
    # Sanity: omitting bridge keeps the original in-process behaviour.
    result = execute_code_with_tools(
        "fetch('a')\n", allowed_tools=["fetch"], registry=registry
    )
    assert result["success"] is True
    assert result["result"] == 1


def test_serve_tool_call_runs_allowed_tool(registry):
    assert serve_tool_call("fetch", ["a"], {}, allowed=["fetch"], registry=registry) == 1


def test_serve_tool_call_rejects_disallowed(registry):
    with pytest.raises(PermissionError):
        serve_tool_call("double", [2], {}, allowed=["fetch"], registry=registry)


def test_serve_tool_call_rejects_unregistered(registry):
    with pytest.raises(NameError):
        serve_tool_call("ghost", [], {}, allowed=["ghost"], registry=registry)


# ---------------------------------------------------------------------------
# Shipped default transport — LocalProcessBridge (subprocess + bridged tools)
# ---------------------------------------------------------------------------


def test_local_process_bridge_satisfies_protocol():
    from praisonaiagents.tools.tool_proxy import LocalProcessBridge

    assert isinstance(LocalProcessBridge(), CodeToolBridge)


def test_isolated_multi_step_pipeline_over_bridge(registry):
    from praisonaiagents.tools.tool_proxy import LocalProcessBridge

    code = (
        "vals = [fetch(u) for u in ['a', 'b', 'c']]\n"
        "best = max(double(v) for v in vals)\n"
        "best\n"
    )
    result = execute_code_with_tools(
        code,
        allowed_tools=["fetch", "double"],
        registry=registry,
        bridge=LocalProcessBridge(),
    )
    assert result["success"] is True
    assert result["result"] == "6"


def test_isolated_stdout_only_returns(registry):
    from praisonaiagents.tools.tool_proxy import LocalProcessBridge

    code = "print('answer:', fetch('a') + fetch('b'))\n"
    result = execute_code_with_tools(
        code,
        allowed_tools=["fetch"],
        registry=registry,
        bridge=LocalProcessBridge(),
    )
    assert result["success"] is True
    assert "answer: 3" in result["stdout"]


def test_isolated_rejects_disallowed_bare_name(registry):
    # A disallowed tool is simply not present in the isolated child's namespace,
    # so the script fails outright (stronger than the in-process path: the name
    # never even resolves to a proxy).
    from praisonaiagents.tools.tool_proxy import LocalProcessBridge

    result = execute_code_with_tools(
        "double(2)\n",
        allowed_tools=["fetch"],
        registry=registry,
        bridge=LocalProcessBridge(),
    )
    assert result["success"] is False


def test_isolated_rejects_disallowed_via_tools_namespace(registry):
    # The tools.<name> form DOES cross the boundary; the parent-side gate must
    # reject it (authoritative), surfacing as PermissionError to the caller.
    from praisonaiagents.tools.tool_proxy import LocalProcessBridge

    with pytest.raises(PermissionError):
        execute_code_with_tools(
            "tools.double(x=2)\n",
            allowed_tools=["fetch"],
            registry=registry,
            bridge=LocalProcessBridge(),
        )


def test_isolated_blocks_imports(registry):
    from praisonaiagents.tools.tool_proxy import LocalProcessBridge

    result = execute_code_with_tools(
        "import os\nprint(os.getcwd())\n",
        allowed_tools=["fetch"],
        registry=registry,
        bridge=LocalProcessBridge(),
    )
    assert result["success"] is False


def test_build_code_execution_tools_isolated_mode(registry):
    from praisonaiagents.tools.python_tools import build_code_execution_tools

    tools = build_code_execution_tools(
        code_mode="isolated",
        allowed_tools=["fetch"],
        registry=registry,
    )
    assert len(tools) == 1
    assert tools[0].__name__ == "execute_code"


def test_build_code_execution_tools_rejects_unknown_mode():
    from praisonaiagents.tools.python_tools import build_code_execution_tools

    with pytest.raises(ValueError):
        build_code_execution_tools(code_mode="bogus")


def test_execution_config_accepts_isolated():
    from praisonaiagents.config.feature_configs import ExecutionConfig

    cfg = ExecutionConfig(code_execution=True, code_mode="isolated")
    assert cfg.code_mode == "isolated"
    assert ExecutionConfig.from_dict(cfg.to_dict()).code_mode == "isolated"


def test_execution_config_rejects_unknown_code_mode():
    from praisonaiagents.config.feature_configs import ExecutionConfig

    with pytest.raises(ValueError):
        ExecutionConfig(code_execution=True, code_mode="bogus")


def test_serve_tool_call_honours_approval_gate(registry):
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
        with pytest.raises(PermissionError):
            serve_tool_call(
                "fetch", ["a"], {}, allowed=["fetch"], registry=registry
            )
    finally:
        set_approval_callback(None)
        remove_approval_requirement("fetch")


def test_isolated_blocks_introspection_escape(registry):
    # A dunder-attribute traversal that could recover unrestricted builtins must
    # be rejected before the child runs (same posture as the in-process path).
    from praisonaiagents.tools.tool_proxy import LocalProcessBridge

    result = execute_code_with_tools(
        "type(tools).__subclasses__()\n",
        allowed_tools=["fetch"],
        registry=registry,
        bridge=LocalProcessBridge(),
    )
    assert result["success"] is False


def test_isolated_ordinary_tool_error_is_not_reraised(registry):
    # An allowed tool raising an ordinary error must NOT escape the bridge as an
    # exception; it must return a structured success=False result.
    from praisonaiagents.tools.tool_proxy import LocalProcessBridge

    reg = ToolRegistry()

    def boom():
        raise ValueError("kaboom")

    reg.register(boom, name="boom")
    result = execute_code_with_tools(
        "boom()\n",
        allowed_tools=["boom"],
        registry=reg,
        bridge=LocalProcessBridge(),
    )
    assert result["success"] is False
    assert "kaboom" in (result.get("stderr") or "")


def test_serve_tool_call_awaits_async_tool(registry):
    # An async def tool must be awaited to its value, not returned as a coroutine.
    from praisonaiagents.tools.tool_proxy import serve_tool_call

    reg = ToolRegistry()

    async def afetch(url):
        return {"a": 10}[url]

    reg.register(afetch, name="afetch")
    value = serve_tool_call("afetch", ["a"], {}, allowed=["afetch"], registry=reg)
    assert value == 10


def test_scoped_registry_does_not_discover_plugins():
    # A discovery-disabled registry must NOT auto-discover global plugins on a
    # missing-name lookup: the agent-scoped tool boundary is authoritative.
    reg = ToolRegistry(discovery_enabled=False)
    called = {"n": 0}

    def _spy():
        called["n"] += 1
        return 0

    reg.discover_plugins = _spy  # type: ignore[assignment]
    assert reg.get("some_installed_plugin") is None
    assert called["n"] == 0


def test_isolated_startup_error_returns_structured_failure(registry, monkeypatch):
    # A subprocess launch failure must surface as the documented failure dict,
    # not a raw exception on the caller.
    import subprocess

    from praisonaiagents.tools.tool_proxy import LocalProcessBridge

    def _boom(*a, **k):
        raise OSError("cannot start process")

    monkeypatch.setattr(subprocess, "Popen", _boom)
    result = LocalProcessBridge().run_code(
        "fetch('a')\n", allowed_tools=["fetch"], registry=registry
    )
    assert result["success"] is False
    assert "could not start child" in (result.get("stderr") or "")
