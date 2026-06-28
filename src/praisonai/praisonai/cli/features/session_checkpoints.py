"""
Session-lifecycle checkpointing for the coding agent loop.

Wires the existing core checkpoint engine
(:class:`praisonaiagents.checkpoints.CheckpointService`, surfaced via
:class:`praisonai.cli.features.checkpoints.CheckpointsHandler`) into the
interactive coding session so that:

* a checkpoint is taken at session start and before each file-mutating turn, and
* an in-session ``/undo`` / ``/revert <n>`` (and a ``--revert`` CLI flag) can
  roll the workspace back to a prior turn, previewing the diff first.

This is an *integration* layer only — it reuses the engine as-is and adds the
missing session/turn bookkeeping. It is default-safe: when disabled it does no
work and adds zero overhead.
"""

import asyncio
import os
from dataclasses import dataclass, field
from typing import List, Optional


def _truthy(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class _Turn:
    """A single checkpointed turn in the session timeline."""

    turn: int
    checkpoint_id: str
    short_id: str
    message: str


@dataclass
class SessionCheckpointManager:
    """
    Turn-aware checkpoint bookkeeping around a coding session.

    Maps session turns to checkpoint ids created by the underlying
    :class:`CheckpointsHandler`, so "undo the last change the agent made" is a
    single action.

    Args:
        workspace_dir: Directory the agent edits.
        enabled: Whether auto-checkpointing is active.
        verbose: Verbose handler logging.
    """

    workspace_dir: str
    enabled: bool = False
    verbose: bool = False
    _handler: Optional[object] = field(default=None, repr=False)
    _turns: List[_Turn] = field(default_factory=list)
    _turn_counter: int = 0
    _initialized: bool = False

    @classmethod
    def from_config(
        cls,
        workspace_dir: Optional[str] = None,
        config: Optional[dict] = None,
        verbose: bool = False,
    ) -> "SessionCheckpointManager":
        """
        Build a manager from a resolved ``checkpoints`` config section.

        Precedence (highest last): config ``checkpoints.auto`` -> the
        ``PRAISONAI_CHECKPOINTS`` environment override. Defaults to disabled so
        there is zero overhead unless a user opts in.
        """
        workspace_dir = workspace_dir or os.getcwd()
        section = (config or {}).get("checkpoints", {}) if config else {}
        enabled = bool(section.get("auto", False)) if isinstance(section, dict) else False

        env_override = os.environ.get("PRAISONAI_CHECKPOINTS")
        if env_override is not None:
            enabled = _truthy(env_override)

        storage_dir = (
            section.get("storage_dir") if isinstance(section, dict) else None
        )

        manager = cls(workspace_dir=workspace_dir, enabled=enabled, verbose=verbose)
        manager._storage_dir = storage_dir  # type: ignore[attr-defined]
        return manager

    def _get_handler(self):
        if self._handler is None:
            from .checkpoints import CheckpointsHandler

            self._handler = CheckpointsHandler(
                workspace_dir=self.workspace_dir, verbose=self.verbose
            )
        return self._handler

    def _run(self, coro):
        """Run an async handler coroutine from the synchronous REPL loop."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        # Fallback for the rare case a loop is already running on this thread.
        return asyncio.new_event_loop().run_until_complete(coro)

    @property
    def turns(self) -> List[_Turn]:
        return list(self._turns)

    def checkpoint_turn(self, message: str) -> Optional[str]:
        """
        Save a checkpoint for the upcoming turn and record it on the timeline.

        Returns the checkpoint id, or ``None`` when disabled or nothing changed.
        Never raises into the REPL loop — checkpointing must not break a turn.
        """
        if not self.enabled:
            return None

        try:
            handler = self._get_handler()
            self._turn_counter += 1
            label = f"turn {self._turn_counter}: {message}".strip()

            async def _save():
                service = await handler._get_service()
                # allow_empty so every turn boundary is a distinct restore
                # point, even when the previous turn left no file changes.
                # This keeps "undo the last turn" reliable and turn-aligned.
                result = await service.save(label, allow_empty=True)
                return result

            result = self._run(_save())
            if result and getattr(result, "success", False):
                cp = result.checkpoint
                self._turns.append(
                    _Turn(
                        turn=self._turn_counter,
                        checkpoint_id=cp.id,
                        short_id=cp.short_id,
                        message=label,
                    )
                )
                self._initialized = True
                return cp.id
        except Exception:
            # Auto-checkpoint is best-effort; never break the turn.
            pass
        return None

    def revert(self, n: int = 1) -> Optional[_Turn]:
        """
        Restore the workspace to ``n`` turns back (1 == last checkpointed turn).

        Returns the restored turn, or ``None`` when there is nothing to revert
        to. Caller is responsible for any diff preview/confirmation.
        """
        if not self.enabled or not self._turns:
            return None
        if n < 1:
            n = 1
        if n > len(self._turns):
            return None

        target = self._turns[-n]
        try:
            handler = self._get_handler()
            ok = self._run(handler.restore(target.checkpoint_id))
            if ok:
                # The workspace now matches `target`'s checkpoint, so keep the
                # timeline up to and including `target` and drop the reverted
                # turns above it. target == self._turns[-n] -> keep up to that
                # index (inclusive).
                self._turns = self._turns[: len(self._turns) - n + 1]
                return target
        except Exception:
            pass
        return None

    def preview(self, n: int = 1) -> None:
        """Print the diff that ``revert(n)`` would undo (best-effort)."""
        if not self.enabled or not self._turns:
            return
        if n < 1:
            n = 1
        if n > len(self._turns):
            return
        target = self._turns[-n]
        try:
            handler = self._get_handler()
            self._run(handler.diff(target.checkpoint_id, None))
        except Exception:
            pass
