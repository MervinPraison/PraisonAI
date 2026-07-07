"""Regression tests for critical correctness bugs found on 2026-06-18."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCliBackendValidation:
    """PR #1988 regression: adapter object was passed instead of framework name."""

    def test_cli_backend_allowed_for_praisonai_framework(self):
        from praisonai.agents_generator import AgentsGenerator

        gen = object.__new__(AgentsGenerator)
        config = {
            "framework": "praisonai",
            "roles": {
                "coder": {
                    "role": "Coder",
                    "goal": "Write code",
                    "backstory": "Engineer",
                    "cli_backend": "claude-code",
                }
            },
        }

        # Must not raise — runtime features are valid on praisonai.
        AgentsGenerator._validate_cli_backend_compatibility(gen, config, "praisonai")

    def test_cli_backend_rejected_for_non_praisonai_framework(self):
        from praisonai.agents_generator import AgentsGenerator

        gen = object.__new__(AgentsGenerator)
        gen.logger = MagicMock()
        config = {
            "framework": "crewai",
            "roles": {
                "worker": {
                    "role": "Worker",
                    "goal": "Work",
                    "backstory": "Helper",
                    "runtime": "cli",
                }
            },
        }

        with pytest.raises(ValueError, match="not supported for framework='crewai'"):
            AgentsGenerator._validate_cli_backend_compatibility(gen, config, "crewai")


class TestBotStreamingPath:
    """Progressive streaming must not pass stream_callback kwarg to achat()."""

    @pytest.mark.asyncio
    async def test_streaming_bridges_via_stream_emitter_and_passes_cancel_token(self):
        from praisonai.bots._session import BotSessionManager

        mgr = BotSessionManager()
        agent = MagicMock()
        agent.chat_history = []

        emitter = MagicMock()
        emitter.add_callback = MagicMock()
        emitter.remove_callback = MagicMock()
        agent.stream_emitter = emitter

        controller = MagicMock()
        controller.is_set = MagicMock(return_value=False)

        async def fake_astart(prompt, **kwargs):
            assert "stream_callback" not in kwargs
            assert kwargs.get("stream") is True
            assert kwargs.get("cancel_token") is controller
            return "streamed reply"

        agent.astart = AsyncMock(side_effect=fake_astart)

        with patch("praisonaiagents.agent.interrupt.InterruptController") as mock_interrupt:
            mock_interrupt.return_value = controller
            response = await mgr.chat(
                agent,
                "user-1",
                "hello",
                stream_callback=AsyncMock(),
            )

        assert response == "streamed reply"
        emitter.add_callback.assert_called_once()
        emitter.remove_callback.assert_called_once()


class TestBotDefaultToolResolution:
    """Bot defaults must resolve tools via praisonai.tool_resolver.ToolResolver."""

    def test_resolve_tool_names_uses_praisonai_tool_resolver(self):
        from praisonai.bots._defaults import _resolve_tool_names_with_workspace

        sentinel = object()
        with patch(
            "praisonaiagents.tools.profiles.resolve_profiles",
            return_value=[sentinel],
        ) as mock_profiles:
            resolved = _resolve_tool_names_with_workspace(["search_web"])

        assert sentinel in resolved
        mock_profiles.assert_called_once_with("web")
