"""Tests for CLI backend hook emission."""

import os
import time
from unittest.mock import AsyncMock, Mock

import pytest

from praisonaiagents.cli_backend.debug import backend_label, redact_command
from praisonaiagents.cli_backend.protocols import CliBackendConfig, CliBackendResult
from praisonaiagents.hooks.events import CliBackendExecuteInput
from praisonaiagents.hooks.registry import HookRegistry
from praisonaiagents.hooks.runner import HookRunner
from praisonaiagents.hooks.types import HookEvent
from praisonaiagents.plugins.manager import PluginManager
from praisonaiagents.plugins.plugin import Plugin, PluginHook, PluginInfo


def test_backend_label_uses_config_command():
    backend = Mock()
    backend.config = CliBackendConfig(command="gemini")
    assert backend_label(backend) == "gemini"


def test_backend_label_falls_back_to_class_name():
    class CustomBackend:
        pass

    assert backend_label(CustomBackend()) == "CustomBackend"


def test_cli_backend_execute_input_serialises():
    payload = CliBackendExecuteInput(
        session_id="sess-1",
        cwd=os.getcwd(),
        event_name=HookEvent.CLI_BACKEND_EXECUTE.value,
        timestamp=str(time.time()),
        agent_name="assistant",
        backend="gemini",
        command=["gemini", "-p", "hi"],
        content="ok",
    )
    data = payload.to_dict()
    assert data["backend"] == "gemini"
    assert data["transport"] == "subprocess"
    assert data["praisonai_llm_http"] is False
    # Prompt value following -p is redacted at the serialization boundary,
    # while the live in-memory command field is untouched.
    assert data["command"] == ["gemini", "-p", "<redacted>"]
    assert payload.command == ["gemini", "-p", "hi"]


def test_redact_command_masks_prompt_values():
    argv = ["gemini", "--yolo", "-p", "secret prompt", "--system", "sys instr"]
    assert redact_command(argv) == [
        "gemini",
        "--yolo",
        "-p",
        "<redacted>",
        "--system",
        "<redacted>",
    ]


def test_redact_command_passes_through_non_list():
    assert redact_command(None) is None
    assert redact_command("gemini -p hi") == "gemini -p hi"


class _TracerPlugin(Plugin):
    def __init__(self):
        self.events = []

    @property
    def info(self):
        return PluginInfo(
            name="tracer",
            hooks=[PluginHook.CLI_BACKEND_EXECUTE],
        )

    def cli_backend_execute(self, context):
        self.events.append(context)


def test_cli_backend_execute_hook_fires_via_plugin_bridge():
    reg = HookRegistry()
    mgr = PluginManager()
    plugin = _TracerPlugin()
    mgr.register(plugin)
    mgr.wire_into_hook_registry(reg)

    runner = HookRunner(registry=reg, cwd=os.getcwd())
    data = CliBackendExecuteInput(
        session_id="sess-1",
        cwd=os.getcwd(),
        event_name=HookEvent.CLI_BACKEND_EXECUTE.value,
        timestamp=str(time.time()),
        agent_name="assistant",
        backend="gemini",
        command=["gemini", "-p", "hi"],
        content="ok",
    )
    runner.execute_sync(HookEvent.CLI_BACKEND_EXECUTE, data)

    assert len(plugin.events) == 1
    assert plugin.events[0]["backend"] == "gemini"
    # Prompt value redacted before reaching the plugin bridge.
    assert plugin.events[0]["command"] == ["gemini", "-p", "<redacted>"]
    assert plugin.events[0]["praisonai_llm_http"] is False


@pytest.mark.asyncio
async def test_chat_via_cli_backend_emits_hook():
    from praisonaiagents.agent.agent import Agent
    from praisonaiagents.hooks.types import HookResult

    captured = []

    def _handler(data):
        captured.append(data.to_dict())
        return HookResult.allow()

    reg = HookRegistry()
    reg.register_function(
        HookEvent.CLI_BACKEND_EXECUTE,
        _handler,
        name="capture",
    )

    agent = Agent(name="assistant", instructions="test", hooks=reg)
    agent._cli_backend = Mock()
    agent._cli_backend.config = CliBackendConfig(command="gemini")
    agent._cli_backend.execute = AsyncMock(
        return_value=CliBackendResult(
            content="ok",
            metadata={"command": ["gemini", "-p", "hi"]},
        )
    )

    result = await agent._chat_via_cli_backend("hello")
    assert result == "ok"
    assert len(captured) == 1
    assert captured[0]["backend"] == "gemini"
    assert captured[0]["command"] == ["gemini", "-p", "<redacted>"]


@pytest.mark.asyncio
async def test_chat_via_cli_backend_emits_hook_on_failure():
    """Subprocess startup errors must still surface through the hook."""
    from praisonaiagents.agent.agent import Agent
    from praisonaiagents.hooks.types import HookResult

    captured = []

    def _handler(data):
        captured.append(data.to_dict())
        return HookResult.allow()

    reg = HookRegistry()
    reg.register_function(
        HookEvent.CLI_BACKEND_EXECUTE,
        _handler,
        name="capture",
    )

    agent = Agent(name="assistant", instructions="test", hooks=reg)
    agent._cli_backend = Mock()
    agent._cli_backend.config = CliBackendConfig(command="gemini")
    agent._cli_backend.execute = AsyncMock(side_effect=RuntimeError("spawn failed"))

    with pytest.raises(RuntimeError):
        await agent._chat_via_cli_backend("hello")

    assert len(captured) == 1
    assert captured[0]["backend"] == "gemini"
    assert "spawn failed" in captured[0]["error"]
