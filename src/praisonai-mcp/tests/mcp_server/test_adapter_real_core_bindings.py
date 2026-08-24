"""
Regression tests for adapter → core API bindings (issue #4304).

The knowledge/hooks/session/tools/eval/workflow/audio/guardrails/ocr/a2a/
containers/skills/realtime adapters called core/wrapper APIs that did not
exist or had different signatures, so they failed at attribute lookup or
argument binding *before any I/O*. 24 of them returned ``"isError": false``
and 9 reported an installed, working module as "not available".

Unlike ``test_memory_adapter_api.py`` (which installs a *hand-written fake*
exposing whatever API the adapter wants and so would pass through a second
drift), these tests bind against **real core** — the installed
``praisonaiagents`` / ``praisonai`` packages — so any future rename on core
that the adapter does not track will fail here.

A "binding failure" is a message that proves the call never reached real I/O:
``object has no attribute``, ``unexpected keyword argument``,
``missing … positional argument``, ``cannot import name``,
``is not callable``, or a false ``… not available`` for an installed module.
Network/credential/runtime errors are *allowed* — they prove the call bound
and executed.
"""

import pytest

pytest.importorskip("praisonaiagents")


# Substrings that prove the adapter never bound to a real callable.
_BINDING_FAILURE_MARKERS = (
    "has no attribute",
    "unexpected keyword argument",
    "missing 1 required positional argument",
    "missing 2 required positional arguments",
    "cannot import name",
    "object is not callable",
    "'module' object is not callable",
    "not available",
    "not installed",
    "takes no arguments",
)


def _assert_bound(out: str) -> None:
    assert isinstance(out, str)
    lowered = out.lower()
    for marker in _BINDING_FAILURE_MARKERS:
        assert marker not in lowered, f"binding failure surfaced: {out!r}"


@pytest.fixture
def isolated_registry():
    """Give each test a fresh tool/resource registry bound to real core."""
    import praisonai_mcp.mcp_server.registry as reg
    from praisonai_mcp.mcp_server.registry import (
        MCPToolRegistry,
        MCPResourceRegistry,
    )

    saved_tool = reg._tool_registry
    saved_resource = reg._resource_registry
    reg._tool_registry = MCPToolRegistry()
    reg._resource_registry = MCPResourceRegistry()
    try:
        yield reg
    finally:
        reg._tool_registry = saved_tool
        reg._resource_registry = saved_resource


def _tool(reg, name):
    tool = reg._tool_registry.get(name)
    assert tool is not None, f"tool not registered: {name}"
    return tool.handler


def _resource(reg, uri):
    resource = reg._resource_registry.get(uri)
    assert resource is not None, f"resource not registered: {uri}"
    return resource.handler


# --------------------------------------------------------------------------
# knowledge.*  (add / query / list / clear / stats)
# --------------------------------------------------------------------------
def test_knowledge_adapter_binds_to_real_core(isolated_registry):
    from praisonai_mcp.mcp_server.adapters.knowledge import register_knowledge_tools

    register_knowledge_tools()
    reg = isolated_registry

    _assert_bound(_tool(reg, "praisonai.knowledge.query")(query="hello"))
    _assert_bound(_tool(reg, "praisonai.knowledge.list")())
    _assert_bound(_tool(reg, "praisonai.knowledge.stats")())
    _assert_bound(_tool(reg, "praisonai.knowledge.clear")())


# --------------------------------------------------------------------------
# hooks.* / session.* / tools.* / eval.*  (cli_tools adapter)
# --------------------------------------------------------------------------
def test_hooks_adapter_binds_to_real_core(isolated_registry):
    from praisonai_mcp.mcp_server.adapters.cli_tools import register_cli_tools

    register_cli_tools()
    reg = isolated_registry

    _assert_bound(_tool(reg, "praisonai.hooks.list")())
    _assert_bound(_tool(reg, "praisonai.hooks.stats")())


def test_session_adapter_binds_to_real_core(isolated_registry):
    from praisonai_mcp.mcp_server.adapters.cli_tools import register_cli_tools

    register_cli_tools()
    reg = isolated_registry

    _assert_bound(_tool(reg, "praisonai.session.list")())
    _assert_bound(_tool(reg, "praisonai.session.info")(session_id="nope"))
    _assert_bound(_tool(reg, "praisonai.session.delete")(session_id="nope"))


def test_tools_adapter_binds_to_real_core(isolated_registry):
    from praisonai_mcp.mcp_server.adapters.cli_tools import register_cli_tools

    register_cli_tools()
    reg = isolated_registry

    _assert_bound(_tool(reg, "praisonai.tools.list")())
    _assert_bound(_tool(reg, "praisonai.tools.info")(tool_name="nope"))
    _assert_bound(_tool(reg, "praisonai.tools.search")(query="x"))


# --------------------------------------------------------------------------
# resources: memory/sessions & knowledge/sources
# --------------------------------------------------------------------------
def test_resources_bind_to_real_core(isolated_registry):
    from praisonai_mcp.mcp_server.adapters.resources import register_mcp_resources

    register_mcp_resources()
    reg = isolated_registry

    sessions = _resource(reg, "praisonai://memory/sessions")()
    assert "error" not in sessions or "not available" not in str(sessions["error"]).lower()

    sources = _resource(reg, "praisonai://knowledge/sources")()
    assert "error" not in sources or "has no attribute" not in str(sources.get("error", "")).lower()


# --------------------------------------------------------------------------
# Wrapper-backed capabilities: the adapter's kwargs must bind against the
# real ``praisonai.capabilities`` callables (no ``unexpected keyword`` /
# ``missing positional``). We bind the signature rather than execute I/O.
# --------------------------------------------------------------------------
import inspect  # noqa: E402


def _bind_ok(module: str, attr: str, **kwargs):
    """Resolve the real wrapper callable and assert kwargs bind to it."""
    from praisonai_mcp._wrapper_bridge import wrapper_callable

    fn = wrapper_callable(module, attr)
    sig = inspect.signature(fn)
    # Raises TypeError if a kwarg name is wrong or a required positional
    # (that the adapter never supplies) is missing.
    sig.bind(**kwargs)


@pytest.mark.parametrize(
    "attr,kwargs",
    [
        ("transcribe", {"audio": "x", "model": "whisper-1", "language": None}),
        ("speech", {"text": "hi", "model": "tts-1", "voice": "alloy"}),
        ("apply_guardrail", {"content": "x", "guardrail_name": "default"}),
        ("ocr", {"document": "x", "model": "gpt-4o"}),
        ("a2a_send", {"target_agent": "url", "message": "hi"}),
        ("container_file_read", {"container_id": "c", "path": "p"}),
        ("container_file_write", {"container_id": "c", "path": "p", "content": "x"}),
        ("skill_load", {"skill_name": "s"}),
        ("realtime_send", {"session_id": "s", "event_type": "e"}),
    ],
)
def test_wrapper_capability_kwargs_bind_to_real_callable(attr, kwargs):
    pytest.importorskip("praisonai")
    _bind_ok("praisonai.capabilities", attr, **kwargs)


def test_generators_signatures_accept_adapter_args():
    """AgentsGenerator needs config_list; AutoGenerator takes pattern in ctor."""
    pytest.importorskip("praisonai")
    from praisonai_mcp._wrapper_bridge import wrapper_callable

    AgentsGenerator = wrapper_callable("praisonai.agents_generator", "AgentsGenerator")
    inspect.signature(AgentsGenerator.__init__).bind(
        None, agent_file="a.yaml", framework="praisonai", config_list=[]
    )

    AutoGenerator = wrapper_callable("praisonai.auto", "AutoGenerator")
    inspect.signature(AutoGenerator.__init__).bind(
        None, topic="t", pattern="sequential"
    )
    # generate() takes no ``pattern`` kwarg
    inspect.signature(AutoGenerator.generate).bind(None)


def test_eval_evaluators_exist_and_accept_adapter_args():
    pytest.importorskip("praisonaiagents")
    from praisonaiagents.eval import AccuracyEvaluator, PerformanceEvaluator

    inspect.signature(AccuracyEvaluator.__init__).bind(
        None, agent=object(), input_text="i", expected_output="e", num_iterations=3
    )
    inspect.signature(PerformanceEvaluator.__init__).bind(
        None, func=lambda: None, num_iterations=10
    )


# --------------------------------------------------------------------------
# _handle_tools_call must flag ``"Error: …"`` string returns as isError:True.
# --------------------------------------------------------------------------
import asyncio  # noqa: E402


def _call_tool(server, name):
    return asyncio.run(server._handle_tools_call({"name": name, "arguments": {}}))


def test_error_string_return_sets_iserror_true():
    from praisonai_mcp.mcp_server.registry import MCPToolRegistry, register_tool
    from praisonai_mcp.mcp_server.server import MCPServer
    import praisonai_mcp.mcp_server.registry as reg

    registry = MCPToolRegistry()
    saved = reg._tool_registry
    reg._tool_registry = registry
    try:
        @register_tool("test.fails")
        def fails() -> str:
            return "Error: something went wrong"

        @register_tool("test.ok")
        def ok() -> str:
            return "all good"
    finally:
        reg._tool_registry = saved

    server = MCPServer(tool_registry=registry)

    failed = _call_tool(server, "test.fails")
    assert failed["isError"] is True

    good = _call_tool(server, "test.ok")
    assert good["isError"] is False
