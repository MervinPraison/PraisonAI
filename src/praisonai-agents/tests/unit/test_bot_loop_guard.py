"""Tests for the bot-to-bot pair loop protection guard (Issue #2683)."""

from praisonaiagents.bots import BotLoopGuard, BotLoopPolicy
from praisonaiagents.bots.silence import _pair_key


def test_below_budget_always_allows():
    guard = BotLoopGuard(BotLoopPolicy(max_events_per_window=5, window_seconds=60))
    now = 1000.0
    for i in range(5):
        assert guard.observe(self_bot_id="A", sender_bot_id="B", now=now + i) is True


def test_budget_exceeded_suppresses():
    guard = BotLoopGuard(BotLoopPolicy(max_events_per_window=3, window_seconds=60))
    now = 1000.0
    # First 3 allowed, 4th within the same window is suppressed.
    assert guard.observe(self_bot_id="A", sender_bot_id="B", now=now) is True
    assert guard.observe(self_bot_id="A", sender_bot_id="B", now=now + 1) is True
    assert guard.observe(self_bot_id="A", sender_bot_id="B", now=now + 2) is True
    assert guard.observe(self_bot_id="A", sender_bot_id="B", now=now + 3) is False


def test_pair_is_direction_independent():
    """A<->B and B<->A count as the same pair (a real loop alternates direction)."""
    guard = BotLoopGuard(BotLoopPolicy(max_events_per_window=3, window_seconds=60))
    now = 1000.0
    assert guard.observe(self_bot_id="A", sender_bot_id="B", now=now) is True
    assert guard.observe(self_bot_id="B", sender_bot_id="A", now=now + 1) is True
    assert guard.observe(self_bot_id="A", sender_bot_id="B", now=now + 2) is True
    # Fourth exchange (either direction) trips the budget.
    assert guard.observe(self_bot_id="B", sender_bot_id="A", now=now + 3) is False


def test_pair_key_canonical():
    assert _pair_key("A", "B") == _pair_key("B", "A")
    assert _pair_key("A", "B") == ("A", "B")


def test_sliding_window_evicts_old_events():
    guard = BotLoopGuard(BotLoopPolicy(max_events_per_window=2, window_seconds=10))
    now = 1000.0
    assert guard.observe(self_bot_id="A", sender_bot_id="B", now=now) is True
    assert guard.observe(self_bot_id="A", sender_bot_id="B", now=now + 1) is True
    # After the window slides past the first two events, budget is fresh again.
    assert guard.observe(self_bot_id="A", sender_bot_id="B", now=now + 20) is True
    assert guard.observe(self_bot_id="A", sender_bot_id="B", now=now + 21) is True


def test_cooldown_suppresses_then_recovers():
    guard = BotLoopGuard(
        BotLoopPolicy(max_events_per_window=2, window_seconds=60, cooldown_seconds=30)
    )
    now = 1000.0
    assert guard.observe(self_bot_id="A", sender_bot_id="B", now=now) is True
    assert guard.observe(self_bot_id="A", sender_bot_id="B", now=now + 1) is True
    # Third trips budget -> cooldown opens, suppressed.
    assert guard.observe(self_bot_id="A", sender_bot_id="B", now=now + 2) is False
    # Still within cooldown -> suppressed (no window reset).
    assert guard.observe(self_bot_id="A", sender_bot_id="B", now=now + 20) is False
    # After cooldown expires -> allowed again.
    assert guard.observe(self_bot_id="A", sender_bot_id="B", now=now + 40) is True


def test_disabled_policy_always_allows():
    guard = BotLoopGuard(BotLoopPolicy(enabled=False, max_events_per_window=1))
    now = 1000.0
    for i in range(10):
        assert guard.observe(self_bot_id="A", sender_bot_id="B", now=now + i) is True
    assert guard.enabled is False


def test_distinct_pairs_are_independent():
    guard = BotLoopGuard(BotLoopPolicy(max_events_per_window=2, window_seconds=60))
    now = 1000.0
    assert guard.observe(self_bot_id="A", sender_bot_id="B", now=now) is True
    assert guard.observe(self_bot_id="A", sender_bot_id="B", now=now + 1) is True
    # A<->B is now at budget, but A<->C is unaffected.
    assert guard.observe(self_bot_id="A", sender_bot_id="C", now=now + 2) is True
    assert guard.observe(self_bot_id="A", sender_bot_id="C", now=now + 3) is True
    assert guard.observe(self_bot_id="A", sender_bot_id="B", now=now + 4) is False


def test_reset_clears_state():
    guard = BotLoopGuard(BotLoopPolicy(max_events_per_window=1, window_seconds=60))
    now = 1000.0
    assert guard.observe(self_bot_id="A", sender_bot_id="B", now=now) is True
    assert guard.observe(self_bot_id="A", sender_bot_id="B", now=now + 1) is False
    guard.reset()
    assert guard.observe(self_bot_id="A", sender_bot_id="B", now=now + 2) is True


def test_from_dict_builds_policy():
    policy = BotLoopPolicy.from_dict(
        {"max_events_per_window": 5, "window_seconds": 30, "cooldown_seconds": 15}
    )
    assert policy.enabled is True
    assert policy.max_events_per_window == 5
    assert policy.window_seconds == 30.0
    assert policy.cooldown_seconds == 15.0


def test_from_dict_none_returns_default():
    policy = BotLoopPolicy.from_dict(None)
    assert policy.enabled is True
    assert policy.max_events_per_window == 20


def test_from_dict_ignores_unknown_keys():
    policy = BotLoopPolicy.from_dict({"max_events_per_window": 3, "future_key": "x"})
    assert policy.max_events_per_window == 3


def test_default_now_uses_wall_clock():
    """observe() works without an injected now (uses time.time())."""
    guard = BotLoopGuard(BotLoopPolicy(max_events_per_window=1, window_seconds=60))
    assert guard.observe(self_bot_id="A", sender_bot_id="B") is True
    assert guard.observe(self_bot_id="A", sender_bot_id="B") is False


def test_zero_budget_is_clamped_to_one():
    """max_events_per_window < 1 is clamped so the first exchange is not blocked."""
    policy = BotLoopPolicy(max_events_per_window=0)
    assert policy.max_events_per_window == 1
    guard = BotLoopGuard(policy)
    now = 1000.0
    # First exchange must still be allowed (not permanently blocked).
    assert guard.observe(self_bot_id="A", sender_bot_id="B", now=now) is True
    assert guard.observe(self_bot_id="A", sender_bot_id="B", now=now + 1) is False


def test_from_dict_clamps_zero_budget():
    policy = BotLoopPolicy.from_dict({"max_events_per_window": 0})
    assert policy.max_events_per_window == 1
