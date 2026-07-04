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
    gen.logger = logging.getLogger(__name__)
    return gen


def test_effective_timeout_cli_wins_over_role():
    gen = _make_generator()
    gen.cli_config = {"tool_timeout": 5}
    config = {"roles": {"a": {"tool_timeout": 30}}}
    assert gen._resolve_effective_tool_timeout(config) == 5.0


def test_effective_timeout_uses_max_declared_role():
    gen = _make_generator()
    config = {"roles": {"a": {"tool_timeout": 30}, "b": {"tool_timeout": 10}}}
    assert gen._resolve_effective_tool_timeout(config) == 30.0


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


def test_ag2_not_in_default_priority():
    from praisonai.framework_adapters.registry import FrameworkAdapterRegistry

    assert "ag2" not in FrameworkAdapterRegistry.DEFAULT_PRIORITY
