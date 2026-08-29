"""
Interrupt Controller - Cooperative cancellation for agent runs.

Provides thread-safe, cooperative cancellation mechanism for long-running agent
operations. Follows protocol-driven design with zero overhead when not used.
"""

import threading
from typing import Optional, Protocol, Set, runtime_checkable
from dataclasses import dataclass, field

__all__ = [
    "InterruptControllerProtocol",
    "CancellableInterruptControllerProtocol",
    "InterruptController",
]


class InterruptControllerProtocol(Protocol):
    """Protocol for interrupt controller extension point.

    ``event`` is intentionally NOT part of this base contract: exposing the
    underlying cancellation Event is an OPTIONAL capability. Existing third-party
    controllers that only implement request/clear/is_set/reason/check remain
    valid; the runtime probes for ``event`` via ``getattr(..., 'event', None)``.
    Controllers that want in-tool cooperative abort can implement
    :class:`CancellableInterruptControllerProtocol`.
    """
    
    def request(self, reason: str = "user") -> None:
        """Request cancellation with optional reason."""
        ...
    
    def clear(self) -> None:
        """Clear interrupt state."""
        ...
    
    def is_set(self) -> bool:
        """Check if interrupt was requested."""
        ...
    
    @property
    def reason(self) -> Optional[str]:
        """Get interrupt reason if set."""
        ...

    def check(self) -> None:
        """Check for interrupt and raise if set."""
        ...


@runtime_checkable
class CancellableInterruptControllerProtocol(InterruptControllerProtocol, Protocol):
    """Optional extension: controllers that expose the cancellation Event.

    A running tool body can wait on / poll this Event to abort promptly instead
    of running until its own timeout. Implementing it is entirely optional and
    fully backward compatible with :class:`InterruptControllerProtocol`.
    """

    @property
    def event(self) -> "threading.Event":
        """Get the underlying cancellation Event for in-tool observation."""
        ...


@dataclass
class InterruptController:
    """Thread-safe cooperative cancellation for agent runs.
    
    Provides a lightweight mechanism for requesting cancellation of agent
    operations. Uses threading.Event for thread safety and cooperative
    checking patterns.
    
    Examples:
        Basic usage:
        >>> controller = InterruptController()
        >>> # In another thread:
        >>> controller.request("user_cancel")
        >>> # In agent loop:
        >>> if controller.is_set():
        >>>     return f"Cancelled: {controller.reason}"
    """
    
    _flag: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _reason: Optional[str] = field(default=None, init=False)
    _active_turns: Set[int] = field(default_factory=set, init=False, repr=False)
    _cancelled_turns: Set[int] = field(default_factory=set, init=False, repr=False)
    _next_turn_id: int = field(default=0, init=False, repr=False)
    _pending_turn_cancel: bool = field(default=False, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def request(self, reason: str = "user") -> None:
        """Request cancellation with a reason.
        
        Args:
            reason: Human-readable reason for cancellation
        """
        with self._lock:
            if not self._flag.is_set():
                self._reason = reason
                self._flag.set()
            if self._active_turns:
                self._cancelled_turns.update(self._active_turns)
            else:
                self._pending_turn_cancel = True

    def _begin_turn(self) -> int:
        """Register an Agent turn and consume any request made while idle."""
        with self._lock:
            self._next_turn_id += 1
            turn_id = self._next_turn_id
            self._active_turns.add(turn_id)
            if self._pending_turn_cancel:
                self._cancelled_turns.add(turn_id)
                self._pending_turn_cancel = False
            return turn_id

    def _turn_is_cancelled(self, turn_id: int) -> bool:
        """Return whether a registered turn was targeted by a request."""
        with self._lock:
            return turn_id in self._cancelled_turns

    def _end_turn(self, turn_id: int) -> None:
        """Unregister a turn so its request cannot affect a future turn.

        Also clears the underlying Event once no turn still needs it (no active
        or still-cancelled turns and no pending request). The Event is exposed to
        running tool bodies via :attr:`event`; leaving it set after an interrupted
        turn would make a reused controller abort tools launched by the NEXT turn.
        """
        with self._lock:
            self._active_turns.discard(turn_id)
            self._cancelled_turns.discard(turn_id)
            if not self._active_turns and not self._cancelled_turns and not self._pending_turn_cancel:
                self._flag.clear()
                self._reason = None

    def clear(self) -> None:
        """Clear the cancellation request."""
        with self._lock:
            self._reason = None
            self._flag.clear()
            self._pending_turn_cancel = False
            self._cancelled_turns.clear()

    def is_set(self) -> bool:
        """Check if cancellation has been requested.
        
        Returns:
            True if cancellation was requested
        """
        return self._flag.is_set()

    @property
    def reason(self) -> Optional[str]:
        """Get the reason for cancellation.
        
        Returns:
            Reason string if cancelled, None otherwise
        """
        with self._lock:
            return self._reason

    @property
    def event(self) -> threading.Event:
        """Expose the underlying cancellation Event.

        Lets a running tool body observe the interrupt cooperatively (e.g. wait
        on it with a timeout, or poll ``is_set()``) so an in-flight subprocess/
        request can be aborted rather than left running until its own timeout.
        """
        return self._flag

    def check(self) -> None:
        """Check for cancellation and raise if requested.
        
        Raises:
            InterruptedError: If cancellation was requested
        """
        if self.is_set():
            reason = self.reason or "unknown"
            raise InterruptedError(f"Operation cancelled: {reason}")
