"""Native tool-timeout delegation is an adapter capability, not a name check (#5797)."""

import subprocess
import sys

from praisonai.framework_adapters.base import BaseFrameworkAdapter
from praisonai.framework_adapters.praisonai_adapter import PraisonAIAdapter
from praisonai.framework_adapters.registry import FrameworkAdapterRegistry


def test_flag_defaults():
    assert BaseFrameworkAdapter.SUPPORTS_CORE_TOOL_TIMEOUT is False
    assert PraisonAIAdapter.SUPPORTS_CORE_TOOL_TIMEOUT is True


def test_renamed_native_adapter_delegates_to_core():
    from praisonai.agents_generator import AgentsGenerator

    class ForkedAdapter(PraisonAIAdapter):
        @property
        def name(self) -> str:
            return "forked"

    registry = FrameworkAdapterRegistry()
    registry.register("forked", ForkedAdapter)

    gen = AgentsGenerator.__new__(AgentsGenerator)
    gen._adapter_registry = registry
    assert gen._delegates_tool_timeout_to_core("forked") is True
    assert gen._delegates_tool_timeout_to_core("missing") is False
    assert gen._delegates_tool_timeout_to_core(None) is False


def test_cli_import_does_not_configure_root_logger():
    code = (
        "import logging, sys; import praisonai.cli.app; "
        "print(len(logging.getLogger().handlers), 'praisonaiagents' in sys.modules)"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout.strip().splitlines()[-1]
    assert out == "0 False"
