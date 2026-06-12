"""
Per-session run control for PraisonAI bots.

Provides busy feedback, pending message slots, interrupt support, and
optional steering for in-flight agent runs. Solves the silent lock
problem where mid-run messages queue invisibly with no user feedback.

Usage inside a bot message handler::

    # Initialize with busy mode policy
    run_ctrl = SessionRunControl(busy_mode="queue")  # or "interrupt", "steer"
    
    # Handle message with run control
    decision = await run_ctrl.submit(user_id, message_text)
    
    if decision == RunDecision.RUN_NOW:
        # Start agent.chat() with interrupt controller
        response = await session_mgr.chat(agent, user_id, text)
    elif decision == RunDecision.QUEUED:
        # Return acknowledgment, message will be processed after current run
        return "⏳ Noted - will consider this after the current task finishes"
    elif decision == RunDecision.MERGED:
        # Message was merged into pending slot
        return "⏳ Added to pending message"

Key features:
- Busy acknowledgment for mid-run messages instead of silent queuing
- Per-user pending slot that merges follow-ups received mid-run
- /stop command via InterruptController integration
- Optional steering mode to inject messages into running turns
- Run generation tracking to prevent canceled runs overwriting fresh state
"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Dict, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from praisonaiagents.agent.interrupt import InterruptController

logger = logging.getLogger(__name__)


class RunDecision(Enum):
    """Decision for how to handle a submitted message."""
    RUN_NOW = "run_now"          # No current run, start immediately
    QUEUED = "queued"            # Current run active, message queued for next turn
    MERGED = "merged"            # Message merged into existing pending slot
    INTERRUPTED = "interrupted"  # Current run was interrupted, start new run


class BusyMode(Enum):
    """Policy for handling messages during active runs."""
    QUEUE = "queue"        # Queue message for next turn (default)
    INTERRUPT = "interrupt"  # Cancel current run and start new one
    STEER = "steer"       # Inject message into current run via steering


class SessionRunState:
    """Per-user run state tracking."""
    
    def __init__(self):
        self.is_running = False
        self.run_generation = 0  # Incremented on each run start
        self.pending_message: Optional[str] = None
        self.interrupt_controller: Optional["InterruptController"] = None
        self.start_time: Optional[float] = None


class SessionRunControl:
    """Per-session pending slot + interrupt handle around agent runs.
    
    Manages run states, pending messages, and interrupt controllers
    for each user session to provide better UX around long-running
    agent operations.
    """

    def __init__(
        self, 
        busy_mode: str = "queue",
        busy_ack_template: str = "⏳ {action} — will be considered next"
    ):
        """Initialize session run control.
        
        Args:
            busy_mode: Policy for mid-run messages ("queue", "interrupt", "steer")
            busy_ack_template: Template for busy acknowledgment messages
        """
        try:
            self._busy_mode = BusyMode(busy_mode)
        except ValueError:
            logger.warning(f"Invalid busy_mode '{busy_mode}', using 'queue'")
            self._busy_mode = BusyMode.QUEUE
            
        self._busy_ack_template = busy_ack_template
        self._sessions: Dict[str, SessionRunState] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    def _get_lock(self, user_id: str) -> asyncio.Lock:
        """Get or create lock for user."""
        if user_id not in self._locks:
            self._locks[user_id] = asyncio.Lock()
        return self._locks[user_id]

    def _get_session(self, user_id: str) -> SessionRunState:
        """Get or create session state for user."""
        if user_id not in self._sessions:
            self._sessions[user_id] = SessionRunState()
        return self._sessions[user_id]

    async def submit(self, user_id: str, text: str) -> RunDecision:
        """Submit a message and get decision on how to handle it.
        
        Args:
            user_id: User identifier
            text: Message text
            
        Returns:
            RunDecision indicating how to proceed
        """
        lock = self._get_lock(user_id)
        async with lock:
            session = self._get_session(user_id)
            
            if not session.is_running:
                # No active run, start immediately
                session.is_running = True
                session.run_generation += 1
                session.start_time = time.time()
                
                # Create interrupt controller for this run
                try:
                    from praisonaiagents.agent.interrupt import InterruptController
                    session.interrupt_controller = InterruptController()
                except ImportError:
                    logger.warning("InterruptController not available")
                    session.interrupt_controller = None
                    
                return RunDecision.RUN_NOW
            
            # There's an active run, handle based on busy mode
            if self._busy_mode == BusyMode.INTERRUPT:
                # Cancel current run and start new one
                if session.interrupt_controller:
                    session.interrupt_controller.request("user_new_message")
                
                session.pending_message = None  # Clear any pending
                session.run_generation += 1
                session.start_time = time.time()
                
                # Create new interrupt controller
                try:
                    from praisonaiagents.agent.interrupt import InterruptController
                    session.interrupt_controller = InterruptController()
                except ImportError:
                    session.interrupt_controller = None
                    
                return RunDecision.INTERRUPTED
                
            elif self._busy_mode == BusyMode.STEER:
                # Try to inject into running agent via steering
                # Note: This requires the agent to have steering enabled
                # For now, we'll fall back to queueing
                logger.debug(f"Steer mode not fully implemented, falling back to queue")
                # TODO: Implement steering integration when agent reference is available
                
            # Default to queue mode (or steer fallback)
            if session.pending_message is None:
                session.pending_message = text
                return RunDecision.QUEUED
            else:
                # Merge with existing pending message
                session.pending_message = f"{session.pending_message}\n{text}"
                return RunDecision.MERGED

    async def get_busy_ack_message(self, user_id: str, decision: RunDecision) -> str:
        """Get appropriate busy acknowledgment message.
        
        Args:
            user_id: User identifier
            decision: The decision returned by submit()
            
        Returns:
            Acknowledgment message to send to user
        """
        session = self._get_session(user_id)
        
        if decision == RunDecision.QUEUED:
            action = "noted"
        elif decision == RunDecision.MERGED:
            action = "added to pending request"
        elif decision == RunDecision.INTERRUPTED:
            return "⚠️ Previous task cancelled, starting your new request"
        else:
            return ""  # No ack needed for RUN_NOW
            
        # Add timing info if available
        timing = ""
        if session.start_time:
            elapsed = int(time.time() - session.start_time)
            if elapsed > 60:
                timing = f" (running for {elapsed//60}m {elapsed%60}s)"
            elif elapsed > 10:
                timing = f" (running for {elapsed}s)"
        
        return self._busy_ack_template.format(action=action) + timing

    async def stop(self, user_id: str) -> bool:
        """Stop the current run for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if a run was stopped, False if no active run
        """
        lock = self._get_lock(user_id)
        async with lock:
            session = self._get_session(user_id)
            
            if not session.is_running:
                return False
                
            # Request interrupt
            if session.interrupt_controller:
                session.interrupt_controller.request("user_stop_command")
                
            # Clear state
            session.is_running = False
            session.pending_message = None
            session.interrupt_controller = None
            session.start_time = None
            
            return True

    def next_pending(self, user_id: str) -> Optional[str]:
        """Get and clear the next pending message for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Pending message if any, None otherwise
        """
        session = self._get_session(user_id)
        pending = session.pending_message
        session.pending_message = None
        return pending

    async def finish_run(self, user_id: str, run_generation: Optional[int] = None):
        """Mark a run as finished.
        
        Args:
            user_id: User identifier
            run_generation: Generation of the run that finished (for race protection)
        """
        lock = self._get_lock(user_id)
        async with lock:
            session = self._get_session(user_id)
            
            # Race protection: only clear if this is the current generation
            if run_generation is None or run_generation == session.run_generation:
                session.is_running = False
                session.interrupt_controller = None
                session.start_time = None

    def get_interrupt_controller(self, user_id: str) -> Optional["InterruptController"]:
        """Get the interrupt controller for a user's current run.
        
        Args:
            user_id: User identifier
            
        Returns:
            InterruptController if run is active, None otherwise
        """
        session = self._get_session(user_id)
        if session.is_running:
            return session.interrupt_controller
        return None

    def get_run_status(self, user_id: str) -> Dict[str, Any]:
        """Get run status for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Dict with run status information
        """
        session = self._get_session(user_id)
        
        status = {
            "is_running": session.is_running,
            "run_generation": session.run_generation,
            "has_pending": session.pending_message is not None,
            "busy_mode": self._busy_mode.value
        }
        
        if session.start_time:
            status["elapsed_seconds"] = int(time.time() - session.start_time)
            
        if session.pending_message:
            status["pending_preview"] = session.pending_message[:100] + "..." if len(session.pending_message) > 100 else session.pending_message
            
        return status

    @property
    def active_sessions_count(self) -> int:
        """Number of sessions with active runs."""
        return sum(1 for session in self._sessions.values() if session.is_running)

    def cleanup_stale_sessions(self, max_age_seconds: int = 3600) -> int:
        """Clean up stale sessions older than max_age_seconds.
        
        Args:
            max_age_seconds: Maximum age in seconds
            
        Returns:
            Number of sessions cleaned up
        """
        if max_age_seconds <= 0:
            return 0
            
        now = time.time()
        stale_users = []
        
        for user_id, session in self._sessions.items():
            if session.start_time and (now - session.start_time) > max_age_seconds:
                stale_users.append(user_id)
                
        for user_id in stale_users:
            del self._sessions[user_id]
            self._locks.pop(user_id, None)
            
        if stale_users:
            logger.debug(f"SessionRunControl: cleaned up {len(stale_users)} stale sessions")
            
        return len(stale_users)