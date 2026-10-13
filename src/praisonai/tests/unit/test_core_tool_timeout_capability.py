"""Native tool-timeout delegation is an adapter capability, not a name check (#5797)."""

import logging
import subprocess
import sys
import threading
import uuid

from praisonai.framework_adapters.base import BaseFrameworkAdapter
from praisonai.framework_adapters.praisonai_adapter import PraisonAIAdapter
from praisonai.framework_adapters.registry import FrameworkAdapterRegistry


def test_flag_defaults():
    assert BaseFrameworkAdapter.SUPPORTS_CORE_TOOL_TIMEOUT is False
    assert PraisonAIAdapter.SUPPORTS_CORE_TOOL_TIMEOUT is True


class ForkedAdapter(PraisonAIAdapter):
    @property
    def name(self) -> str:
        return "forked"


def _make_generator(framework):
    from praisonai.agents_generator import AgentsGenerator

    registry = FrameworkAdapterRegistry()
    registry.register("forked", ForkedAdapter)

    gen = AgentsGenerator.__new__(AgentsGenerator)
    gen._adapter_registry = registry
    gen.framework = framework
    gen.cli_config = {}
    gen._tool_timeout_executor = None
    gen._owns_tool_timeout_executor = True
    gen._tool_timeout_executor_lock = threading.Lock()
    gen._leaked_workers = 0
    gen._max_leaked_workers = 16
    gen._timeout_owner_key = uuid.uuid4()
    gen.logger = logging.getLogger(__name__)
    return gen


def test_renamed_native_adapter_delegates_to_core():
    gen = _make_generator("forked")
    assert gen._delegates_tool_timeout_to_core("forked") is True
    assert gen._delegates_tool_timeout_to_core("missing") is False
    assert gen._delegates_tool_timeout_to_core(None) is False


def test_renamed_native_adapter_leaves_plain_callables_unwrapped():
    def plain():
        return "ok"

    class _Resolver:
        def resolve_all_from_yaml(self, config):
            return {"plain": plain}

    gen = _make_generator("forked")
    gen.cli_config = {"tool_timeout": 5}
    gen.tool_resolver = _Resolver()
    gen.tools = []
    try:
        # Both callers go through the capability, not ``== "praisonai"``.
        assert gen._build_tools_dict({"roles": {"a": {}}})["plain"] is plain
        assert gen._run_ctx["_native_tool_timeout_resolver"]("a") == 5.0
        assert gen._wrap_tool_with_timeout(plain, 5) is plain
    finally:
        gen.close()


def test_discover_instances_polls_live_providers(monkeypatch):
    import praisonai.cli.commands.managed as managed_cli

    assert managed_cli._PS_PROVIDERS is None
    polled = []

    def fake_resolve(name):
        polled.append(name)
        raise ImportError(name)

    monkeypatch.setattr(
        "praisonaiagents.managed._compute_bridge.resolve_compute", fake_resolve
    )
    monkeypatch.setattr(
        "praisonaiagents.managed._compute_bridge.available_providers",
        lambda: ("docker", "late_provider"),
    )
    managed_cli._discover_instances()
    assert polled == ["docker", "late_provider"]


def test_cli_import_does_not_configure_root_logger():
    code = (
        "import logging, sys; import praisonai.cli.app; "
        "print(len(logging.getLogger().handlers), 'praisonaiagents' in sys.modules)"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout.strip().splitlines()[-1]
    assert out == "0 False"
