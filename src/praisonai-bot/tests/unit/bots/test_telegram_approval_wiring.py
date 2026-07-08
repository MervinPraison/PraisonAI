"""Tests for wiring the durable PresentationApprovalBackend into the live
Telegram interactive-callback path (issue #2797).

Verifies that a `cmd:/approve <approval_id> <decision>` button tap dispatched
through the adapter's InteractiveRegistry resolves against the durable,
actor-authorised backend instead of dying as an "Unhandled callback".
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock

from praisonaiagents.bots import BotConfig, InteractiveContext
from praisonai_bot.bots.telegram import TelegramBot
from praisonai_bot.bots._presentation_approval_backend import (
    PresentationApprovalBackend,
)


def _make_bot() -> TelegramBot:
    config = BotConfig(token="test_token")
    return TelegramBot(token="test_token", config=config)


def _make_query(text: str = "Tool Approval Required"):
    query = MagicMock()
    query.message = MagicMock()
    query.message.text = text
    query.edit_message_text = AsyncMock()
    return query


def _make_ctx(bot, callback_data: str, user_id: str, query) -> InteractiveContext:
    return InteractiveContext(
        callback_data=callback_data,
        user_id=user_id,
        message_id="1",
        chat_id="chat-1",
        bot_adapter=bot,
        platform_data={"query": query},
    )


def _make_request(approval_id="abc123", tool_name="delete_file"):
    from praisonaiagents.approval import ApprovalRequest

    return ApprovalRequest(
        tool_name=tool_name,
        arguments={"path": "/etc/passwd"},
        risk_level="high",
        approval_id=approval_id,
    )


def test_register_approval_backend_wires_sender_and_target():
    bot = _make_bot()
    backend = PresentationApprovalBackend(allowed_actors={"owner"})

    bot.register_approval_backend(backend, target="chat-1")

    assert bot._approval_backend is backend
    assert backend._target == "chat-1"
    # The channel sender is the adapter's presentation renderer so the backend
    # can render Allow/Deny buttons onto the chat.
    assert backend._channel_send_func == bot.render_presentation


def test_approve_callback_resolves_via_durable_backend():
    """An authorized /approve tap dispatched through the live registry resolves
    the durable backend's pending approval."""

    async def run():
        bot = _make_bot()
        backend = PresentationApprovalBackend(allowed_actors={"owner"})
        bot.register_approval_backend(backend, target="chat-1")

        request = _make_request(approval_id="wire-id")

        async def tap_later():
            await asyncio.sleep(0.01)
            query = _make_query()
            ctx = _make_ctx(bot, "cmd:/approve wire-id allow", "owner", query)
            handled = await bot._interactive_registry.dispatch(ctx)
            return handled, query

        async def ask():
            backend._timeout = 1.0
            return await backend.request_approval(request)

        decision, (handled, query) = await asyncio.gather(ask(), tap_later())
        return decision, handled, query

    decision, handled, query = asyncio.run(run())
    assert handled is True
    assert decision.approved is True
    query.edit_message_text.assert_awaited()


def test_unauthorized_actor_tap_does_not_resolve():
    """A stranger's tap must not resolve the approval; the request fails closed."""

    async def run():
        bot = _make_bot()
        backend = PresentationApprovalBackend(allowed_actors={"owner"})
        bot.register_approval_backend(backend, target="chat-1")

        request = _make_request(approval_id="stranger-id")

        async def tap_later():
            await asyncio.sleep(0.01)
            query = _make_query()
            ctx = _make_ctx(bot, "cmd:/approve stranger-id allow", "stranger", query)
            return await bot._interactive_registry.dispatch(ctx)

        async def ask():
            backend._timeout = 0.2
            return await backend.request_approval(request)

        decision, handled = await asyncio.gather(ask(), tap_later())
        return decision, handled

    decision, handled = asyncio.run(run())
    assert decision.approved is False


def test_approve_callback_ignored_without_backend():
    """With no backend wired, a /approve tap is not routed as an approval and
    falls through (returns unhandled)."""

    async def run():
        bot = _make_bot()
        bot._command_policy = MagicMock()
        bot._command_policy.can_run = MagicMock(return_value=True)
        query = _make_query()
        ctx = _make_ctx(bot, "cmd:/approve some-id allow", "owner", query)
        return await bot._interactive_registry.dispatch(ctx)

    handled = asyncio.run(run())
    assert handled is False


@pytest.mark.asyncio
async def test_rehydrate_approvals_noop_without_backend():
    bot = _make_bot()
    assert await bot.rehydrate_approvals() == 0


def test_autowire_agent_approval_backend():
    """A durable backend attached to the agent (via --approval presentation) is
    auto-wired to the channel on start without explicit registration."""
    bot = _make_bot()
    backend = PresentationApprovalBackend(allowed_actors={"owner"})

    agent = MagicMock()
    agent._approval_backend = backend
    bot._agent = agent

    bot._autowire_agent_approval_backend()

    assert bot._approval_backend is backend
    assert backend._channel_send_func == bot.render_presentation


def test_autowire_ignores_non_durable_backend():
    """A backend without the durable contract (no handle_callback/rehydrate) is
    not auto-wired."""
    bot = _make_bot()
    agent = MagicMock()
    agent._approval_backend = object()  # lacks handle_callback/rehydrate
    bot._agent = agent

    bot._autowire_agent_approval_backend()

    assert bot._approval_backend is None
