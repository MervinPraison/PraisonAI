"""Example third-party framework adapter (entry-point template)."""

from praisonaiagents.frameworks.base import BaseFrameworkAdapter


class MyFrameworkAdapter(BaseFrameworkAdapter):
    name = "my_framework"
    install_hint = "pip install my-framework-bridge"
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
        return f"my_framework ran: {topic}"
