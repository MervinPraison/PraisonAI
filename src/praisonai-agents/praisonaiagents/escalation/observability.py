"""
Observability Hooks for Escalation Pipeline.

Provides lightweight tracing and metrics collection for escalation execution.
Opt-in only - no overhead when not enabled.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

from .types import EscalationStage

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Types of observable events."""
    # Stage events
    STAGE_ENTER = "stage_enter"
    STAGE_EXIT = "stage_exit"
    STAGE_ESCALATE = "stage_escalate"
    STAGE_DEESCALATE = "stage_deescalate"
    
    # Execution events
    EXECUTION_START = "execution_start"
    EXECUTION_END = "execution_end"
    STEP_START = "step_start"
    STEP_END = "step_end"
    
    # Tool events
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_END = "tool_call_end"
    TOOL_CALL_ERROR = "tool_call_error"
    
    # Checkpoint events
    CHECKPOINT_CREATE = "checkpoint_create"
    CHECKPOINT_RESTORE = "checkpoint_restore"
    
    # Loop detection events
    DOOM_LOOP_DETECTED = "doom_loop_detected"
    RECOVERY_ATTEMPT = "recovery_attempt"
    
    # Budget events
    BUDGET_WARNING = "budget_warning"
    BUDGET_EXCEEDED = "budget_exceeded"


@dataclass
class ObservabilityEvent:
    """An observable event from the escalation pipeline."""
    event_type: EventType
    timestamp: float
    data: Dict[str, Any] = field(default_factory=dict)
    
    # Context
    session_id: Optional[str] = None
    stage: Optional[EscalationStage] = None
    step_number: int = 0
    
    # Timing
    duration_ms: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "data": self.data,
            "session_id": self.session_id,
            "stage": self.stage.name if self.stage else None,
            "step_number": self.step_number,
            "duration_ms": self.duration_ms,
        }


@dataclass
class ExecutionMetrics:
    """Metrics collected during execution."""
    # Timing
    total_duration_ms: float = 0.0
    stage_durations_ms: Dict[str, float] = field(default_factory=dict)
    
    # Counts
    total_steps: int = 0
    tool_calls: int = 0
    tool_errors: int = 0
    escalations: int = 0
    deescalations: int = 0
    
    # Tokens
    tokens_used: int = 0
    
    # Checkpoints
    checkpoints_created: int = 0
    
    # Loop detection
    doom_loops_detected: int = 0
    recovery_attempts: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_duration_ms": self.total_duration_ms,
            "stage_durations_ms": self.stage_durations_ms,
            "total_steps": self.total_steps,
            "tool_calls": self.tool_calls,
            "tool_errors": self.tool_errors,
            "escalations": self.escalations,
            "deescalations": self.deescalations,
            "tokens_used": self.tokens_used,
            "checkpoints_created": self.checkpoints_created,
            "doom_loops_detected": self.doom_loops_detected,
            "recovery_attempts": self.recovery_attempts,
        }


class ObservabilityHooks:
    """
    Observability hooks for escalation pipeline.
    
    Provides:
    - Event emission
    - Metrics collection
    - Custom handler registration
    - Tracing support
    
    Example:
        hooks = ObservabilityHooks()
        
        # Register handler
        hooks.on(EventType.STAGE_ESCALATE, lambda e: print(f"Escalated to {e.stage}"))
        
        # Use with pipeline
        pipeline = EscalationPipeline(observability=hooks)
    """
    
    def __init__(self, enabled: bool = True):
        """
        Initialize observability hooks.
        
        Args:
            enabled: Whether observability is enabled
        """
        self.enabled = enabled
        self._handlers: Dict[EventType, List[Callable[[ObservabilityEvent], None]]] = {
            event_type: [] for event_type in EventType
        }
        self._events: List[ObservabilityEvent] = []
        self._metrics = ExecutionMetrics()
        self._session_id: Optional[str] = None
        self._current_stage: Optional[EscalationStage] = None
        self._step_number: int = 0
        self._stage_start_times: Dict[str, float] = {}
    
    def on(self, event_type: EventType, handler: Callable[[ObservabilityEvent], None]):
        """
        Register an event handler.
        
        Args:
            event_type: Type of event to handle
            handler: Handler function
        """
        self._handlers[event_type].append(handler)
    
    def off(self, event_type: EventType, handler: Callable[[ObservabilityEvent], None]):
        """
        Unregister an event handler.
        
        Args:
            event_type: Type of event
            handler: Handler to remove
        """
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)
    
    def emit(self, event_type: EventType, data: Optional[Dict[str, Any]] = None, duration_ms: Optional[float] = None):
        """
        Emit an event.
        
        Args:
            event_type: Type of event
            data: Event data
            duration_ms: Optional duration
        """
        if not self.enabled:
            return
        
        event = ObservabilityEvent(
            event_type=event_type,
            timestamp=time.time(),
            data=data or {},
            session_id=self._session_id,
            stage=self._current_stage,
            step_number=self._step_number,
            duration_ms=duration_ms,
        )
        
        self._events.append(event)
        self._update_metrics(event)
        
        # Call handlers
        for handler in self._handlers[event_type]:
            try:
                handler(event)
            except Exception as e:
                logger.warning(f"Event handler error: {e}")
    
    def _update_metrics(self, event: ObservabilityEvent):
        """Update metrics based on event."""
        if event.event_type == EventType.STEP_END:
            self._metrics.total_steps += 1
        elif event.event_type == EventType.TOOL_CALL_END:
            self._metrics.tool_calls += 1
        elif event.event_type == EventType.TOOL_CALL_ERROR:
            self._metrics.tool_errors += 1
        elif event.event_type == EventType.STAGE_ESCALATE:
            self._metrics.escalations += 1
        elif event.event_type == EventType.STAGE_DEESCALATE:
            self._metrics.deescalations += 1
        elif event.event_type == EventType.CHECKPOINT_CREATE:
            self._metrics.checkpoints_created += 1
        elif event.event_type == EventType.DOOM_LOOP_DETECTED:
            self._metrics.doom_loops_detected += 1
        elif event.event_type == EventType.RECOVERY_ATTEMPT:
            self._metrics.recovery_attempts += 1
    
    def set_session(self, session_id: str):
        """Set current session ID."""
        self._session_id = session_id
    
    def set_stage(self, stage: EscalationStage):
        """Set current stage."""
        old_stage = self._current_stage
        self._current_stage = stage
        
        # Track stage timing
        now = time.time()
        if old_stage:
            stage_key = old_stage.name
            if stage_key in self._stage_start_times:
                duration = (now - self._stage_start_times[stage_key]) * 1000
                self._metrics.stage_durations_ms[stage_key] = (
                    self._metrics.stage_durations_ms.get(stage_key, 0) + duration
                )
        
        self._stage_start_times[stage.name] = now
    
    def increment_step(self):
        """Increment step counter."""
        self._step_number += 1
    
    def add_tokens(self, count: int):
        """Add to token count."""
        self._metrics.tokens_used += count
    
    def get_events(self) -> List[ObservabilityEvent]:
        """Get all recorded events."""
        return self._events.copy()
    
    def get_metrics(self) -> ExecutionMetrics:
        """Get collected metrics."""
        return self._metrics
    
    def reset(self):
        """Reset all state."""
        self._events.clear()
        self._metrics = ExecutionMetrics()
        self._session_id = None
        self._current_stage = None
        self._step_number = 0
        self._stage_start_times.clear()
    
    def start_execution(self, session_id: Optional[str] = None):
        """Mark execution start."""
        self.reset()
        if session_id:
            self._session_id = session_id
        self.emit(EventType.EXECUTION_START)
    
    def end_execution(self, duration_ms: float):
        """Mark execution end."""
        self._metrics.total_duration_ms = duration_ms
        self.emit(EventType.EXECUTION_END, {"duration_ms": duration_ms}, duration_ms)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get execution summary."""
        return {
            "session_id": self._session_id,
            "metrics": self._metrics.to_dict(),
            "event_count": len(self._events),
            "final_stage": self._current_stage.name if self._current_stage else None,
        }


# Global hooks instance (opt-in)
_global_hooks: Optional[ObservabilityHooks] = None


def get_hooks() -> Optional[ObservabilityHooks]:
    """Get global observability hooks."""
    return _global_hooks


def enable_observability() -> ObservabilityHooks:
    """Enable global observability."""
    global _global_hooks
    if _global_hooks is None:
        _global_hooks = ObservabilityHooks(enabled=True)
    return _global_hooks


def disable_observability():
    """Disable global observability."""
    global _global_hooks
    _global_hooks = None
