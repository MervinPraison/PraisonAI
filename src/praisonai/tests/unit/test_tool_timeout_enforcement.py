#!/usr/bin/env python3

"""
Tests for wrapper-layer tool_timeout enforcement (issue #2608, gap #2) and the
removal of the unregistered ``ag2`` default dispatch target (gap #1c).

Prior to the fix the wrapper accepted ``tool_timeout`` from CLI/YAML, wrote it
into every role, and then silently dropped it: ``_build_tools_dict`` returned
naked callables and ``_wrap_tool_with_timeout`` had zero call sites.
"""

import json
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
        tools_dict = gen._build_tools_dict({"roles": {"a": {"tool_timeout": 0.3}}})
        result = tools_dict["blocking"]()
        payload = json.loads(result)
        assert payload["error"] == "tool_timeout"
    finally:
        never.set()
        gen.close()


def test_build_tools_dict_no_wrap_when_no_timeout():
    gen = _make_generator()
    gen.cli_config = {}

    sentinel = lambda: "ok"

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
