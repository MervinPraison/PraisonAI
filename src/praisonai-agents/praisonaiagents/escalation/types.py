"""
Types for Escalation Pipeline.

Defines stages, signals, configs, and results for progressive escalation.
"""

from dataclasses import dataclass, field
from enum import IntEnum, Enum
from typing import Any, Dict, List, Optional, Set


class EscalationStage(IntEnum):
    """
    Escalation stages for progressive execution.
    
    Stage 0: Direct response - no tools, no planning, immediate answer
    Stage 1: Heuristic tools - use tools based on local signals, no extra LLM call
    Stage 2: Lightweight plan - single LLM call to create constrained plan
    Stage 3: Full autonomous - tools + subagents + verification + checkpoints
    """
    DIRECT = 0       # Direct response, no tools
    HEURISTIC = 1    # Heuristic tool selection
    PLANNED = 2      # Lightweight planning
    AUTONOMOUS = 3   # Full autonomous loop


class EscalationSignal(Enum):
    """
    Signals that indicate escalation may be needed.
    
    These are detected without extra LLM calls using heuristics.
    """
    # Complexity signals
    LONG_PROMPT = "long_prompt"              # Word count > threshold
    COMPLEX_KEYWORDS = "complex_keywords"    # Contains analysis/design/etc keywords
    MULTI_STEP_INTENT = "multi_step_intent"  # Multiple questions or steps implied
    
    # Context signals
    REPO_CONTEXT = "repo_context"            # Working in a code repository
    FILE_REFERENCES = "file_references"      # References specific files
    CODE_BLOCKS = "code_blocks"              # Contains code to analyze/modify
    
    # Task signals
    EDIT_INTENT = "edit_intent"              # User wants to modify files
    TEST_INTENT = "test_intent"              # User wants to run tests
    BUILD_INTENT = "build_intent"            # User wants to build/compile
    REFACTOR_INTENT = "refactor_intent"      # User wants to refactor code
    
    # Failure signals (for escalation during execution)
    TOOL_FAILURE = "tool_failure"            # Tool call failed
    AMBIGUOUS_RESULT = "ambiguous_result"    # Result is unclear
    INCOMPLETE_TASK = "incomplete_task"      # Task not fully completed
    
    # De-escalation signals
    SIMPLE_QUESTION = "simple_question"      # Simple factual question
    CLARIFICATION = "clarification"          # User asking for clarification
    ACKNOWLEDGMENT = "acknowledgment"        # User acknowledging/thanking


@dataclass
class EscalationConfig:
    """
    Configuration for escalation pipeline.
    
    Controls thresholds, budgets, and behavior.
    """
    # Stage thresholds
    long_prompt_threshold: int = 100         # Words to trigger LONG_PROMPT
    complex_keyword_threshold: int = 2       # Keywords to trigger COMPLEX_KEYWORDS
    
    # Budgets
    max_steps: int = 20                      # Maximum steps in autonomous mode
    max_time_seconds: int = 300              # Maximum time for task
    max_tokens: int = 100000                 # Maximum tokens to use
    max_tool_calls: int = 50                 # Maximum tool calls
    
    # Stage-specific limits
    heuristic_max_tools: int = 3             # Max tools in heuristic stage
    planned_max_steps: int = 5               # Max steps in planned stage
    
    # Behavior
    auto_escalate: bool = True               # Auto-escalate on signals
    auto_deescalate: bool = True             # Auto-de-escalate when resolved
    require_approval_for_writes: bool = True # Require approval for file writes
    enable_checkpoints: bool = True          # Enable checkpoints for undo
    
    # Doom loop prevention
    max_retries: int = 3                     # Max retries per step
    max_identical_actions: int = 3           # Max identical consecutive actions
    backoff_factor: float = 1.5              # Backoff multiplier on retry
    
    # Model routing
    use_router: bool = True                  # Use model router
    escalate_model_on_failure: bool = True   # Try stronger model on failure


@dataclass
class EscalationResult:
    """
    Result of escalation pipeline execution.
    
    Contains the response, metadata, and any state changes.
    """
    # Core result
    response: str
    success: bool
    
    # Stage info
    initial_stage: EscalationStage
    final_stage: EscalationStage
    escalations: int = 0
    deescalations: int = 0
    
    # Signals detected
    signals: List[EscalationSignal] = field(default_factory=list)
    
    # Execution stats
    steps_taken: int = 0
    tool_calls: int = 0
    tokens_used: int = 0
    time_seconds: float = 0.0
    
    # Checkpoints
    checkpoint_id: Optional[str] = None
    files_modified: List[str] = field(default_factory=list)
    
    # Errors
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def was_escalated(self) -> bool:
        """Check if execution was escalated."""
        return self.final_stage > self.initial_stage
    
    @property
    def was_deescalated(self) -> bool:
        """Check if execution was de-escalated."""
        return self.final_stage < self.initial_stage


@dataclass
class StageContext:
    """
    Context passed between escalation stages.
    
    Maintains state across stage transitions.
    """
    # Current state
    stage: EscalationStage
    prompt: str
    signals: Set[EscalationSignal] = field(default_factory=set)
    
    # Execution history
    steps: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    
    # Accumulated context
    context_summary: str = ""
    files_read: Set[str] = field(default_factory=set)
    files_modified: Set[str] = field(default_factory=set)
    
    # Budget tracking
    tokens_used: int = 0
    tool_calls: int = 0
    time_elapsed: float = 0.0
    
    # Checkpoints
    checkpoint_ids: List[str] = field(default_factory=list)
    
    # Session
    session_id: Optional[str] = None
    
    def add_step(self, action: str, result: Any, success: bool = True):
        """Add a step to history."""
        self.steps.append({
            "action": action,
            "result": result,
            "success": success,
            "stage": self.stage.name,
        })
    
    def add_tool_result(self, tool: str, args: Dict, result: Any, success: bool = True):
        """Add a tool result."""
        self.tool_results.append({
            "tool": tool,
            "args": args,
            "result": result,
            "success": success,
        })
        self.tool_calls += 1
    
    def should_escalate(self, config: EscalationConfig) -> bool:
        """Check if escalation is needed based on current state."""
        # Check for failure signals
        recent_failures = sum(
            1 for step in self.steps[-3:]
            if not step.get("success", True)
        )
        if recent_failures >= 2:
            return True
        
        # Check for incomplete task signals
        if EscalationSignal.INCOMPLETE_TASK in self.signals:
            return True
        
        return False
    
    def should_deescalate(self, config: EscalationConfig) -> bool:
        """Check if de-escalation is appropriate."""
        # If task is simple and resolved
        if EscalationSignal.SIMPLE_QUESTION in self.signals:
            return True
        
        # If recent steps all succeeded and no complex signals
        recent_success = all(
            step.get("success", True)
            for step in self.steps[-3:]
        )
        if recent_success and not self._has_complex_signals():
            return True
        
        return False
    
    def _has_complex_signals(self) -> bool:
        """Check if any complex signals are present."""
        complex_signals = {
            EscalationSignal.COMPLEX_KEYWORDS,
            EscalationSignal.MULTI_STEP_INTENT,
            EscalationSignal.REFACTOR_INTENT,
        }
        return bool(self.signals & complex_signals)
