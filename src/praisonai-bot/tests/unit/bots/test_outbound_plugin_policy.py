"""Exercise plugin output decisions at the bot's final delivery boundary."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from praisonai_bot.bots import LocalBot
from praisonaiagents.hooks import HookEvent, HookRegistry, HookResult, HookRunner
from praisonaiagents.hooks.events import MessageSendingInput
from praisonaiagents.plugins.manager import PluginManager
from praisonaiagents.plugins.plugin import GuardrailBlocked, Plugin, PluginDecision, PluginInfo


class OutboundPolicy(Plugin):
    def __init__(self, decision):
        self.decision = decision
        self.seen = []

    @property
    def info(self):
        return PluginInfo(name="outbound_policy")

    def after_message(self, message):
        self.seen.append(message)
        if self.decision == "raise":
            raise GuardrailBlocked("Delivery withheld")
        if self.decision == "rewrite":
            return {**message, "content": "[REDACTED]"}
        return self.decision


def make_bot(decision, *, granted=True):
    plugin = OutboundPolicy(decision)
    manager = PluginManager()
    manager.register(plugin)
    if granted:
        manager.set_plugin_options({"outbound_policy": {"allow_conversation": True}})
    registry = HookRegistry()
    manager.wire_into_hook_registry(registry)
    runner = HookRunner(registry)
    bot = LocalBot(agent=SimpleNamespace(name="assistant", _hook_runner=runner))
    bot._session.chat = AsyncMock(return_value="private account details")
    bot.send_message = AsyncMock()
    sent = []
    registry.register_function(HookEvent.MESSAGE_SENT, lambda data: sent.append(data.content))
    return bot, plugin, sent


@pytest.mark.parametrize("decision", [
    PluginDecision.deny("Delivery withheld"),
    PluginDecision.block("Delivery withheld"),
    HookResult.deny("Delivery withheld"),
    HookResult.block("Delivery withheld"),
    "raise",
])
def test_denied_plugin_output_never_reaches_transport(decision):
    bot, plugin, sent = make_bot(decision)

    asyncio.run(bot._handle_line("look up my account"))

    bot._session.chat.assert_awaited_once()
    bot.send_message.assert_not_awaited()
    assert sent == []
    assert plugin.seen[0]["content"] == "private account details"
    assert plugin.seen[0]["channel_id"] == "local"


@pytest.mark.parametrize("decision", [None, PluginDecision.allow(), HookResult.allow()])
def test_allowed_plugin_output_is_delivered_once(decision):
    bot, _, sent = make_bot(decision)

    asyncio.run(bot._handle_line("look up my account"))

    bot.send_message.assert_awaited_once_with("local", "private account details")
    assert sent == ["private account details"]


def test_plugin_rewrite_is_the_content_delivered_and_observed():
    bot, _, sent = make_bot("rewrite")

    asyncio.run(bot._handle_line("look up my account"))

    bot.send_message.assert_awaited_once_with("local", "[REDACTED]")
    assert sent == ["[REDACTED]"]


def test_ungranted_plugin_cannot_read_or_block_output():
    bot, plugin, sent = make_bot(PluginDecision.block("Delivery withheld"), granted=False)

    asyncio.run(bot._handle_line("look up my account"))

    assert plugin.seen == []
    bot.send_message.assert_awaited_once_with("local", "private account details")
    assert sent == ["private account details"]


def test_explicit_guardrail_block_is_a_successful_policy_decision():
    bot, _, _ = make_bot("raise")
    runner = bot._agent._hook_runner
    data = MessageSendingInput(
        session_id="s", cwd=".", event_name=HookEvent.MESSAGE_SENDING,
        timestamp="now", content="private account details", channel_id="local",
    )

    results = runner.execute_sync(HookEvent.MESSAGE_SENDING, data)

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].error is None
    assert runner.is_blocked(results)
    assert runner.get_blocking_reason(results) == "Delivery withheld"


@pytest.mark.parametrize("decision, cancelled, observed", [
    (PluginDecision.block("Delivery withheld"), True, []),
    (HookResult(modified_input={"content": "[REDACTED]"}), False, ["[REDACTED]"]),
    ("rewrite", False, ["[REDACTED]"]),
])
def test_output_policies_compose_in_registration_order(decision, cancelled, observed):
    policy = OutboundPolicy(decision)

    class Observer(OutboundPolicy):
        @property
        def info(self):
            return PluginInfo(name="observer")

    observer = Observer(None)
    manager = PluginManager()
    manager.register(policy)
    manager.register(observer)
    manager.set_plugin_options({
        "outbound_policy": {"allow_conversation": True},
        "observer": {"allow_conversation": True},
    })
    registry = HookRegistry()
    manager.wire_into_hook_registry(registry)
    bot = LocalBot(agent=SimpleNamespace(name="assistant", _hook_runner=HookRunner(registry)))

    result = bot.fire_message_sending("local", "private account details")

    assert result["cancel"] is cancelled
    assert [message["content"] for message in observer.seen] == observed
    if not cancelled:
        assert result["content"] == "[REDACTED]"
