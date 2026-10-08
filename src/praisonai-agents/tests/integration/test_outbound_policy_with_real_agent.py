"""Opt-in LLM inference followed by the bot's final outbound policy gate."""

import asyncio
import os
from unittest.mock import AsyncMock

import pytest


@pytest.mark.live
@pytest.mark.parametrize("blocked", [False, True])
def test_real_agent_reply_obeys_outbound_plugin_policy(monkeypatch, tmp_path, blocked):
    from praisonaiagents import Agent, HooksConfig
    from praisonaiagents.hooks import HookRegistry
    from praisonaiagents.plugins.manager import PluginManager
    from praisonaiagents.plugins.plugin import Plugin, PluginDecision, PluginInfo

    LocalBot = pytest.importorskip("praisonai_bot.bots").LocalBot

    class DeliveryPolicy(Plugin):
        seen = None

        @property
        def info(self):
            return PluginInfo(name="delivery_policy")

        def after_message(self, message):
            self.seen = message["content"]
            if blocked:
                return PluginDecision.block("Delivery withheld")
            return {**message, "content": "Approved reply"}

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "home"))
    policy = DeliveryPolicy()
    manager = PluginManager()
    manager.register(policy)
    manager.set_plugin_options({"delivery_policy": {"allow_conversation": True}})
    registry = HookRegistry()
    manager.wire_into_hook_registry(registry)
    options = dict(
        llm={"model": os.getenv("PRAISONAI_TEST_MODEL", "openai/gpt-4o-mini"), "max_tokens": 96},
        instructions="Reply briefly.", reflection=False, rules=False,
        output="silent", hooks=HooksConfig(registry=registry),
    )
    if os.getenv("OPENAI_BASE_URL"):
        options["base_url"] = os.environ["OPENAI_BASE_URL"]

    with Agent(**options) as agent:
        bot = LocalBot(agent=agent)
        bot.send_message = AsyncMock()

        async def real_chat(_agent, _user_id, content, **kwargs):
            answer = await asyncio.to_thread(agent.start, content)
            print("Full Agent.start output:", answer)
            assert isinstance(answer, str) and answer.strip()
            return answer

        bot._session.chat = real_chat
        asyncio.run(bot._handle_line("Say hello in one short sentence."))

        assert isinstance(policy.seen, str) and policy.seen.strip()
        print("Outbound policy:", "blocked" if blocked else "rewritten")
        if blocked:
            bot.send_message.assert_not_awaited()
        else:
            bot.send_message.assert_awaited_once_with("local", "Approved reply")
