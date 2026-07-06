"""
Run-status controller and stall watchdog for bot gateways.

A pure, transport-agnostic run-presentation policy that advances an in-chat
reaction (or a status-label edit on channels without reactions) through the
agent run lifecycle, plus an armable stall watchdog that surfaces "still
working…" / "taking longer than expected" signals when a run goes quiet.

This complements the one-shot ``AckReactor`` (receipt -> done only) in
``praisonai_bot.bots`` with a *progressing* phase state machine driven by the
same run lifecycle signals the ack lifecycle and streaming already consume.
No new agent instrumentation is required.

Design (mirrors ``silence.py`` / ``presentation.py``): zero transport imports.
Channel adapters inject two capability-gated async callbacks and the controller
decides *which* to use from :class:`PlatformCapabilities`:

* ``set_status_reaction(emoji)`` — used when the channel supports reactions.
* ``edit_status_label(label)``   — used to degrade gracefully to a status line.

Off by default: adapters opt in (``streaming.status_reactions: true``).

Usage::

    controller = RunStatusController(
        caps,
        set_status_reaction=react_fn,     # async (emoji: str) -> None
        edit_status_label=edit_fn,        # async (label: str) -> None
    )
    await controller.on_phase(RunPhase.QUEUED)     # 👀
    await controller.on_phase(RunPhase.THINKING)   # 🧠
    await controller.on_phase(RunPhase.TOOL)       # 🛠️
    # if the run goes quiet, drive the watchdog from a periodic ticker:
    await controller.tick(elapsed_s)               # ⏳ then ⚠️
    await controller.on_phase(RunPhase.DONE)       # ✅
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING, Awaitable, Callable, Optional

if TYPE_CHECKING:
    from .protocols import PlatformCapabilities

logger = logging.getLogger(__name__)


class RunPhase(Enum):
    """Progressing run phases surfaced to the chat channel.

    Advances QUEUED -> THINKING -> TOOL -> DONE/ERROR. Intermediate
    transitions are debounced to avoid flicker; terminal transitions
    (DONE/ERROR) are applied immediately.
    """

    QUEUED = "queued"
    THINKING = "thinking"
    TOOL = "tool"
    DONE = "done"
    ERROR = "error"

    @property
    def is_terminal(self) -> bool:
        """Whether this phase ends the run (applied immediately, no debounce)."""
        return self in (RunPhase.DONE, RunPhase.ERROR)


class StallState(Enum):
    """Watchdog stall states derived from elapsed-since-last-progress time."""

    OK = "ok"
    SOFT = "soft"  # "still working…"
    HARD = "hard"  # "taking longer than expected"


DEFAULT_PHASE_EMOJI = {
    RunPhase.QUEUED: "👀",
    RunPhase.THINKING: "🧠",
    RunPhase.TOOL: "🛠️",
    RunPhase.DONE: "✅",
    RunPhase.ERROR: "❌",
}

DEFAULT_STALL_EMOJI = {
    StallState.SOFT: "⏳",
    StallState.HARD: "⚠️",
}

DEFAULT_PHASE_LABEL = {
    RunPhase.QUEUED: "queued",
    RunPhase.THINKING: "thinking…",
    RunPhase.TOOL: "using a tool…",
    RunPhase.DONE: "done",
    RunPhase.ERROR: "error",
}

DEFAULT_STALL_LABEL = {
    StallState.SOFT: "still working…",
    StallState.HARD: "this is taking longer than expected",
}


class StallWatchdog:
    """Pure soft/hard stall threshold evaluator.

    Maps an ``elapsed_s`` (seconds since the last observed progress) to a
    :class:`StallState`. Holds no clock of its own — the caller feeds elapsed
    time from a periodic ticker or the same progress signal that drives phases,
    keeping this fully deterministic and testable.
    """

    def __init__(self, *, soft_s: float = 20.0, hard_s: float = 60.0) -> None:
        if hard_s < soft_s:
            hard_s = soft_s
        self._soft_s = float(soft_s)
        self._hard_s = float(hard_s)
        self._state = StallState.OK

    @property
    def state(self) -> StallState:
        """The most recently evaluated stall state."""
        return self._state

    def evaluate(self, elapsed_s: float) -> StallState:
        """Return the stall state for ``elapsed_s`` seconds without progress."""
        if elapsed_s >= self._hard_s:
            state = StallState.HARD
        elif elapsed_s >= self._soft_s:
            state = StallState.SOFT
        else:
            state = StallState.OK
        self._state = state
        return state

    def reset(self) -> None:
        """Clear the stall state (call on any real progress / phase change)."""
        self._state = StallState.OK


ReactionFn = Callable[[str], Awaitable[None]]
LabelFn = Callable[[str], Awaitable[None]]


class RunStatusController:
    """Transport-agnostic run-status state machine with a stall watchdog.

    Drives a chat-visible status through the run lifecycle. Reactions are used
    when :attr:`PlatformCapabilities.reactions`-style support is present;
    otherwise it degrades to editing a single status label. Both rendering
    callbacks are optional and injected by the channel adapter.

    Args:
        caps: Platform capabilities used to gate reaction vs label rendering.
            When ``caps`` exposes a truthy ``supports_reactions`` (or dict-style
            ``reactions``) the controller renders reactions; otherwise it uses
            the label callback.
        set_status_reaction: Async callback ``(emoji) -> None`` to set the
            single status reaction (implementations typically swap the prior
            emoji). Optional.
        edit_status_label: Async callback ``(label) -> None`` to edit a single
            status line/label. Optional.
        debounce_ms: Minimum spacing between *intermediate* renders to avoid
            flicker. Terminal phases (DONE/ERROR) always render immediately.
        stall_soft_s: Seconds without progress before the soft stall signal.
        stall_hard_s: Seconds without progress before the hard stall signal.
        enabled: Master switch. Off by default; adapters opt in.
        now: Monotonic clock callable (injectable for tests).
    """

    def __init__(
        self,
        caps: Optional["PlatformCapabilities"] = None,
        *,
        set_status_reaction: Optional[ReactionFn] = None,
        edit_status_label: Optional[LabelFn] = None,
        debounce_ms: int = 700,
        stall_soft_s: float = 20.0,
        stall_hard_s: float = 60.0,
        enabled: bool = False,
        now: Optional[Callable[[], float]] = None,
    ) -> None:
        self._caps = caps
        self._set_reaction = set_status_reaction
        self._edit_label = edit_status_label
        self._debounce_s = max(0.0, debounce_ms / 1000.0)
        self._enabled = enabled
        self.watchdog = StallWatchdog(soft_s=stall_soft_s, hard_s=stall_hard_s)

        if now is None:
            import time

            now = time.monotonic
        self._now = now

        self._phase: Optional[RunPhase] = None
        self._rendered_phase: Optional[RunPhase] = None
        self._pending_phase: Optional[RunPhase] = None
        self._last_render_at: float = 0.0
        self._stall_shown: StallState = StallState.OK

    @property
    def enabled(self) -> bool:
        """Whether the controller will render anything at all."""
        if not self._enabled:
            return False
        return self._set_reaction is not None or self._edit_label is not None

    @property
    def phase(self) -> Optional[RunPhase]:
        """The last phase supplied via :meth:`on_phase` (may be un-rendered)."""
        return self._phase

    def _use_reactions(self) -> bool:
        """Decide reaction vs label rendering from capabilities and callbacks."""
        if self._set_reaction is None:
            return False
        if self._edit_label is None:
            return True
        caps = self._caps
        if caps is None:
            return True
        supports = getattr(caps, "supports_reactions", None)
        if supports is None:
            # Dict-style ChannelCapabilities fallback.
            try:
                supports = caps.get("reactions")  # type: ignore[attr-defined]
            except AttributeError:
                supports = None
        return bool(supports) if supports is not None else True

    async def _render(self, *, emoji: str, label: str) -> None:
        """Render the given emoji/label via the capability-gated callback."""
        try:
            if self._use_reactions() and self._set_reaction is not None:
                await self._set_reaction(emoji)
            elif self._edit_label is not None:
                await self._edit_label(label)
        except Exception as e:  # pragma: no cover - defensive; never break a run
            logger.debug("RunStatusController: render failed: %s", e)

    async def on_phase(self, phase: RunPhase) -> None:
        """Advance to ``phase``.

        Intermediate phases are debounced (coalesced) to avoid flicker; the
        most recent pending phase wins when the debounce window elapses (drive
        via :meth:`tick`). Terminal phases render immediately and clear any
        pending intermediate phase and stall signal.
        """
        self._phase = phase
        # Any phase change is real progress -> clear the stall watchdog.
        self.watchdog.reset()
        self._stall_shown = StallState.OK

        if not self.enabled:
            return

        if phase.is_terminal:
            self._pending_phase = None
            await self._apply_phase(phase)
            return

        if self._rendered_phase is None:
            # First intermediate phase renders immediately for responsiveness.
            await self._apply_phase(phase)
            return

        now = self._now()
        if now - self._last_render_at >= self._debounce_s:
            await self._apply_phase(phase)
        else:
            # Coalesce: remember the latest phase; flushed on the next tick().
            self._pending_phase = phase

    async def _apply_phase(self, phase: RunPhase) -> None:
        self._rendered_phase = phase
        self._pending_phase = None
        self._last_render_at = self._now()
        await self._render(
            emoji=DEFAULT_PHASE_EMOJI.get(phase, ""),
            label=DEFAULT_PHASE_LABEL.get(phase, phase.value),
        )

    async def tick(self, elapsed_s: float) -> None:
        """Drive debounced phase flush and the stall watchdog.

        Call periodically while a run is in flight. ``elapsed_s`` is the time
        since the last observed progress (phase change or run event). Flushes a
        coalesced pending phase once the debounce window has elapsed, then arms
        the soft/hard stall signal when the corresponding threshold is crossed.
        """
        if not self.enabled:
            return

        # Flush a debounced pending intermediate phase if it's now due.
        if self._pending_phase is not None:
            now = self._now()
            if now - self._last_render_at >= self._debounce_s:
                await self._apply_phase(self._pending_phase)

        # Do not arm stall signals once the run has terminated.
        if self._phase is not None and self._phase.is_terminal:
            return

        state = self.watchdog.evaluate(elapsed_s)
        if state == self._stall_shown:
            return
        self._stall_shown = state
        if state in DEFAULT_STALL_EMOJI:
            await self._render(
                emoji=DEFAULT_STALL_EMOJI[state],
                label=DEFAULT_STALL_LABEL[state],
            )
        # state == OK: cleared implicitly by the next phase render.
