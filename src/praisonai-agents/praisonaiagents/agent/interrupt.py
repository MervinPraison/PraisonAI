"""
Interrupt Controller - Cooperative cancellation for agent runs.

Provides thread-safe, cooperative cancellation mechanism for long-running agent
operations. Follows protocol-driven design with zero overhead when not used.
"""

import threading
from typing import Optional, Protocol
from dataclasses import dataclass, field

__all__ = ["InterruptControllerProtocol", "InterruptController"]


class InterruptControllerProtocol(Protocol):
    """Protocol for interrupt controller extension point."""
    
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

    def clear(self) -> None:
        """Clear the cancellation request."""
        with self._lock:
            self._reason = None
            self._flag.clear()

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

    def check(self) -> None:
        """Check for cancellation and raise if requested.
        
        Raises:
            InterruptedError: If cancellation was requested
        """
        if self.is_set():
            reason = self.reason or "unknown"
            raise InterruptedError(f"Operation cancelled: {reason}")
