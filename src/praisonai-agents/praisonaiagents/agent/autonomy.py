"""
Agent Autonomy Module.

Provides agent-centric autonomy configuration and helpers.
This module integrates escalation, doom loop detection, and observability
directly into the Agent class as first-class capabilities.

Unified Architecture:
    - AutonomyStage is an alias for EscalationStage (single source of truth)
    - AutonomyTrigger delegates to EscalationTrigger (DRY)
    - DoomLoopTracker adds recovery actions on top of basic detection

Usage:
    from praisonaiagents import Agent
    
    # Enable autonomy with defaults
    agent = Agent(instructions="...", autonomy=True)
    
    # Enable with custom config
    agent = Agent(
        instructions="...",
        autonomy={
            "max_iterations": 30,
            "doom_loop_threshold": 5,
            "auto_escalate": True
        }
    )
    
    # Run autonomous task
    result = agent.run_autonomous("Refactor the auth module")
    print(result.success, result.output)
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Set
from enum import Enum
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# Unified Stage Enum (G-DUP-1 fix: single source of truth)
# ============================================================================
# AutonomyStage is an alias for EscalationStage so both systems share
# the same IntEnum. Backward-compatible: AutonomyStage.DIRECT == EscalationStage.DIRECT.
from ..escalation.types import EscalationStage as AutonomyStage  # noqa: F401

# Valid autonomy levels for AutonomyConfig.level
VALID_AUTONOMY_LEVELS = {"suggest", "auto_edit", "full_auto"}

# Signal name mapping: EscalationSignal.value → AutonomyTrigger string
# Keeps backward compat for existing code that checks string signal names.
_ESCALATION_TO_AUTONOMY_SIGNAL = {
    "simple_question": "simple_question",
    "file_references": "file_references",
    "code_blocks": "code_blocks",
    "edit_intent": "edit_intent",
    "test_intent": "test_intent",
    "refactor_intent": "refactor_intent",
    "multi_step_intent": "multi_step",
    "complex_keywords": "complex_keywords",
    "long_prompt": "long_prompt",
    "repo_context": "repo_context",
    "build_intent": "build_intent",
    "tool_failure": "tool_failure",
    "ambiguous_result": "ambiguous_result",
    "incomplete_task": "incomplete_task",
    "clarification": "clarification",
    "acknowledgment": "acknowledgment",
}

# Reverse map for converting autonomy signal strings back to EscalationSignal values
_AUTONOMY_TO_ESCALATION_SIGNAL = {v: k for k, v in _ESCALATION_TO_AUTONOMY_SIGNAL.items()}


@dataclass
class AutonomyConfig:
    """Configuration for Agent autonomy features.
    
    Autonomy is the safety center: doom loops, escalation, sandbox,
    filesystem tracking, and verification hooks all live here.
    
    Attributes:
        enabled: Whether autonomy is enabled
        level: Autonomy level (suggest, auto_edit, full_auto)
        max_iterations: Maximum iterations before stopping
        doom_loop_threshold: Number of repeated actions to trigger doom loop
        auto_escalate: Whether to automatically escalate complexity
        observe: Whether to emit observability events
        completion_promise: Optional string that signals completion when wrapped in <promise>TEXT</promise>
        clear_context: Whether to clear chat history between iterations
        verification_hooks: List of VerificationHook instances for output verification
        track_changes: Whether to track filesystem changes via shadow git.
            Defaults to True when level="full_auto", False otherwise.
            When enabled, agent.undo()/redo()/diff() become available.
        sandbox: Optional SandboxConfig for execution isolation.
            When level="full_auto" and sandbox is None, subprocess sandbox is auto-enabled.
        snapshot_dir: Directory for snapshot storage. Defaults to ~/.praisonai/snapshots.
    
    Usage::
    
        # Simple — full_auto auto-enables tracking + sandbox
        Agent(autonomy="full_auto")
        
        # Advanced — explicit config
        Agent(autonomy=AutonomyConfig(
            level="full_auto",
            track_changes=True,
            sandbox=SandboxConfig.native(writable_paths=["./src"]),
        ))
    """
    enabled: bool = True
    level: str = "suggest"
    max_iterations: int = 20
    doom_loop_threshold: int = 3
    auto_escalate: bool = True
    observe: bool = False
    completion_promise: Optional[str] = None
    clear_context: bool = False
    verification_hooks: Optional[List[Any]] = None
    # Safety features — autonomy owns the safety model
    track_changes: Optional[bool] = None  # None = auto (True for full_auto)
    sandbox: Optional[Any] = None  # SandboxConfig (lazy import to avoid circular)
    snapshot_dir: Optional[str] = None  # Defaults to ~/.praisonai/snapshots
    # Default tools for autonomy mode (auto-populated with code intelligence tools)
    default_tools: Optional[List[Any]] = None  # None = auto (uses get_autonomy_default_tools())
    
    def __post_init__(self):
        if self.level not in VALID_AUTONOMY_LEVELS:
            raise ValueError(
                f"Invalid autonomy level: {self.level!r}. "
                f"Must be one of {sorted(VALID_AUTONOMY_LEVELS)}"
            )
        # Auto-enable track_changes for full_auto if not explicitly set
        if self.track_changes is None:
            self.track_changes = (self.level == "full_auto")
        # Default snapshot directory
        if self.snapshot_dir is None:
            import os
            self.snapshot_dir = os.path.join(
                os.path.expanduser("~"), ".praisonai", "snapshots"
            )
    
    @property
    def effective_track_changes(self) -> bool:
        """Whether track_changes is effectively enabled."""
        return bool(self.track_changes)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AutonomyConfig":
        """Create config from dictionary."""
        level = data.get("level", "suggest")
        if level not in VALID_AUTONOMY_LEVELS:
            raise ValueError(
                f"Invalid autonomy level: {level!r}. "
                f"Must be one of {sorted(VALID_AUTONOMY_LEVELS)}"
            )
        return cls(
            enabled=data.get("enabled", True),
            level=level,
            max_iterations=data.get("max_iterations", 20),
            doom_loop_threshold=data.get("doom_loop_threshold", 3),
            auto_escalate=data.get("auto_escalate", True),
            observe=data.get("observe", False),
            completion_promise=data.get("completion_promise"),
            clear_context=data.get("clear_context", False),
            verification_hooks=data.get("verification_hooks"),
            track_changes=data.get("track_changes"),
            sandbox=data.get("sandbox"),
            snapshot_dir=data.get("snapshot_dir"),
            default_tools=data.get("default_tools"),
        )


class AutonomySignal(str, Enum):
    """Signals detected from prompts for autonomy decisions.
    
    .. deprecated::
        AutonomySignal is deprecated. Use EscalationSignal from
        praisonaiagents.escalation.types instead. AutonomyTrigger
        returns plain strings, not AutonomySignal values.
    """
    SIMPLE_QUESTION = "simple_question"
    FILE_REFERENCES = "file_references"
    CODE_BLOCKS = "code_blocks"
    EDIT_INTENT = "edit_intent"
    TEST_INTENT = "test_intent"
    REFACTOR_INTENT = "refactor_intent"
    MULTI_STEP = "multi_step"
    COMPLEX_KEYWORDS = "complex_keywords"
    
    def __init_subclass__(cls, **kwargs):
        import warnings
        warnings.warn(
            "AutonomySignal is deprecated. Use EscalationSignal instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init_subclass__(**kwargs)


def _warn_autonomy_signal():
    """Emit deprecation warning when AutonomySignal is accessed."""
    import warnings
    warnings.warn(
        "AutonomySignal is deprecated. Use EscalationSignal from "
        "praisonaiagents.escalation.types instead.",
        DeprecationWarning,
        stacklevel=3,
    )


class AutonomyTrigger:
    """Detects signals from prompts for autonomy decisions.
    
    Delegates to EscalationTrigger (DRY, G-DUP-3 fix) and maps
    signal names for backward compatibility.
    """
    
    def __init__(self):
        from ..escalation.triggers import EscalationTrigger
        self._delegate = EscalationTrigger()
    
    def analyze(self, prompt: str) -> Set[str]:
        """Analyze prompt and return detected signals.
        
        Args:
            prompt: The user prompt to analyze
            
        Returns:
            Set of signal names (lowercase strings)
        """
        escalation_signals = self._delegate.analyze(prompt)
        return {
            _ESCALATION_TO_AUTONOMY_SIGNAL.get(s.value, s.value)
            for s in escalation_signals
        }
    
    def recommend_stage(self, signals: Set[str]) -> AutonomyStage:
        """Recommend execution stage based on signals.
        
        Args:
            signals: Set of detected signal names
            
        Returns:
            Recommended AutonomyStage (alias for EscalationStage)
        """
        from ..escalation.types import EscalationSignal
        esc_signals = set()
        for s in signals:
            signal_value = _AUTONOMY_TO_ESCALATION_SIGNAL.get(s, s)
            try:
                esc_signals.add(EscalationSignal(signal_value))
            except ValueError:
                pass
        return self._delegate.recommend_stage(esc_signals)


@dataclass
class AutonomyResult:
    """Result of an autonomous execution.
    
    Attributes:
        success: Whether the task completed successfully
        output: Final output/response
        completion_reason: Why execution stopped (goal, timeout, max_iterations, doom_loop, error, promise)
        iterations: Number of iterations executed
        stage: Final execution stage
        actions: List of actions taken
        duration_seconds: Total execution time
        error: Error message if failed
        started_at: ISO 8601 timestamp when execution started
    """
    success: bool
    output: str = ""
    completion_reason: str = "goal"  # goal, timeout, max_iterations, doom_loop, error, promise
    iterations: int = 0
    stage: str = "direct"
    actions: List[Dict[str, Any]] = field(default_factory=list)
    duration_seconds: float = 0.0
    error: Optional[str] = None
    started_at: Optional[str] = None

    def __str__(self) -> str:
        """Return the output text for display purposes.
        
        When AutonomyResult is printed or converted to str(), users
        should see just the response — not the internal dataclass fields.
        Use repr() for debugging details.
        """
        return self.output or ""


class DoomLoopTracker:
    """Tracks actions to detect doom loops with graduated recovery.
    
    Delegates to DoomLoopDetector (DRY, G-DUP-2 fix) for detection
    while providing graduated recovery actions on top.
    
    Recovery progression:
        1st doom loop → retry_different (try new approach)
        2nd doom loop → escalate_model (use stronger model)
        3rd doom loop → request_help (ask human)
        4th+ doom loop → abort (stop execution)
    """
    
    def __init__(self, threshold: int = 3):
        """Initialize tracker with DoomLoopDetector delegation.
        
        Args:
            threshold: Number of repeated actions to trigger doom loop
        """
        from ..escalation.doom_loop import DoomLoopDetector, DoomLoopConfig
        self.threshold = threshold
        self._delegate = DoomLoopDetector(DoomLoopConfig(
            max_identical_actions=threshold,
            max_consecutive_failures=threshold,
            max_similar_actions=threshold + 2,
        ))
        self._delegate.start_session()
        self._recovery_attempts: int = 0
    
    def record(self, action_type: str, args: Dict[str, Any], result: Any, success: bool) -> None:
        """Record an action for loop detection.
        
        Args:
            action_type: Type of action (e.g., "read_file")
            args: Action arguments
            result: Action result
            success: Whether action succeeded
        """
        self._delegate.record_action(
            action_type=action_type,
            args=args,
            result=result,
            success=success,
        )
    
    def is_doom_loop(self) -> bool:
        """Check if we're in a doom loop.
        
        Returns:
            True if doom loop detected
        """
        return self._delegate.is_doom_loop()
    
    def get_recovery_action(self) -> str:
        """Get recommended recovery action when doom loop detected.
        
        Returns graduated recovery actions:
        - "retry_different": Try a different approach (1st detection)
        - "escalate_model": Escalate to stronger model (2nd detection)
        - "request_help": Request human intervention (3rd detection)
        - "abort": Stop execution (4th+ detection)
        - "continue": No doom loop, continue normally
        """
        if not self.is_doom_loop():
            return "continue"
        
        self._recovery_attempts += 1
        
        if self._recovery_attempts <= 1:
            return "retry_different"
        elif self._recovery_attempts <= 2:
            return "escalate_model"
        elif self._recovery_attempts <= 3:
            return "request_help"
        else:
            return "abort"
    
    def clear_actions(self) -> None:
        """Clear action history but keep recovery attempt count."""
        self._delegate.start_session()
    
    def mark_progress(self, marker: str) -> None:
        """Mark meaningful progress to reset no-progress detection.
        
        Args:
            marker: Description of progress made
        """
        self._delegate.mark_progress(marker)
    
    def reset(self) -> None:
        """Reset the tracker completely."""
        self._delegate.start_session()
        self._recovery_attempts = 0


class AutonomyMixin:
    """Helper-only trait for autonomy utilities.
    
    This module provides reusable helper classes (AutonomyConfig, AutonomyTrigger,
    DoomLoopTracker, AutonomyResult, etc.) that the Agent class uses.
    
    The Agent class is the SINGLE OWNER of all autonomy methods:
    - _init_autonomy()
    - run_autonomous() / run_autonomous_async()
    - analyze_prompt() / get_recommended_stage()
    - _record_action() / _is_doom_loop() / _reset_doom_loop()
    
    This class is intentionally empty — kept only for backward compatibility
    in case external code references it.
    """
    pass
