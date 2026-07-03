"""Tests for bot session history compaction (issue #2197).

Long-lived gateway/bot sessions should compact older turns (summarise them
and keep a recent verbatim tail) instead of hard-truncating history, so
context survives weeks-long conversations and restarts. Truncation remains
the default when compaction is not configured.
"""

import pytest

from praisonai_bot.bots._session import BotSessionManager
from praisonai_bot.bots._config_schema import SessionCompactionConfigSchema

# The compaction path needs the core engine; skip cleanly in a minimal
# (wrapper-only) install rather than hard-failing on assertions below.
pytest.importorskip("praisonaiagents.compaction")


def _make_history(n: int, size: int = 200):
    return [
        {"role": "user", "content": f"message number {i} " + ("x" * size)}
        for i in range(n)
    ]


def test_default_truncation_unchanged():
    """Without compaction, the legacy tail-slice truncation is applied."""
    mgr = BotSessionManager(max_history=5)
    assert mgr._compaction_enabled is False
    mgr._save_history("u1", _make_history(12, size=4))
    saved = mgr._histories[mgr._storage_key("u1")]
    assert len(saved) == 5


def test_disabled_compaction_config_falls_back_to_truncation():
    cfg = SessionCompactionConfigSchema(enabled=False)
    mgr = BotSessionManager(max_history=5, compaction=cfg)
    assert mgr._compaction_enabled is False
    mgr._save_history("u2", _make_history(12, size=4))
    assert len(mgr._histories[mgr._storage_key("u2")]) == 5


def test_compaction_summarises_old_turns():
    cfg = SessionCompactionConfigSchema(
        enabled=True, strategy="summarize", max_messages=5, keep_recent=2
    )
    mgr = BotSessionManager(compaction=cfg)
    assert mgr._compaction_enabled is True

    history = _make_history(40)
    mgr._save_history("u3", history)
    saved = mgr._histories[mgr._storage_key("u3")]

    assert len(saved) < len(history)
    roles = [m.get("role") for m in saved]
    assert "system" in roles


def test_compaction_keeps_recent_tail_verbatim():
    cfg = SessionCompactionConfigSchema(
        enabled=True, strategy="summarize", max_messages=5, keep_recent=3
    )
    mgr = BotSessionManager(compaction=cfg)
    history = _make_history(30)
    mgr._save_history("u4", history)
    saved = mgr._histories[mgr._storage_key("u4")]

    assert saved[-1]["content"] == history[-1]["content"]


def test_compaction_config_accepts_dict():
    mgr = BotSessionManager(
        compaction={"enabled": True, "strategy": "truncate", "max_messages": 10}
    )
    assert mgr._compaction_enabled is True


def test_compaction_config_max_tokens_overrides_messages():
    cfg = SessionCompactionConfigSchema(
        enabled=True, strategy="summarize", max_tokens=100, keep_recent=2
    )
    mgr = BotSessionManager(compaction=cfg)
    assert mgr._compaction_enabled is True
    # A per-call compactor is built from config; verify the token budget.
    assert mgr._build_compactor(mgr._compaction_config).max_tokens == 100


def test_invalid_strategy_rejected():
    with pytest.raises(ValueError):
        SessionCompactionConfigSchema(enabled=True, strategy="bogus")


def test_compaction_persists_to_store():
    class _Store:
        def __init__(self):
            self.data = {}

        def get_chat_history(self, key):
            return self.data.get(key, [])

        def set_chat_history(self, key, history):
            self.data[key] = list(history)

        def clear_session(self, key):
            self.data.pop(key, None)

    store = _Store()
    cfg = SessionCompactionConfigSchema(
        enabled=True, strategy="summarize", max_messages=5, keep_recent=2
    )
    mgr = BotSessionManager(store=store, platform="telegram", compaction=cfg)
    history = _make_history(40)
    mgr._save_history("u5", history)

    key = mgr._session_key("u5")
    assert key in store.data
    assert len(store.data[key]) < len(history)


def test_compaction_isolated_across_users_on_one_manager():
    """A single manager must not leak compaction state between users.

    The core ContextCompactor carries mutable per-conversation state, so the
    manager builds a fresh compactor per save. Two users on the same manager
    must each get their own summary with no cross-contamination.
    """
    cfg = SessionCompactionConfigSchema(
        enabled=True, strategy="summarize", max_messages=5, keep_recent=2
    )
    mgr = BotSessionManager(compaction=cfg)

    hist_a = [
        {"role": "user", "content": f"ALPHA topic {i} " + ("x" * 200)}
        for i in range(40)
    ]
    hist_b = [
        {"role": "user", "content": f"BETA topic {i} " + ("y" * 200)}
        for i in range(40)
    ]

    mgr._save_history("alice", hist_a)
    mgr._save_history("bob", hist_b)

    saved_a = mgr._histories[mgr._storage_key("alice")]
    saved_b = mgr._histories[mgr._storage_key("bob")]

    text_a = " ".join(str(m.get("content", "")) for m in saved_a)
    text_b = " ".join(str(m.get("content", "")) for m in saved_b)

    # Each user's summary must reference only their own topic.
    assert "ALPHA" in text_a and "BETA" not in text_a
    assert "BETA" in text_b and "ALPHA" not in text_b


def test_max_history_hard_cap_in_compaction_mode():
    """Short messages under-shoot the token estimate, but max_history still
    bounds in-memory history growth in compaction mode."""
    cfg = SessionCompactionConfigSchema(
        enabled=True, strategy="summarize", max_messages=5, keep_recent=2
    )
    mgr = BotSessionManager(max_history=5, compaction=cfg)
    # Tiny messages: token budget (5*80=400 tokens) won't trigger compaction.
    history = _make_history(1000, size=1)
    mgr._save_history("u6", history)
    saved = mgr._histories[mgr._storage_key("u6")]
    # Hard cap = max_history * 4 = 20; history must not grow unbounded.
    assert len(saved) <= mgr._max_history * 4
