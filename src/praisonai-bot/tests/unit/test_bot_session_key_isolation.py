"""Colliding bot user ids must get separate persisted histories (Issue #6024)."""

import asyncio

from praisonaiagents.session.store import DefaultSessionStore
from praisonai_bot.bots._session import BotSessionManager


class _EchoAgent:
    def __init__(self):
        self.name = "support"
        self.chat_history = []
        self.seen = {}

    def chat(self, prompt):
        self.seen[prompt] = [m["content"] for m in self.chat_history if m["role"] == "user"]
        self.chat_history.append({"role": "user", "content": prompt})
        self.chat_history.append({"role": "assistant", "content": "ok"})
        return "ok"


def test_colliding_email_senders_are_isolated(tmp_path):
    mgr = BotSessionManager(store=DefaultSessionStore(session_dir=str(tmp_path)), platform="email")
    agent = _EchoAgent()

    async def main():
        await mgr.chat(agent, "alice.smith@example.com", "My account PIN is 4471.")
        await mgr.chat(agent, "alice_smith@example.com", "What do you know about me?")

    asyncio.run(main())
    assert "My account PIN is 4471." not in agent.seen["What do you know about me?"]
    assert len([p for p in tmp_path.iterdir() if p.suffix == ".json"]) == 2
