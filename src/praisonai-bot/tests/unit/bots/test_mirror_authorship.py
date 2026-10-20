"""#5928 — mirror entries record true authorship and never break alternation."""

from __future__ import annotations

import asyncio

from praisonai_bot.bots._mirror import coalesce_mirror_turns, mirror_to_session
from praisonai_bot.bots._session import BotSessionManager


def test_external_text_is_mirrored_as_labelled_user_turn():
    mgr = BotSessionManager(platform="telegram")
    mgr._histories["alice"] = []
    assert mirror_to_session(
        mgr, "alice", "Backup finished: 3 files",
        source_label="cron", authored_by="external",
    )
    entry = mgr._histories["alice"][0]
    assert entry["role"] == "user"
    assert entry["content"] == "[cron] Backup finished: 3 files"
    assert entry["mirror"] is True


def test_agent_text_stays_assistant_by_default():
    mgr = BotSessionManager(platform="telegram")
    mgr._histories["alice"] = []
    assert mirror_to_session(mgr, "alice", "Here is your brief", source_label="cron")
    assert mgr._histories["alice"][0]["role"] == "assistant"
    assert mgr._histories["alice"][0]["content"] == "Here is your brief"


def test_coalesce_merges_only_mirror_induced_runs():
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "assistant", "content": "brief 1", "mirror": True},
        {"role": "assistant", "content": "brief 2", "mirror": True},
        {"role": "user", "content": "[cron] out", "mirror": True},
    ]
    out = coalesce_mirror_turns(history)
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    assert out[1]["content"] == "hello\n\nbrief 1\n\nbrief 2"
    # Non-mirror same-role runs are left untouched.
    plain = [{"role": "user", "content": "a"}, {"role": "user", "content": "b"}]
    assert coalesce_mirror_turns(plain) == plain


def test_executor_forwards_external_authorship_to_accepting_handler():
    from praisonai_bot.scheduler.executor import ScheduledAgentExecutor

    seen = {}

    async def handler(delivery, text, authored_by="agent"):
        seen["authored_by"] = authored_by
        return True

    async def legacy(delivery, text):
        seen["legacy"] = text
        return True

    ex = ScheduledAgentExecutor.__new__(ScheduledAgentExecutor)
    ex._deliver = handler
    assert asyncio.run(ex._dispatch_delivery(object(), "x", authored_by="external"))
    assert seen["authored_by"] == "external"
    ex._deliver = legacy
    assert asyncio.run(ex._dispatch_delivery(object(), "y", authored_by="external"))
    assert seen["legacy"] == "y"


def test_reply_after_external_delivery_keeps_role_alternation():
    """A reply after a command/notice mirror must not send two user turns."""

    class _RecordingAgent:
        def __init__(self):
            self.chat_history = []
            self.sent = None

        def chat(self, prompt):
            self.sent = self.chat_history + [{"role": "user", "content": prompt}]
            self.chat_history = self.sent + [{"role": "assistant", "content": "ok"}]
            return "ok"

    mgr = BotSessionManager(platform="telegram")
    mgr._histories["alice"] = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    assert mirror_to_session(
        mgr, "alice", "Backup finished", source_label="cron", authored_by="external",
    )
    agent = _RecordingAgent()
    assert asyncio.run(mgr.chat(agent, "alice", "thanks, any errors?")) == "ok"

    roles = [m["role"] for m in agent.sent]
    assert roles == ["user", "assistant", "user"]
    assert agent.sent[-1]["content"] == "[cron] Backup finished\n\nthanks, any errors?"
