"""W1 — Outbound delivery mirror.

When a Bot pushes a message via ``Bot.send_message()`` (notifications,
scheduled deliveries, cross-platform replies), the mirror appends a
``{"role": "assistant", "mirror": True}`` entry to the user's session
so the agent has context next turn.
"""

from __future__ import annotations

from praisonai.bots._mirror import mirror_to_session
from praisonai.bots._session import BotSessionManager


class TestMirrorBasic:
    def test_mirror_appends_assistant_entry(self):
        mgr = BotSessionManager(platform="telegram")
        mgr._histories["alice"] = []

        ok = mirror_to_session(
            mgr,
            user_id="alice",
            message_text="Daily summary: 5 PRs merged.",
            source_label="cron",
        )

        assert ok is True
        history = mgr._histories["alice"]
        assert len(history) == 1
        assert history[0]["role"] == "assistant"
        assert "5 PRs merged" in history[0]["content"]
        assert history[0]["mirror"] is True
        assert history[0]["mirror_source"] == "cron"

    def test_mirror_creates_history_when_absent(self):
        mgr = BotSessionManager(platform="telegram")
        ok = mirror_to_session(mgr, user_id="bob", message_text="hello")
        assert ok is True
        assert "bob" in mgr._histories

    def test_mirror_with_resolver_uses_unified_key(self):
        from praisonaiagents.session.identity import InMemoryIdentityResolver

        resolver = InMemoryIdentityResolver()
        resolver.link("telegram", "12345", "alice-global")
        mgr = BotSessionManager(platform="telegram", identity_resolver=resolver)

        ok = mirror_to_session(mgr, user_id="12345", message_text="hi")
        assert ok is True
        # Stored under unified key, not platform user id
        assert "alice-global" in mgr._histories
        assert "12345" not in mgr._histories


class TestMirrorIsNonFatal:
    def test_mirror_swallows_exceptions(self):
        class BrokenManager:
            def _session_key(self, user_id):
                raise RuntimeError("boom")

        # Must not raise; returns False
        ok = mirror_to_session(BrokenManager(), user_id="alice", message_text="x")
        assert ok is False
