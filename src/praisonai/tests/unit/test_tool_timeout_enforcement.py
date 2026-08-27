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


def test_build_tools_dict_clears_stale_wrap_state_on_reuse():
    # Reusing the same generator with a different timeout layout must not leak a
    # previous run's closure: the uniform and per-agent keys are mutually
    # exclusive, so the inactive one is always reset to None. Otherwise an
    # adapter could apply an earlier run's budget to the current tools.
    gen = _make_generator()

    def sentinel():
        return "ok"

    class _FakeResolver:
        def resolve_all_from_yaml(self, config):
            return {"plain": sentinel}

    gen.tool_resolver = _FakeResolver()
    gen.tools = []

    try:
        # Run 1: uniform CLI timeout -> uniform wrap set, resolver cleared.
        gen.cli_config = {"tool_timeout": 5}
        gen._build_tools_dict({"roles": {"a": {}}})
        assert callable(gen.cli_config.get("_tool_timeout_wrap"))
        assert gen.cli_config.get("_agent_tool_wrap_resolver") is None

        # Run 2: heterogeneous per-agent timeouts -> resolver set, stale uniform
        # wrap MUST be cleared so adapters don't reuse run 1's budget.
        gen.cli_config = {}
        gen._build_tools_dict(
            {"roles": {"a": {"tool_timeout": 10}, "b": {"tool_timeout": 30}}}
        )
        assert gen.cli_config.get("_tool_timeout_wrap") is None
        assert callable(gen.cli_config.get("_agent_tool_wrap_resolver"))

        # Run 3: no timeout at all -> both keys cleared.
        gen.cli_config = {}
        gen._build_tools_dict({"roles": {"a": {}}})
        assert gen.cli_config.get("_tool_timeout_wrap") is None
        assert gen.cli_config.get("_agent_tool_wrap_resolver") is None
    finally:
        gen.close()


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


def test_explicit_workflow_timeout_ignores_cli_default():
    # The legacy CLI always injects its --tool-timeout argparse default (60)
    # into cli_config, so a bare default must NOT be treated as a user request
    # (otherwise every ordinary workflow YAML run would raise). Regression for
    # the workflow tool_timeout fail-fast (PR #3963).
    gen = _make_generator()
    gen.cli_config = {"tool_timeout": 60}
    assert gen._resolve_explicit_workflow_tool_timeout({}) is None
    assert gen._resolve_explicit_workflow_tool_timeout(
        {"roles": {"a": {}}}
    ) is None


def test_explicit_workflow_timeout_flags_changed_cli_value():
    gen = _make_generator()
    gen.cli_config = {"tool_timeout": 30}
    assert gen._resolve_explicit_workflow_tool_timeout({}) == 30.0


def test_explicit_workflow_timeout_flags_yaml_declared():
    gen = _make_generator()
    gen.cli_config = {"tool_timeout": 60}  # bare CLI default
    config = {"roles": {"a": {"tool_timeout": 10}}}
    assert gen._resolve_explicit_workflow_tool_timeout(config) == 10.0


def test_explicit_workflow_timeout_ignores_bool_yaml():
    gen = _make_generator()
    gen.cli_config = {}
    config = {"agents": {"a": {"tool_timeout": True}}}
    assert gen._resolve_explicit_workflow_tool_timeout(config) is None


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


# --- Issue #4449: wrapper gaps -------------------------------------------------


def test_uniform_timeout_all_equal_declared():
    # When every declared per-agent tool_timeout is identical a single uniform
    # wrap is applied (cheapest path, same behaviour as before).
    gen = _make_generator()
    config = {"roles": {"a": {"tool_timeout": 10}, "b": {"tool_timeout": 10}}}
    assert gen._resolve_uniform_tool_timeout(config) == 10.0


def test_uniform_timeout_none_for_heterogeneous():
    # Heterogeneous per-agent budgets must NOT collapse to a single value; the
    # uniform resolver returns None so the caller falls back to per-agent wraps.
    gen = _make_generator()
    config = {"roles": {"a": {"tool_timeout": 5}, "b": {"tool_timeout": 120}}}
    assert gen._resolve_uniform_tool_timeout(config) is None


def test_uniform_timeout_cli_wins():
    gen = _make_generator()
    gen.cli_config = {"tool_timeout": 15}
    config = {"roles": {"a": {"tool_timeout": 5}, "b": {"tool_timeout": 120}}}
    assert gen._resolve_uniform_tool_timeout(config) == 15.0


def test_uniform_timeout_none_when_one_agent_declares_and_another_omits():
    # Greptile P1: a lone declared budget must NOT be treated as uniform, or the
    # undeclared agent inherits it via the shared-dict wrap and its valid
    # long-running calls fail with ToolTimeoutError. The per-agent resolver must
    # own this case instead.
    gen = _make_generator()
    gen.cli_config = {}
    config = {"roles": {"declared": {"tool_timeout": 5}, "undeclared": {}}}
    assert gen._resolve_uniform_tool_timeout(config) is None


def test_per_agent_resolver_leaves_undeclared_agent_unwrapped():
    # The declaring agent gets its budget; the agent that omitted tool_timeout
    # gets no wrap at all (None), so its tools run without an imposed timeout.
    gen = _make_generator()
    gen.cli_config = {}
    config = {"roles": {"declared": {"tool_timeout": 5}, "undeclared": {}}}
    resolver = gen.make_agent_tool_wrap_resolver(config)
    assert callable(resolver("declared"))
    assert resolver("undeclared") is None


def test_resolve_agent_tool_timeout_per_agent():
    # Each agent gets its own declared budget, no cross-agent downgrade.
    gen = _make_generator()
    config = {"roles": {"fast": {"tool_timeout": 5}, "slow": {"tool_timeout": 120}}}
    assert gen.resolve_agent_tool_timeout("fast", config) == 5.0
    assert gen.resolve_agent_tool_timeout("slow", config) == 120.0


def test_resolve_agent_tool_timeout_falls_back_to_cli():
    gen = _make_generator()
    gen.cli_config = {"tool_timeout": 42}
    config = {"roles": {"fast": {"tool_timeout": 5}, "plain": {}}}
    assert gen.resolve_agent_tool_timeout("fast", config) == 5.0
    assert gen.resolve_agent_tool_timeout("plain", config) == 42.0


def test_make_agent_tool_wrap_resolver_none_without_declarations():
    gen = _make_generator()
    assert gen.make_agent_tool_wrap_resolver({"roles": {"a": {}}}) is None


def test_heterogeneous_per_agent_timeouts_honoured_end_to_end():
    # A heterogeneous config leaves the shared tools_dict unwrapped and instead
    # exposes a per-agent resolver so each agent's tools carry its own budget.
    gen = _make_generator()
    gen.cli_config = {}

    never = threading.Event()

    def _blocking():
        never.wait(30)
        return "done"

    def _fast():
        return "quick"

    class _FakeResolver:
        def resolve_all_from_yaml(self, config):
            return {"scrape_page": _blocking, "internet_search": _fast}

    gen.tool_resolver = _FakeResolver()
    gen.tools = []

    config = {
        "roles": {
            "fast_router": {"tool_timeout": 0.3, "tools": ["internet_search"]},
            "slow_analyst": {"tool_timeout": 30, "tools": ["scrape_page"]},
        }
    }

    try:
        from praisonai.agents_generator import ToolTimeoutError

        tools_dict = gen._build_tools_dict(config)
        # Shared dict is NOT uniformly wrapped (heterogeneous budgets).
        assert tools_dict["scrape_page"] is _blocking
        # A per-agent resolver was exposed for adapters to apply.
        resolver = gen.cli_config.get("_agent_tool_wrap_resolver")
        assert callable(resolver)

        # The fast agent's tools get a tight 0.3s guard.
        fast_wrap = resolver("fast_router")
        assert callable(fast_wrap)
        # The slow agent keeps its own larger budget (not downgraded to 0.3).
        assert gen.resolve_agent_tool_timeout("slow_analyst", config) == 30.0

        guarded_blocking = fast_wrap(_blocking)
        with pytest.raises(ToolTimeoutError) as exc_info:
            guarded_blocking()
        assert exc_info.value.timeout_seconds == 0.3
    finally:
        never.set()
        gen.close()


def test_build_agent_specs_applies_per_agent_wrap():
    # build_agent_specs wraps each agent's resolved tools with that agent's
    # resolver-provided wrap; tool objects stay shared (only the guard differs).
    from praisonai.framework_adapters._config_builder import build_agent_specs

    def tool_a():
        return "a"

    tools_dict = {"tool_a": tool_a}

    def _fmt(v, topic=""):
        return v

    seen = {}

    def resolver(agent_key):
        seen[agent_key] = True

        def wrap(tool, _key=agent_key):
            def _wrapped(*args, **kwargs):
                return (_key, tool(*args, **kwargs))
            return _wrapped

        return wrap

    config = {
        "roles": {
            "alpha": {"role": "A", "tools": ["tool_a"]},
            "beta": {"role": "B", "tools": ["tool_a"]},
        }
    }

    specs = build_agent_specs(
        config, "topic", tools_dict, _fmt, agent_tool_wrap_resolver=resolver
    )
    by_key = {s.key: s for s in specs}
    assert by_key["alpha"].tools[0]() == ("alpha", "a")
    assert by_key["beta"].tools[0]() == ("beta", "a")
    assert seen == {"alpha": True, "beta": True}


def test_build_agent_specs_no_wrap_when_resolver_absent():
    from praisonai.framework_adapters._config_builder import build_agent_specs

    def tool_a():
        return "a"

    def _fmt(v, topic=""):
        return v

    config = {"roles": {"alpha": {"role": "A", "tools": ["tool_a"]}}}
    specs = build_agent_specs(config, "topic", {"tool_a": tool_a}, _fmt)
    assert specs[0].tools[0] is tool_a


def test_maybe_inject_centric_tools_applies_wrap():
    # Injected ACP/LSP centric tools must carry the same timeout wrap as the
    # YAML-declared tools instead of silently bypassing it.
    try:
        from praisonai.framework_adapters.praisonai_adapter import PraisonAIAdapter
    except ImportError:
        pytest.skip("PraisonAIAdapter not available")

    adapter = PraisonAIAdapter.__new__(PraisonAIAdapter)

    class _FakeRuntime:
        pass

    def _lsp_tool():
        return "def"

    # Patch the lazily-imported factory used inside the method.
    import sys
    import types

    fake_mod = types.ModuleType("praisonai.cli.features.agent_tools")
    fake_mod.create_agent_centric_tools = lambda rt: {"lsp_find_definition": _lsp_tool}
    sys.modules["praisonai.cli.features.agent_tools"] = fake_mod
    try:
        marker = []

        def wrap(tool):
            marker.append(tool)
            return lambda *a, **k: ("wrapped", tool())

        merged = adapter._maybe_inject_centric_tools(
            _FakeRuntime(), {"existing": lambda: "x"}, wrap=wrap
        )
        assert marker == [_lsp_tool]
        assert merged["lsp_find_definition"]() == ("wrapped", "def")
    finally:
        del sys.modules["praisonai.cli.features.agent_tools"]


def test_autogen_code_execution_disabled_by_default():
    # Safe-by-default: without config.autogen.code_execution the resolved config
    # must disable local code execution (no host RCE surface).
    _assert_autogen_code_exec({}, expected=False, expected_human="TERMINATE")


def test_autogen_code_execution_opt_in_defaults_docker():
    _assert_autogen_code_exec(
        {"config": {"autogen": {"code_execution": True}}},
        expected={"work_dir": "coding", "use_docker": True},
        expected_human="TERMINATE",
    )


def test_autogen_code_execution_dict_defaults_docker_true():
    _assert_autogen_code_exec(
        {"config": {"autogen": {"code_execution": {"work_dir": "x"}}}},
        expected={"work_dir": "x", "use_docker": True},
        expected_human="TERMINATE",
    )


def test_autogen_human_input_mode_overridable():
    _assert_autogen_code_exec(
        {"config": {"autogen": {"human_input_mode": "ALWAYS"}}},
        expected=False,
        expected_human="ALWAYS",
    )


def _assert_autogen_code_exec(config, *, expected, expected_human):
    """Drive AutoGenAdapter.run just far enough to capture UserProxyAgent kwargs."""
    try:
        from praisonai.framework_adapters.autogen_adapter import AutoGenAdapter
    except ImportError:
        pytest.skip("AutoGen adapter not available")

    import sys
    import types
    from unittest import mock

    captured = {}

    class _FakeUserProxy:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    fake_autogen = types.ModuleType("autogen")
    fake_autogen.UserProxyAgent = _FakeUserProxy
    fake_autogen.AssistantAgent = lambda **k: None

    adapter = AutoGenAdapter()

    # Stop execution right after user_proxy construction by making the shared
    # spec builder raise; we only care about the captured UserProxyAgent kwargs.
    with mock.patch.dict(sys.modules, {"autogen": fake_autogen}):
        with mock.patch(
            "praisonai.framework_adapters._config_builder.build_agent_specs",
            side_effect=RuntimeError("stop after user_proxy"),
        ):
            with pytest.raises(RuntimeError, match="stop after user_proxy"):
                adapter.run(config, [{"model": "gpt-4o-mini"}], "topic")

    assert captured["code_execution_config"] == expected
    assert captured["human_input_mode"] == expected_human
