"""
Doom Loop Detection for PraisonAI Agents.

Detects and prevents infinite loops, repeated failures, and stuck states.
Provides recovery strategies when loops are detected.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum
import time
import hashlib
import logging

logger = logging.getLogger(__name__)


class DoomLoopType(Enum):
    """Types of doom loops that can be detected."""
    REPEATED_ACTION = "repeated_action"      # Same action repeated
    REPEATED_FAILURE = "repeated_failure"    # Same failure repeated
    NO_PROGRESS = "no_progress"              # No meaningful progress
    CIRCULAR_PLAN = "circular_plan"          # Plan loops back to start
    RESOURCE_EXHAUSTION = "resource_exhaustion"  # Budget exceeded
    REPEATED_OUTPUT = "repeated_output"      # Same output text repeated (content chanting)


class RecoveryAction(Enum):
    """Actions to take when doom loop is detected."""
    CONTINUE = "continue"           # Continue execution
    RETRY_DIFFERENT = "retry_different"  # Retry with different approach
    ESCALATE_MODEL = "escalate_model"    # Try stronger model
    REQUEST_HELP = "request_help"        # Ask user for clarification
    ABORT = "abort"                      # Stop execution safely


@dataclass
class DoomLoopConfig:
    """Configuration for doom loop detection."""
    # Thresholds
    max_identical_actions: int = 3       # Max identical consecutive actions
    max_similar_actions: int = 5         # Max similar actions (fuzzy match)
    max_consecutive_failures: int = 3    # Max failures before intervention
    max_no_progress_steps: int = 5       # Max steps without progress
    
    # Similarity threshold for fuzzy matching (0-1)
    similarity_threshold: float = 0.85
    
    # Time limits
    max_time_per_action: float = 60.0    # Max seconds per action
    max_total_time: float = 300.0        # Max total execution time
    
    # Recovery settings
    enable_auto_recovery: bool = True    # Auto-attempt recovery
    max_recovery_attempts: int = 2       # Max recovery attempts
    escalate_on_loop: bool = True        # Escalate model on loop detection
    
    # Backoff settings
    initial_backoff: float = 1.0         # Initial backoff in seconds
    backoff_multiplier: float = 2.0      # Backoff multiplier
    max_backoff: float = 30.0            # Maximum backoff
    
    # Content streaming detection
    max_repeated_chunks: int = 8         # Max identical output chunks before flagging
    content_chunk_size: int = 50         # Sliding window chunk size (chars)


@dataclass
class DoomLoopEvent:
    """Event representing a doom loop detection."""
    loop_type: DoomLoopType
    description: str
    action_history: List[str]
    recovery_action: RecoveryAction
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionRecord:
    """Record of an action for loop detection."""
    action_type: str
    action_hash: str
    args_hash: str
    result_hash: Optional[str]
    success: bool
    timestamp: float
    duration: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class DoomLoopDetector:
    """
    Detects and prevents doom loops in agent execution.
    
    Monitors action history for patterns that indicate stuck states:
    - Repeated identical actions
    - Repeated similar actions
    - Consecutive failures
    - No meaningful progress
    
    Example:
        detector = DoomLoopDetector()
        
        # Record actions
        detector.record_action("read_file", {"path": "foo.py"}, "content", True)
        detector.record_action("read_file", {"path": "foo.py"}, "content", True)
        
        # Check for loops
        if detector.is_doom_loop():
            event = detector.get_loop_event()
            recovery = detector.get_recovery_action()
    """
    
    def __init__(self, config: Optional[DoomLoopConfig] = None):
        """Initialize detector with optional config."""
        self.config = config or DoomLoopConfig()
        self._actions: List[ActionRecord] = []
        self._loop_events: List[DoomLoopEvent] = []
        self._recovery_attempts: int = 0
        self._start_time: Optional[float] = None
        self._progress_markers: List[str] = []
        self._current_backoff: float = self.config.initial_backoff
        self._content_chunk_counts: Dict[str, int] = {}  # hash -> count
    
    def start_session(self):
        """Start a new detection session."""
        self._start_time = time.time()
        self._actions.clear()
        self._loop_events.clear()
        self._recovery_attempts = 0
        self._progress_markers.clear()
        self._current_backoff = self.config.initial_backoff
        self._content_chunk_counts.clear()
    
    def record_action(
        self,
        action_type: str,
        args: Dict[str, Any],
        result: Any,
        success: bool,
        duration: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Record an action for loop detection.
        
        Args:
            action_type: Type of action (e.g., "read_file", "edit")
            args: Action arguments
            result: Action result
            success: Whether action succeeded
            duration: Action duration in seconds
            metadata: Optional metadata
        """
        record = ActionRecord(
            action_type=action_type,
            action_hash=self._hash_action(action_type, args),
            args_hash=self._hash_dict(args),
            result_hash=self._hash_result(result) if result else None,
            success=success,
            timestamp=time.time(),
            duration=duration,
            metadata=metadata or {}
        )
        self._actions.append(record)
        
        # Check for loops after recording
        if self.is_doom_loop():
            self._handle_loop_detection()
    
    def record_response(self, text: str):
        """
        Record model response text for content streaming loop detection.
        
        Hashes sliding window chunks and tracks repetition counts.
        Inspired by gemini-cli's sliding window approach.
        
        Args:
            text: The model's response text
        """
        if not text or len(text) < self.config.content_chunk_size:
            return
        
        chunk_size = self.config.content_chunk_size
        for i in range(0, len(text) - chunk_size + 1, chunk_size):
            chunk = text[i:i + chunk_size]
            chunk_hash = hashlib.md5(chunk.encode()).hexdigest()[:16]
            self._content_chunk_counts[chunk_hash] = self._content_chunk_counts.get(chunk_hash, 0) + 1
    
    def mark_progress(self, marker: str):
        """
        Mark meaningful progress.
        
        Call this when the agent makes real progress (e.g., file modified,
        test passed, user goal partially achieved).
        """
        self._progress_markers.append(marker)
    
    def is_doom_loop(self) -> bool:
        """
        Check if current state indicates a doom loop.
        
        Returns:
            True if doom loop detected
        """
        # Content streaming loop can occur even without recorded actions
        if self._check_content_loop():
            return True
        
        if len(self._actions) < 2:
            return False
        
        # Check for repeated identical actions
        if self._check_repeated_identical():
            return True
        
        # Check for repeated similar actions
        if self._check_repeated_similar():
            return True
        
        # Check for consecutive failures
        if self._check_consecutive_failures():
            return True
        
        # Check for no progress
        if self._check_no_progress():
            return True
        
        # Check for resource exhaustion
        if self._check_resource_exhaustion():
            return True
        
        # Check for content streaming loops (repeated output text)
        if self._check_content_loop():
            return True
        
        return False
    
    def get_loop_type(self) -> Optional[DoomLoopType]:
        """Get the type of doom loop detected."""
        if self._check_repeated_identical():
            return DoomLoopType.REPEATED_ACTION
        if self._check_repeated_similar():
            return DoomLoopType.REPEATED_ACTION
        if self._check_consecutive_failures():
            return DoomLoopType.REPEATED_FAILURE
        if self._check_no_progress():
            return DoomLoopType.NO_PROGRESS
        if self._check_resource_exhaustion():
            return DoomLoopType.RESOURCE_EXHAUSTION
        if self._check_content_loop():
            return DoomLoopType.REPEATED_OUTPUT
        return None
    
    def get_loop_event(self) -> Optional[DoomLoopEvent]:
        """Get the current loop event if one exists."""
        loop_type = self.get_loop_type()
        if not loop_type:
            return None
        
        return DoomLoopEvent(
            loop_type=loop_type,
            description=self._get_loop_description(loop_type),
            action_history=[a.action_type for a in self._actions[-10:]],
            recovery_action=self._determine_recovery_action(loop_type),
            metadata={
                "action_count": len(self._actions),
                "recovery_attempts": self._recovery_attempts,
            }
        )
    
    def get_recovery_action(self) -> RecoveryAction:
        """
        Get recommended recovery action.
        
        Returns:
            Recommended recovery action
        """
        loop_type = self.get_loop_type()
        if not loop_type:
            return RecoveryAction.CONTINUE
        
        return self._determine_recovery_action(loop_type)
    
    def apply_backoff(self) -> float:
        """
        Apply backoff delay and return the delay used.
        
        Returns:
            Backoff delay in seconds
        """
        delay = min(self._current_backoff, self.config.max_backoff)
        self._current_backoff *= self.config.backoff_multiplier
        time.sleep(delay)
        return delay
    
    def reset_backoff(self):
        """Reset backoff to initial value."""
        self._current_backoff = self.config.initial_backoff
    
    def increment_recovery(self) -> bool:
        """
        Increment recovery attempt counter.
        
        Returns:
            True if more recovery attempts allowed
        """
        self._recovery_attempts += 1
        return self._recovery_attempts < self.config.max_recovery_attempts
    
    def get_stats(self) -> Dict[str, Any]:
        """Get detection statistics."""
        elapsed = time.time() - self._start_time if self._start_time else 0
        
        return {
            "total_actions": len(self._actions),
            "successful_actions": sum(1 for a in self._actions if a.success),
            "failed_actions": sum(1 for a in self._actions if not a.success),
            "loop_events": len(self._loop_events),
            "recovery_attempts": self._recovery_attempts,
            "progress_markers": len(self._progress_markers),
            "elapsed_time": elapsed,
            "current_backoff": self._current_backoff,
        }
    
    # =========================================================================
    # Private Methods
    # =========================================================================
    
    def _hash_action(self, action_type: str, args: Dict[str, Any]) -> str:
        """Create hash for action + args."""
        content = f"{action_type}:{self._hash_dict(args)}"
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    def _hash_dict(self, d: Dict[str, Any]) -> str:
        """Create hash for dictionary."""
        # Sort keys for consistent hashing
        content = str(sorted(d.items()))
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    def _hash_result(self, result: Any) -> str:
        """Create hash for result."""
        content = str(result)[:1000]  # Limit size
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    def _check_repeated_identical(self) -> bool:
        """Check for repeated identical actions."""
        if len(self._actions) < self.config.max_identical_actions:
            return False
        
        recent = self._actions[-self.config.max_identical_actions:]
        first_hash = recent[0].action_hash
        
        return all(a.action_hash == first_hash for a in recent)
    
    def _check_repeated_similar(self) -> bool:
        """Check for repeated similar actions."""
        if len(self._actions) < self.config.max_similar_actions:
            return False
        
        recent = self._actions[-self.config.max_similar_actions:]
        action_types = [a.action_type for a in recent]
        
        # Check if same action type repeated
        if len(set(action_types)) == 1:
            return True
        
        return False
    
    def _check_consecutive_failures(self) -> bool:
        """Check for consecutive failures."""
        if len(self._actions) < self.config.max_consecutive_failures:
            return False
        
        recent = self._actions[-self.config.max_consecutive_failures:]
        return all(not a.success for a in recent)
    
    def _check_no_progress(self) -> bool:
        """Check for no meaningful progress."""
        if len(self._actions) < self.config.max_no_progress_steps:
            return False
        
        # If we have progress markers, we're making progress
        recent_markers = [
            m for m in self._progress_markers
            if True  # Could add timestamp filtering
        ]
        if recent_markers:
            return False
        
        # Check if recent actions produced different results
        recent = self._actions[-self.config.max_no_progress_steps:]
        result_hashes = [a.result_hash for a in recent if a.result_hash]
        
        # If all results are the same, no progress
        if len(set(result_hashes)) <= 1:
            return True
        
        return False
    
    def _check_resource_exhaustion(self) -> bool:
        """Check for resource exhaustion."""
        if not self._start_time:
            return False
        
        elapsed = time.time() - self._start_time
        return elapsed > self.config.max_total_time
    
    def _check_content_loop(self) -> bool:
        """Check for repeated output text (content streaming loop).
        
        Uses sliding window chunk hashing. If any chunk hash appears
        more than max_repeated_chunks times, it indicates the model
        is generating repetitive output (chanting).
        """
        if not self._content_chunk_counts:
            return False
        
        threshold = self.config.max_repeated_chunks
        return any(count >= threshold for count in self._content_chunk_counts.values())
    
    def _determine_recovery_action(self, loop_type: DoomLoopType) -> RecoveryAction:
        """Determine appropriate recovery action."""
        # If max recovery attempts reached, abort
        if self._recovery_attempts >= self.config.max_recovery_attempts:
            return RecoveryAction.ABORT
        
        # Resource exhaustion always aborts
        if loop_type == DoomLoopType.RESOURCE_EXHAUSTION:
            return RecoveryAction.ABORT
        
        # First attempt: try different approach
        if self._recovery_attempts == 0:
            return RecoveryAction.RETRY_DIFFERENT
        
        # Second attempt: escalate model if configured
        if self._recovery_attempts == 1 and self.config.escalate_on_loop:
            return RecoveryAction.ESCALATE_MODEL
        
        # Otherwise request help
        return RecoveryAction.REQUEST_HELP
    
    def _get_loop_description(self, loop_type: DoomLoopType) -> str:
        """Get human-readable description of loop."""
        descriptions = {
            DoomLoopType.REPEATED_ACTION: (
                f"Same action repeated {self.config.max_identical_actions} times"
            ),
            DoomLoopType.REPEATED_FAILURE: (
                f"Action failed {self.config.max_consecutive_failures} times consecutively"
            ),
            DoomLoopType.NO_PROGRESS: (
                f"No meaningful progress in {self.config.max_no_progress_steps} steps"
            ),
            DoomLoopType.CIRCULAR_PLAN: "Plan has looped back to a previous state",
            DoomLoopType.RESOURCE_EXHAUSTION: (
                f"Exceeded time limit of {self.config.max_total_time}s"
            ),
            DoomLoopType.REPEATED_OUTPUT: (
                f"Model output repeating — {self.config.max_repeated_chunks}+ identical chunks detected"
            ),
        }
        return descriptions.get(loop_type, "Unknown loop type")
    
    def _handle_loop_detection(self):
        """Handle loop detection internally."""
        event = self.get_loop_event()
        if event:
            self._loop_events.append(event)
            logger.warning(f"Doom loop detected: {event.description}")
