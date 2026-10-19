"""Entry-point style framework adapter registration smoke test."""

import pytest

from praisonai.framework_adapters.base import BaseFrameworkAdapter
from praisonai.framework_adapters.registry import FrameworkAdapterRegistry


class _EchoAdapter(BaseFrameworkAdapter):
    name = "echo_test_adapter"
    install_hint = "pip install echo-test"
    requires_tools_extra = False

    def is_available(self) -> bool:
        return True

    def run(
        self,
        config,
        llm_config,
        topic,
        *,
        tools_dict=None,
        agent_callback=None,
        task_callback=None,
        cli_config=None,
    ) -> str:
        return f"echo:{topic}"


def test_runtime_register_and_create():
    registry = FrameworkAdapterRegistry()
    registry.register("echo_test_adapter", _EchoAdapter)
    adapter = registry.create("echo_test_adapter")
    assert adapter.run({}, [], "hello", tools_dict={}) == "echo:hello"


def test_list_available_frameworks():
    registry = FrameworkAdapterRegistry()
    registry.register("echo_test_adapter", _EchoAdapter)
    available = registry.list_available_frameworks()
    assert "echo_test_adapter" in available


def test_entry_point_group_discoverable():
    from praisonai.framework_adapters.registry import get_default_registry

    names = get_default_registry().list_names()
    assert "praisonai" in names


def test_agents_generator_uses_custom_registry(monkeypatch):
    registry = FrameworkAdapterRegistry()
    registry.register("echo_test_adapter", _EchoAdapter)

    yaml_content = """
framework: echo_test_adapter
topic: hello
roles:
  agent:
    role: Tester
    goal: Echo
    backstory: Test agent
    tasks:
      t1:
        description: Say {topic}
        expected_output: echo
"""

    from praisonai.agents_generator import AgentsGenerator

    gen = AgentsGenerator(
        agent_file="test.yaml",
        framework="echo_test_adapter",
        config_list=[{"model": "openai/gpt-4o-mini"}],
        agent_yaml=yaml_content,
        adapter_registry=registry,
    )

    monkeypatch.setattr(gen, "_prepare_for_run", lambda _config=None: {
        "adapter": registry.create("echo_test_adapter"),
        "config": {"framework": "echo_test_adapter", "topic": "hello", "roles": {}},
        "topic": "hello",
        "tools_dict": {},
    })

    result = gen.generate_crew_and_kickoff()
    assert "echo:hello" in result


def test_agents_generator_uses_registry_default_when_framework_omitted(monkeypatch):
    registry = FrameworkAdapterRegistry(discover_entry_points=False)
    registry.unregister("praisonai")
    registry.register("echo_test_adapter", _EchoAdapter)

    from praisonai.agents_generator import AgentsGenerator

    gen = AgentsGenerator(
        agent_file="test.yaml",
        framework=None,
        config_list=[{"model": "openai/gpt-4o-mini"}],
        agent_yaml="roles: {}\ntopic: hello\n",
        adapter_registry=registry,
    )
    monkeypatch.setattr(gen, "_validate_agents_config", lambda _config: None)
    monkeypatch.setattr(gen, "_build_tools_and_run_ctx", lambda _config: ({}, {}))
    monkeypatch.setattr(
        gen,
        "_validate_cli_backend_compatibility",
        lambda *_args, **_kwargs: None,
    )

    prep = gen._prepare_for_run({"roles": {}, "topic": "hello"})

    assert prep["adapter"].name == "echo_test_adapter"


def test_entry_point_loaders_use_add_loader_path():
    """Entry-point loaders use the same _add_loader path as _discover_entry_points."""
    registry = FrameworkAdapterRegistry(discover_entry_points=False)
    # Mirror what _discover_entry_points does for each entry point (without
    # importlib.metadata, which varies under pytest-xdist on CI).
    registry._add_loader("echo_test_adapter", lambda: _EchoAdapter)

    assert "echo_test_adapter" in registry.list_names()
    adapter = registry.create("echo_test_adapter")
    assert adapter.run({}, [], "world", tools_dict={}) == "echo:world"
    assert "echo_test_adapter" in registry.list_available_frameworks()


def test_overlapping_run_cannot_swap_this_runs_tool_timeout_ctx(monkeypatch):
    """A second run preparing mid-flight must not change this run's ctx (#5904)."""
    seen = {}

    class _CaptureAdapter(_EchoAdapter):
        def run(self, config, llm_config, topic, *, cli_config=None, **_kwargs):
            seen["cli_config"] = cli_config
            return "ok"

    registry = FrameworkAdapterRegistry(discover_entry_points=False)
    registry.register("echo_test_adapter", _CaptureAdapter)

    from praisonai.agents_generator import AgentsGenerator

    gen = AgentsGenerator(
        agent_file="test.yaml",
        framework="echo_test_adapter",
        config_list=[{"model": "openai/gpt-4o-mini"}],
        # Uniform per-role timeout -> this run gets a ``_tool_timeout_wrap``.
        agent_yaml=(
            "framework: echo_test_adapter\ntopic: hello\nroles:\n"
            "  a:\n    role: A\n    goal: g\n    backstory: b\n    tool_timeout: 5\n"
            "    tasks:\n      t:\n        description: d\n        expected_output: e\n"
        ),
        adapter_registry=registry,
    )
    monkeypatch.setattr(gen, "_validate_agents_config", lambda _config: None)

    def _other_run_prepares(_adapter):
        # Heterogeneous budgets -> resolver only, no uniform wrap. This is what
        # used to overwrite the shared ``self._run_ctx`` under the first run.
        gen._build_tools_dict({"roles": {"x": {"tool_timeout": 1}, "y": {"tool_timeout": 9}}})

    monkeypatch.setattr(gen, "_run_adapter_setup", _other_run_prepares)

    try:
        assert gen.generate_crew_and_kickoff() == "ok"
        assert gen._run_ctx["_tool_timeout_wrap"] is None
        assert callable(seen["cli_config"]["_tool_timeout_wrap"])
        assert seen["cli_config"]["_agent_tool_wrap_resolver"] is None
    finally:
        gen.close()
