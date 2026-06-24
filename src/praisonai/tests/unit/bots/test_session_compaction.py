"""Tests for bot session history compaction (issue #2197).

Long-lived gateway/bot sessions should compact older turns (summarise them
and keep a recent verbatim tail) instead of hard-truncating history, so
context survives weeks-long conversations and restarts. Truncation remains
the default when compaction is not configured.
"""

from praisonai.bots._session import BotSessionManager
from praisonai.bots._config_schema import SessionCompactionConfigSchema


def _make_history(n: int, size: int = 200):
    return [
        {"role": "user", "content": f"message number {i} " + ("x" * size)}
        for i in range(n)
    ]


def test_default_truncation_unchanged():
    """Without compaction, the legacy tail-slice truncation is applied."""
    mgr = BotSessionManager(max_history=5)
    assert mgr._compactor is None
    mgr._save_history("u1", _make_history(12, size=4))
    saved = mgr._histories[mgr._storage_key("u1")]
    assert len(saved) == 5


def test_disabled_compaction_config_falls_back_to_truncation():
    cfg = SessionCompactionConfigSchema(enabled=False)
    mgr = BotSessionManager(max_history=5, compaction=cfg)
    assert mgr._compactor is None
    mgr._save_history("u2", _make_history(12, size=4))
    assert len(mgr._histories[mgr._storage_key("u2")]) == 5


def test_compaction_summarises_old_turns():
    cfg = SessionCompactionConfigSchema(
        enabled=True, strategy="summarize", max_messages=5, keep_recent=2
    )
    mgr = BotSessionManager(compaction=cfg)
    assert mgr._compactor is not None

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
    assert mgr._compactor is not None


def test_compaction_config_max_tokens_overrides_messages():
    cfg = SessionCompactionConfigSchema(
        enabled=True, strategy="summarize", max_tokens=100, keep_recent=2
    )
    mgr = BotSessionManager(compaction=cfg)
    assert mgr._compactor is not None
    assert mgr._compactor.max_tokens == 100


def test_invalid_strategy_rejected():
    import pytest

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
