"""Core SDK framework adapter protocol exports."""

from praisonaiagents.frameworks.protocols import FrameworkAdapterProtocol
from praisonaiagents.frameworks.base import BaseFrameworkAdapter


def test_protocol_is_runtime_checkable():
    class _MinimalAdapter:
        name = "x"
        install_hint = "pip install x"
        requires_tools_extra = False
        is_router = False

        def is_available(self):
            return True

        def resolve(self, *, config=None):
            return self

        def setup(self, *, framework_tag: str):
            pass

        def run(self, config, llm_config, topic, *, tools_dict=None, agent_callback=None, task_callback=None, cli_config=None):
            return "ok"

        async def arun(self, config, llm_config, topic, *, tools_dict=None, agent_callback=None, task_callback=None, cli_config=None):
            return "ok"

        def cleanup(self):
            pass

        def resolve_alias(self):
            return self.name

    assert isinstance(_MinimalAdapter(), FrameworkAdapterProtocol)


def test_base_framework_adapter_format_template():
    adapter = BaseFrameworkAdapter()
    assert adapter._format_template("Hello {topic}", topic="world") == "Hello world"
