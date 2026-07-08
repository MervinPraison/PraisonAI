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
    # Number of conversation messages captured at turn start. Used to rewind
    # the conversation store to the same boundary as the file checkpoint so
    # files and history stay coherent after an undo. ``None`` when no
    # conversation store is wired in (legacy / file-only sessions).
    message_count: Optional[int] = None


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
    storage_dir: Optional[str] = None
    # Optional conversation store + session id. When both are set, a revert
    # rewinds the conversation history to the same turn boundary as the file
    # checkpoint, keeping files and chat_history coherent. Left unset for
    # file-only / legacy sessions, which keeps existing behaviour unchanged.
    session_store: Optional[object] = None
    session_id: Optional[str] = None
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
        session_store: Optional[object] = None,
        session_id: Optional[str] = None,
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

        return cls(
            workspace_dir=workspace_dir,
            enabled=enabled,
            verbose=verbose,
            storage_dir=storage_dir,
            session_store=session_store,
            session_id=session_id,
        )

    def _get_handler(self):
        if self._handler is None:
            from .checkpoints import CheckpointsHandler

            self._handler = CheckpointsHandler(
                workspace_dir=self.workspace_dir,
                verbose=self.verbose,
                storage_dir=self.storage_dir,
            )
        return self._handler

    def _run(self, coro):
        """Run an async handler coroutine from the synchronous REPL loop."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        # A loop is already running on this thread (async-hosted caller):
        # run the coroutine on a dedicated worker thread so we never try to
        # drive a second loop on a thread that already has one.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(asyncio.run, coro).result()

    @property
    def turns(self) -> List[_Turn]:
        return list(self._turns)

    def _conversation_message_count(self) -> Optional[int]:
        """
        Best-effort count of messages currently in the conversation store.

        Returns ``None`` when no conversation store is wired in or the count
        cannot be determined, so callers can skip conversation bookkeeping and
        preserve the previous file-only behaviour.
        """
        store = self.session_store
        if store is None or not self.session_id:
            return None
        try:
            getter = getattr(store, "get_messages", None)
            if callable(getter):
                messages = getter(self.session_id)
                if messages is not None:
                    return len(messages)
            session = getattr(store, "get_extended_session", None)
            if callable(session):
                data = session(self.session_id)
                msgs = getattr(data, "messages", None)
                if msgs is not None:
                    return len(msgs)
        except Exception:
            pass
        return None

    def _rewind_conversation(self, message_count: Optional[int]) -> None:
        """
        Rewind the conversation store to ``message_count`` messages.

        Uses the core ``revert_to_message`` primitive so that undoing a turn
        drops the assistant/tool messages produced by the reverted turn(s),
        keeping ``chat_history`` consistent with the restored files. Best-effort
        and non-raising: a conversation-revert failure must not corrupt the
        already-restored workspace.
        """
        store = self.session_store
        if store is None or not self.session_id or message_count is None:
            return
        try:
            if message_count <= 0:
                # Nothing to keep: clear history where the store supports it.
                revert = getattr(store, "revert_to_message", None)
                if callable(revert):
                    revert(self.session_id, 0)
                return
            revert = getattr(store, "revert_to_message", None)
            if callable(revert):
                # revert_to_message keeps messages[:index + 1]; to keep
                # ``message_count`` messages we target the last kept index.
                revert(self.session_id, message_count - 1)
        except Exception:
            pass

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

            # Capture the conversation boundary *before* the turn runs so a
            # later revert rewinds history to exactly this point.
            message_count = self._conversation_message_count()

            result = self._run(_save())
            if result and getattr(result, "success", False):
                cp = result.checkpoint
                self._turns.append(
                    _Turn(
                        turn=self._turn_counter,
                        checkpoint_id=cp.id,
                        short_id=cp.short_id,
                        message=label,
                        message_count=message_count,
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
                # Files are restored; now rewind the conversation history to the
                # same turn boundary so the agent's chat_history no longer
                # references the edits that were just undone. Best-effort: a
                # conversation-revert failure leaves the restored files intact.
                self._rewind_conversation(target.message_count)
                # The workspace now matches `target`'s checkpoint. Drop the
                # restored turn *and* every turn above it from the timeline so
                # the next /undo walks further back instead of restoring the
                # same checkpoint again. With [start, t1, t2], revert(1)
                # restores t2 and leaves [start, t1], so the next /undo -> t1.
                self._turns = self._turns[: len(self._turns) - n]
                return target
        except Exception:
            pass
        return None

    def dropped_message_count(self, n: int = 1) -> Optional[int]:
        """
        How many conversation messages ``revert(n)`` would drop.

        Returns ``None`` when no conversation store is wired in or the boundary
        was not captured, so callers can present a file-only preview unchanged.
        """
        if not self.enabled or not self._turns:
            return None
        if n < 1:
            n = 1
        if n > len(self._turns):
            return None
        target = self._turns[-n]
        if target.message_count is None:
            return None
        current = self._conversation_message_count()
        if current is None:
            return None
        return max(0, current - target.message_count)

    def preview(self, n: int = 1) -> None:
        """Print the diff and conversation rollback that ``revert(n)`` would undo."""
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
        try:
            dropped = self.dropped_message_count(n)
            if dropped:
                print(
                    f"This will also drop {dropped} conversation "
                    f"message(s) to keep history in sync with the files."
                )
        except Exception:
            pass
