"""
Telegram typing indicator renewal utility.

Provides a background task to periodically renew typing indicators
during long-running operations like agent.chat() calls.
"""

import asyncio
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class TypingIndicator:
    """Manages typing indicator renewal during long operations."""
    
    def __init__(self, interval: float = 4.0):
        """
        Initialize typing indicator manager.
        
        Args:
            interval: Seconds between typing renewals (default 4.0 for Telegram)
        """
        self.interval = interval
        self._task: Optional[asyncio.Task] = None
        self._cancelled = False
    
    async def start(self, typing_func: Callable[[], Any]) -> None:
        """
        Start typing indicator renewal task.
        
        Args:
            typing_func: Async function that sends typing action
        """
        if self._task and not self._task.done():
            # Already running
            return
        
        self._cancelled = False
        self._task = asyncio.create_task(self._typing_loop(typing_func))
    
    def cancel(self) -> None:
        """Cancel the typing indicator renewal."""
        self._cancelled = True
        if self._task and not self._task.done():
            self._task.cancel()
    
    async def _typing_loop(self, typing_func: Callable[[], Any]) -> None:
        """Background loop that periodically sends typing action."""
        try:
            while not self._cancelled:
                try:
                    # Send typing indicator
                    if asyncio.iscoroutinefunction(typing_func):
                        await typing_func()
                    else:
                        typing_func()
                    
                    # Wait for interval or until cancelled
                    await asyncio.sleep(self.interval)
                    
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.debug(f"Typing indicator send failed: {e}")
                    # Continue trying even if one fails
                    await asyncio.sleep(self.interval)
        except asyncio.CancelledError:
            pass
        finally:
            logger.debug("Typing indicator loop ended")


async def with_typing_renewal(
    typing_func: Callable[[], Any],
    operation_coro,
    interval: float = 4.0
):
    """
    Execute an operation with typing indicator renewal.
    
    Args:
        typing_func: Function to call for typing indication
        operation_coro: Coroutine to execute while showing typing
        interval: Seconds between typing renewals
    
    Returns:
        Result of the operation
    """
    indicator = TypingIndicator(interval=interval)
    
    try:
        # Start typing renewal
        await indicator.start(typing_func)
        
        # Execute the operation
        result = await operation_coro
        
        return result
        
    finally:
        # Always cancel typing renewal
        indicator.cancel()