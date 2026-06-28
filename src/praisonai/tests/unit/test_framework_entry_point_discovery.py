"""Entry-point style framework adapter registration smoke test."""

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
