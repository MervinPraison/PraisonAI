"""The anti-thrashing guard must be able to go stale.

``_low_savings_streak`` stops a compactor that cannot shrink a conversation
from burning a summarisation call every turn. The streak is only cleared
*after* a compaction actually runs -- but the guard returns before reaching
that code, so once it latched it could never be released. A long-running
agent that tripped it stopped compacting for the rest of the session and its
context grew without bound, which is the precise opposite of what auto
compaction is for.

These tests pin both halves of the contract: the guard still suppresses
repeat passes on an unchanged conversation, and it releases once the
conversation has grown enough to be worth re-testing.
"""

import pytest

from praisonaiagents.compaction import CompactionConfig, ContextCompactor


def _config(**overrides):
    """A tight budget so a handful of turns is enough to trip the guard."""
    base = dict(
        max_tokens=200,
        target_tokens=150,
        preserve_recent=2,
        min_savings_pct=10.0,
        max_consecutive_low_savings=2,
    )
    base.update(overrides)
    return CompactionConfig(**base)


def _conversation(turns):
    """A highly compactible conversation: repetitive, summarisable turns."""
    return [{"role": "system", "content": "sys"}] + [
        {"role": "user", "content": f"Please refactor module_{i}.py and keep the public API stable."}
        for i in range(turns)
    ]


def _latched(config, at_tokens):
    """A compactor in the state a long session reaches after two low-yield passes."""
    compactor = ContextCompactor(config=config, strategy="summarize")
    compactor._low_savings_streak = config.max_consecutive_low_savings
    compactor._low_savings_tokens = at_tokens
    return compactor


class TestGuardHolds:
    """Anti-thrashing behaviour must be preserved."""

    def test_unchanged_conversation_is_still_skipped(self):
        """Re-running on identical input is the thrashing the guard exists to stop."""
        config = _config()
        messages = _conversation(200)
        probe = ContextCompactor(config=config, strategy="summarize")
        compactor = _latched(config, probe.count_total_tokens(messages))

        _, result = compactor.compact(messages)

        assert result.was_skipped_due_to_low_savings
        assert result.messages_removed == 0

    def test_marginal_growth_is_still_skipped(self):
        """Growth below the retry threshold is not new evidence.

        A couple of extra turns does not justify re-running a summarisation
        that just failed to pay for itself; without this the release would
        fire on essentially every turn.
        """
        config = _config()
        probe = ContextCompactor(config=config, strategy="summarize")
        compactor = _latched(config, probe.count_total_tokens(_conversation(200)))

        _, result = compactor.compact(_conversation(205))

        assert result.was_skipped_due_to_low_savings


class TestGuardReleases:
    """A materially larger conversation is new evidence."""

    def test_growth_releases_the_guard(self):
        """Past the threshold the verdict is retried, and the retry pays off."""
        config = _config()
        probe = ContextCompactor(config=config, strategy="summarize")
        compactor = _latched(config, probe.count_total_tokens(_conversation(200)))

        _, result = compactor.compact(_conversation(300))

        assert not result.was_skipped_due_to_low_savings
        assert result.messages_removed > 0
        # And it must actually shrink -- a released guard that yields nothing
        # would mean the release is cosmetic.
        assert result.compacted_tokens < result.original_tokens

    def test_release_matches_a_fresh_compactor(self):
        """The clearest statement of the bug.

        A latched compactor used to hand back untouched the very input an
        otherwise-identical fresh one shrinks by ~96%. Once released the two
        must be indistinguishable.
        """
        config = _config()
        messages = _conversation(300)
        probe = ContextCompactor(config=config, strategy="summarize")
        latched = _latched(config, probe.count_total_tokens(_conversation(200)))
        fresh = ContextCompactor(config=config, strategy="summarize")

        _, latched_result = latched.compact(messages)
        _, fresh_result = fresh.compact(messages)

        assert latched_result.compacted_tokens == fresh_result.compacted_tokens

    def test_streak_resets_so_the_full_allowance_returns(self):
        """Releasing must clear the streak, not merely skip the check once.

        A release that left the streak at the cap would re-latch on the next
        call, turning the fix into a one-shot reprieve.
        """
        config = _config()
        probe = ContextCompactor(config=config, strategy="summarize")
        compactor = _latched(config, probe.count_total_tokens(_conversation(200)))

        compactor.compact(_conversation(300))

        assert compactor._low_savings_streak < config.max_consecutive_low_savings

    def test_needs_compaction_agrees_with_compact(self):
        """Both gates must release together.

        ``needs_compaction()`` is the public gate callers consult. If it kept
        reporting False the release would never be reached in the agent's real
        code path, and fixing ``compact()`` alone would be dead code.
        """
        config = _config()
        probe = ContextCompactor(config=config, strategy="summarize")
        compactor = _latched(config, probe.count_total_tokens(_conversation(200)))

        assert compactor.needs_compaction(_conversation(300)) is True

    def test_needs_compaction_still_declines_an_unchanged_conversation(self):
        """The other half of that agreement: both gates must also hold together."""
        config = _config()
        messages = _conversation(200)
        probe = ContextCompactor(config=config, strategy="summarize")
        compactor = _latched(config, probe.count_total_tokens(messages))

        assert compactor.needs_compaction(messages) is False


class TestLongSession:
    """End-to-end: the failure this guard bug actually caused."""

    def test_compaction_keeps_engaging_across_a_long_session(self):
        """No white-box setup: drive a real session and watch compaction die.

        This is the failure a user actually hits, reproduced only through the
        public API, so it stands even if the guard's internals are reworked.
        """
        config = CompactionConfig(max_tokens=300, target_tokens=200, preserve_recent=2)
        compactor = ContextCompactor(config=config, strategy="summarize")
        messages = [{"role": "system", "content": "You are a coding agent."}]
        events = 0

        for turn in range(1, 41):
            messages.extend([
                {"role": "user", "content": f"Step {turn}: refactor module_{turn}.py, keep the API stable."},
                {"role": "assistant", "content": f"Done: module_{turn}.py refactored, helper_{turn}() extracted."},
            ])
            compacted, result = compactor.compact(messages)
            messages[:] = compacted
            if result.messages_removed:
                events += 1

        # Before the fix this latched at 4 events and then never fired again,
        # letting the context grow unbounded for the rest of the session.
        assert events > 4, f"compaction stopped engaging after {events} events"


@pytest.mark.parametrize("strategy", ["summarize", "truncate", "sliding"])
def test_guard_release_is_strategy_independent(strategy):
    """The guard lives above strategy selection, so it must not favour one."""
    config = _config()
    probe = ContextCompactor(config=config, strategy=strategy)
    compactor = _latched(config, probe.count_total_tokens(_conversation(200)))

    _, result = compactor.compact(_conversation(300))

    assert not result.was_skipped_due_to_low_savings
