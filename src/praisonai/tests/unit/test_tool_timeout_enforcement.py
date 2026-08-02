#!/usr/bin/env python3

"""
Tests for wrapper-layer tool_timeout enforcement (issue #2608, gap #2) and the
removal of the unregistered ``ag2`` default dispatch target (gap #1c).

Prior to the fix the wrapper accepted ``tool_timeout`` from CLI/YAML, wrote it
into every role, and then silently dropped it: ``_build_tools_dict`` returned
naked callables and ``_wrap_tool_with_timeout`` had zero call sites.
"""

import logging
import threading
import uuid

import pytest


def _make_generator():
    try:
        from praisonai.agents_generator import AgentsGenerator
    except ImportError:
        pytest.skip("AgentsGenerator not available")
    gen = AgentsGenerator.__new__(AgentsGenerator)
    gen.cli_config = {}
    # __new__ skips __init__; wire up the executor state the timeout stack needs.
    gen._tool_timeout_executor = None
    gen._owns_tool_timeout_executor = True
    gen._tool_timeout_executor_lock = threading.Lock()
    gen._leaked_workers = 0
    gen._max_leaked_workers = 16
    gen._timeout_owner_key = uuid.uuid4()
    gen.logger = logging.getLogger(__name__)
    return gen


def test_effective_timeout_cli_wins_over_role():
    gen = _make_generator()
    gen.cli_config = {"tool_timeout": 5}
    config = {"roles": {"a": {"tool_timeout": 30}}}
    assert gen._resolve_effective_tool_timeout(config) == 5.0


def test_effective_timeout_uses_tightest_declared_role():
    # Safe by default: the smallest declared timeout wins so a fast agent is
    # never forced to wait for a slower agent's larger budget (issue #3175).
    gen = _make_generator()
    config = {"roles": {"a": {"tool_timeout": 30}, "b": {"tool_timeout": 10}}}
    assert gen._resolve_effective_tool_timeout(config) == 10.0


def test_effective_timeout_reads_agents_section():
    gen = _make_generator()
    config = {"agents": {"a": {"tool_timeout": 7}}}
    assert gen._resolve_effective_tool_timeout(config) == 7.0


def test_effective_timeout_none_when_absent():
    gen = _make_generator()
    assert gen._resolve_effective_tool_timeout({"roles": {"a": {}}}) is None
    assert gen._resolve_effective_tool_timeout({}) is None


def test_effective_timeout_ignores_bool_values():
    # ``bool`` subclasses ``int``; ``tool_timeout: yes`` (YAML -> True) must not
    # be treated as a 1-second timeout applied to every tool.
    gen = _make_generator()
    gen.cli_config = {"tool_timeout": True}
    assert gen._resolve_effective_tool_timeout({}) is None

    gen.cli_config = {}
    config = {"roles": {"a": {"tool_timeout": True}, "b": {"tool_timeout": False}}}
    assert gen._resolve_effective_tool_timeout(config) is None


def test_build_tools_dict_wraps_with_timeout():
    gen = _make_generator()
    gen.cli_config = {"tool_timeout": 0.3}

    # Block on an Event that is never set so the tool "hangs"; this is immune to
    # the autouse fast_sleep fixture that caps time.sleep in unit tests.
    never = threading.Event()

    def _blocking():
        never.wait(30)
        return "done"

    class _FakeResolver:
        def resolve_all_from_yaml(self, config):
            return {"blocking": _blocking}

    gen.tool_resolver = _FakeResolver()
    gen.tools = []

    try:
        from praisonai.agents_generator import ToolTimeoutError
        tools_dict = gen._build_tools_dict({"roles": {"a": {"tool_timeout": 0.3}}})
        # On timeout the wrapper raises ToolTimeoutError instead of returning a
        # JSON string, preserving the tool's declared return-type contract.
        with pytest.raises(ToolTimeoutError) as exc_info:
            tools_dict["blocking"]()
        assert exc_info.value.tool_name == "_blocking"
        assert exc_info.value.timeout_seconds == 0.3
    finally:
        never.set()
        gen.close()


def test_build_tools_dict_no_wrap_when_no_timeout():
    gen = _make_generator()
    gen.cli_config = {}

    def sentinel():
        return "ok"

    class _FakeResolver:
        def resolve_all_from_yaml(self, config):
            return {"plain": sentinel}

    gen.tool_resolver = _FakeResolver()
    gen.tools = []

    tools_dict = gen._build_tools_dict({"roles": {"a": {}}})
    assert tools_dict["plain"] is sentinel


def test_timeout_proxy_preserves_isinstance_and_schema():
    # A shared framework-tool object wrapped for timeout must keep its type
    # identity: downstream executors (praisonaiagents tool_execution, CrewAI /
    # LangChain) route on ``isinstance(tool, BaseTool)`` to call ``.run``. A
    # plain proxy that fails that check (and is not callable) would silently
    # execute nothing, so the proxy subclasses the wrapped tool's own class.
    from concurrent.futures import ThreadPoolExecutor

    from praisonai.agents_generator import _wrap_with_timeout, _TimeoutBoundTool

    class FrameworkTool:
        name = "calc"
        description = "doubles x"
        args_schema = {"x": "int"}

        def _run(self, x=1):
            return x * 2

        def run(self, x=1):
            return self._run(x)

    inner = FrameworkTool()
    executor = ThreadPoolExecutor(max_workers=2)
    try:
        proxy = _wrap_with_timeout(
            inner, 5.0, lambda: executor, owner_key=uuid.uuid4()
        )
        # Type identity preserved for isinstance-based dispatch.
        assert isinstance(proxy, FrameworkTool)
        assert isinstance(proxy, _TimeoutBoundTool)
        # Schema attributes still delegate to the shared inner object.
        assert proxy.name == "calc"
        assert proxy.args_schema == {"x": "int"}
        # Execution routes through the timeout-wrapped methods and returns.
        assert proxy.run(x=3) == 6
        assert proxy._run(x=4) == 8
        # The shared inner object is never mutated in place.
        assert "run" not in vars(inner)
        assert "_run" not in vars(inner)
    finally:
        executor.shutdown()


def test_timeout_proxy_isolated_across_generators():
    # One generator's executor must never leak into another's calls. After the
    # first generator's pool is shut down, a second generator's proxy (built on
    # the same shared inner object) must still execute successfully.
    from concurrent.futures import ThreadPoolExecutor

    from praisonai.agents_generator import _wrap_with_timeout, _TIMEOUT_ORIGINAL

    class FrameworkTool:
        name = "echo"
        description = "echoes"

        def _run(self, v=0):
            return v

        def run(self, v=0):
            return self._run(v)

    inner = FrameworkTool()

    exec_a = ThreadPoolExecutor(max_workers=2)
    key_a = uuid.uuid4()
    proxy_a = _wrap_with_timeout(inner, 5.0, lambda: exec_a, owner_key=key_a)

    # Same owner re-wrapping is idempotent (no proxy rebuild / wrapper stacking).
    assert _wrap_with_timeout(proxy_a, 5.0, lambda: exec_a, owner_key=key_a) is proxy_a

    exec_b = ThreadPoolExecutor(max_workers=2)
    key_b = uuid.uuid4()
    proxy_b = _wrap_with_timeout(proxy_a, 5.0, lambda: exec_b, owner_key=key_b)
    try:
        assert proxy_b is not proxy_a
        # The second proxy unwraps back to the shared inner, never the peer proxy.
        assert getattr(proxy_b, _TIMEOUT_ORIGINAL) is inner
        # Shutting down generator A's pool must not break generator B's calls.
        exec_a.shutdown()
        assert proxy_b.run(v=11) == 11
    finally:
        exec_b.shutdown()


def test_ag2_not_in_default_priority():
    from praisonai.framework_adapters.registry import FrameworkAdapterRegistry

    assert "ag2" not in FrameworkAdapterRegistry.DEFAULT_PRIORITY


def test_autogen_adapter_translates_tool_timeout_to_string():
    # AutoGen v0.2 runs tools inside its own chat loop and expects a value to
    # hand back to the LLM; a ToolTimeoutError must be translated at the adapter
    # boundary instead of aborting the whole conversation.
    try:
        from praisonai.framework_adapters.autogen_adapter import AutoGenAdapter
        from praisonai.agents_generator import ToolTimeoutError
    except ImportError:
        pytest.skip("AutoGen adapter / timeout stack not available")

    def _times_out():
        raise ToolTimeoutError(
            tool_name="_times_out", timeout_seconds=0.1,
            background_work_may_continue=True,
        )

    guarded = AutoGenAdapter._wrap_tool_for_execution(_times_out, "_times_out")
    result = guarded()
    assert isinstance(result, str)
    assert "timed out" in result


def test_autogen_adapter_passes_through_normal_result():
    try:
        from praisonai.framework_adapters.autogen_adapter import AutoGenAdapter
    except ImportError:
        pytest.skip("AutoGen adapter not available")

    def _ok(x):
        return x + 1

    guarded = AutoGenAdapter._wrap_tool_for_execution(_ok, "_ok")
    assert guarded(41) == 42
