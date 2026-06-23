"""Regression tests for critical correctness fixes."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestBotStreamingBridge:
    """Bot streaming must bridge via stream_emitter, not astart(stream_callback=)."""

    @pytest.mark.asyncio
    async def test_streaming_does_not_pass_stream_callback_to_astart(self):
        from praisonai.bots._session import BotSessionManager

        agent = MagicMock()
        agent.chat_history = []
        agent.astart = AsyncMock(return_value="ok")
        emitter = MagicMock()
        agent.stream_emitter = emitter

        mgr = BotSessionManager()
        stream_cb = AsyncMock()
        await mgr.chat(agent, "user1", "hello", stream_callback=stream_cb)

        agent.astart.assert_called_once()
        _, kwargs = agent.astart.call_args
        assert "stream_callback" not in kwargs
        assert kwargs.get("stream") is True
        emitter.add_callback.assert_called_once()
        emitter.remove_callback.assert_called_once()


class TestBotDefaultToolResolver:
    """Default bot tools must resolve via praisonai.tool_resolver.ToolResolver."""

    def test_resolve_tool_names_uses_wrapper_tool_resolver(self):
        from praisonai.bots import _defaults

        with patch("praisonai.tool_resolver.ToolResolver") as mock_resolver_cls:
            mock_resolver = MagicMock()
            mock_resolver.resolve_many.return_value = [MagicMock()]
            mock_resolver_cls.return_value = mock_resolver

            with patch(
                "praisonaiagents.tools.profiles.resolve_profiles",
                return_value=[],
            ):
                tools = _defaults._resolve_tool_names_with_workspace(
                    ["clarify"], workspace=None
                )

        mock_resolver_cls.assert_called_once()
        mock_resolver.resolve_many.assert_called_once_with(["clarify"])
        assert len(tools) == 1
