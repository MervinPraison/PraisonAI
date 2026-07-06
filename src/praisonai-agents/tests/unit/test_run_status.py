"""
Unit tests for the run-status controller and stall watchdog.
"""

import asyncio

import pytest

from praisonaiagents.bots import (
    RunPhase,
    RunStatusController,
    StallState,
    StallWatchdog,
)
from praisonaiagents.bots.protocols import PlatformCapabilities


class FakeClock:
    """Deterministic monotonic clock for tests."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class Recorder:
    def __init__(self) -> None:
        self.reactions = []
        self.labels = []

    async def react(self, emoji: str) -> None:
        self.reactions.append(emoji)

    async def label(self, text: str) -> None:
        self.labels.append(text)


# ---------------------------------------------------------------------------
# StallWatchdog
# ---------------------------------------------------------------------------


class TestStallWatchdog:
    def test_ok_below_soft(self):
        wd = StallWatchdog(soft_s=20, hard_s=60)
        assert wd.evaluate(0) == StallState.OK
        assert wd.evaluate(19.9) == StallState.OK

    def test_soft_at_threshold(self):
        wd = StallWatchdog(soft_s=20, hard_s=60)
        assert wd.evaluate(20) == StallState.SOFT
        assert wd.evaluate(59.9) == StallState.SOFT

    def test_hard_at_threshold(self):
        wd = StallWatchdog(soft_s=20, hard_s=60)
        assert wd.evaluate(60) == StallState.HARD
        assert wd.evaluate(1000) == StallState.HARD

    def test_reset_clears_state(self):
        wd = StallWatchdog(soft_s=20, hard_s=60)
        wd.evaluate(70)
        assert wd.state == StallState.HARD
        wd.reset()
        assert wd.state == StallState.OK

    def test_hard_never_below_soft(self):
        wd = StallWatchdog(soft_s=60, hard_s=20)
        # hard clamped up to soft; only SOFT/HARD at >=60
        assert wd.evaluate(30) == StallState.OK
        assert wd.evaluate(60) == StallState.HARD


# ---------------------------------------------------------------------------
# RunStatusController — enable / disable
# ---------------------------------------------------------------------------


class TestControllerEnablement:
    def test_disabled_by_default(self):
        rec = Recorder()
        c = RunStatusController(set_status_reaction=rec.react)
        assert c.enabled is False
        _run(c.on_phase(RunPhase.QUEUED))
        assert rec.reactions == []

    def test_enabled_requires_a_callback(self):
        c = RunStatusController(enabled=True)
        assert c.enabled is False

    def test_enabled_with_reaction_callback(self):
        rec = Recorder()
        c = RunStatusController(enabled=True, set_status_reaction=rec.react)
        assert c.enabled is True


# ---------------------------------------------------------------------------
# RunStatusController — phase rendering
# ---------------------------------------------------------------------------


class TestPhaseRendering:
    def test_first_phase_renders_immediately(self):
        rec = Recorder()
        clock = FakeClock()
        c = RunStatusController(
            enabled=True, set_status_reaction=rec.react, now=clock
        )
        _run(c.on_phase(RunPhase.QUEUED))
        assert rec.reactions == ["👀"]
        assert c.phase == RunPhase.QUEUED

    def test_intermediate_debounced(self):
        rec = Recorder()
        clock = FakeClock()
        c = RunStatusController(
            enabled=True,
            set_status_reaction=rec.react,
            debounce_ms=700,
            now=clock,
        )
        _run(c.on_phase(RunPhase.QUEUED))  # renders 👀
        # Immediate second transition within debounce window -> coalesced
        _run(c.on_phase(RunPhase.THINKING))
        assert rec.reactions == ["👀"]
        # Advance beyond debounce and tick to flush.
        clock.advance(0.8)
        _run(c.tick(0.8))
        assert rec.reactions == ["👀", "🧠"]

    def test_transition_after_debounce_renders(self):
        rec = Recorder()
        clock = FakeClock()
        c = RunStatusController(
            enabled=True,
            set_status_reaction=rec.react,
            debounce_ms=700,
            now=clock,
        )
        _run(c.on_phase(RunPhase.QUEUED))
        clock.advance(1.0)
        _run(c.on_phase(RunPhase.THINKING))
        assert rec.reactions == ["👀", "🧠"]

    def test_terminal_renders_immediately_despite_debounce(self):
        rec = Recorder()
        clock = FakeClock()
        c = RunStatusController(
            enabled=True,
            set_status_reaction=rec.react,
            debounce_ms=700,
            now=clock,
        )
        _run(c.on_phase(RunPhase.QUEUED))
        _run(c.on_phase(RunPhase.DONE))  # no advance; terminal is immediate
        assert rec.reactions == ["👀", "✅"]

    def test_error_terminal(self):
        rec = Recorder()
        c = RunStatusController(enabled=True, set_status_reaction=rec.react)
        _run(c.on_phase(RunPhase.ERROR))
        assert rec.reactions == ["❌"]


# ---------------------------------------------------------------------------
# RunStatusController — capability gating (reactions vs label)
# ---------------------------------------------------------------------------


class TestCapabilityGating:
    def test_label_fallback_when_no_reactions(self):
        rec = Recorder()
        caps = PlatformCapabilities()  # no supports_reactions attr -> dict-less
        # Force label path: provide only label callback.
        c = RunStatusController(
            caps=caps, enabled=True, edit_status_label=rec.label
        )
        _run(c.on_phase(RunPhase.THINKING))
        assert rec.labels == ["thinking…"]
        assert rec.reactions == []

    def test_reactions_preferred_when_both_and_supported(self):
        rec = Recorder()

        class Caps:
            supports_reactions = True

        c = RunStatusController(
            caps=Caps(),
            enabled=True,
            set_status_reaction=rec.react,
            edit_status_label=rec.label,
        )
        _run(c.on_phase(RunPhase.TOOL))
        assert rec.reactions == ["🛠️"]
        assert rec.labels == []

    def test_label_when_reactions_unsupported(self):
        rec = Recorder()

        class Caps:
            supports_reactions = False

        c = RunStatusController(
            caps=Caps(),
            enabled=True,
            set_status_reaction=rec.react,
            edit_status_label=rec.label,
        )
        _run(c.on_phase(RunPhase.TOOL))
        assert rec.labels == ["using a tool…"]
        assert rec.reactions == []


# ---------------------------------------------------------------------------
# RunStatusController — stall watchdog integration
# ---------------------------------------------------------------------------


class TestStallIntegration:
    def test_soft_then_hard_signals(self):
        rec = Recorder()
        clock = FakeClock()
        c = RunStatusController(
            enabled=True,
            set_status_reaction=rec.react,
            stall_soft_s=20,
            stall_hard_s=60,
            now=clock,
        )
        _run(c.on_phase(RunPhase.TOOL))
        assert rec.reactions == ["🛠️"]
        _run(c.tick(10))  # OK, no new signal
        assert rec.reactions == ["🛠️"]
        _run(c.tick(25))  # soft
        assert rec.reactions == ["🛠️", "⏳"]
        _run(c.tick(70))  # hard
        assert rec.reactions == ["🛠️", "⏳", "⚠️"]

    def test_stall_signal_not_repeated(self):
        rec = Recorder()
        c = RunStatusController(
            enabled=True,
            set_status_reaction=rec.react,
            stall_soft_s=20,
            stall_hard_s=60,
        )
        _run(c.on_phase(RunPhase.TOOL))
        _run(c.tick(25))
        _run(c.tick(30))  # still soft; should not re-emit
        assert rec.reactions == ["🛠️", "⏳"]

    def test_phase_change_clears_stall(self):
        rec = Recorder()
        c = RunStatusController(
            enabled=True,
            set_status_reaction=rec.react,
            stall_soft_s=20,
            stall_hard_s=60,
        )
        _run(c.on_phase(RunPhase.TOOL))
        _run(c.tick(25))  # soft
        assert c.watchdog.state == StallState.SOFT
        _run(c.on_phase(RunPhase.THINKING))  # progress clears stall
        assert c.watchdog.state == StallState.OK

    def test_no_stall_after_terminal(self):
        rec = Recorder()
        c = RunStatusController(
            enabled=True,
            set_status_reaction=rec.react,
            stall_soft_s=20,
            stall_hard_s=60,
        )
        _run(c.on_phase(RunPhase.DONE))
        _run(c.tick(100))
        assert rec.reactions == ["✅"]


class TestRenderRobustness:
    def test_render_failure_swallowed(self):
        async def boom(_emoji):
            raise RuntimeError("network down")

        c = RunStatusController(enabled=True, set_status_reaction=boom)
        # Should not raise.
        _run(c.on_phase(RunPhase.QUEUED))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
