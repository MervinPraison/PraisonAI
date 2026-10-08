"""Withhold account details at the final bot delivery boundary.

Install praisonaiagents and praisonai-bot, set OPENAI_API_KEY, then run this file.
This gate covers final bot replies; disable progressive drafts when using an
output policy. Direct transport sends do not pass through this hook.
"""

import asyncio

from praisonai_bot.bots import LocalBot
from praisonaiagents import Agent, HooksConfig
from praisonaiagents.hooks import HookRegistry
from praisonaiagents.plugins.manager import PluginManager
from praisonaiagents.plugins.plugin import Plugin, PluginDecision, PluginInfo


class AccountPolicy(Plugin):
    @property
    def info(self):
        return PluginInfo(name="account_policy")

    def after_message(self, message):
        if "account number" in message["content"].lower():
            return PluginDecision.block("Account details must not be sent to this channel")
        return message


async def main():
    manager = PluginManager()
    manager.register(AccountPolicy())
    # Conversation access must be explicitly granted to third-party plugins.
    manager.set_plugin_options({"account_policy": {"allow_conversation": True}})
    registry = HookRegistry()
    manager.wire_into_hook_registry(registry)
    with Agent(
        instructions="Answer briefly.", output="silent", reflection=False,
        hooks=HooksConfig(registry=registry),
    ) as agent:
        await LocalBot(agent=agent).start()


if __name__ == "__main__":
    asyncio.run(main())
