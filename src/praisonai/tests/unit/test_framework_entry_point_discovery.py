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

    class _Prep:
        adapter = registry.create("echo_test_adapter")

        def run(self, *args, **kwargs):
            return self.adapter.run(*args, **kwargs)

    monkeypatch.setattr(gen, "_prepare_for_run", lambda _config=None: {
        "adapter": registry.create("echo_test_adapter"),
        "config": {"framework": "echo_test_adapter", "topic": "hello", "roles": {}},
        "topic": "hello",
        "tools_dict": {},
    })

    result = gen.generate_crew_and_kickoff()
    assert "echo:hello" in result
