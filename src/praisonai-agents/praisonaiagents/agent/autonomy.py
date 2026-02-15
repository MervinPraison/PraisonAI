"""
Agent Autonomy Module.

Provides agent-centric autonomy configuration and helpers.
This module integrates escalation, doom loop detection, and observability
directly into the Agent class as first-class capabilities.

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
from typing import Optional, Dict, Any, List, Set, Callable, Protocol, runtime_checkable
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class AutonomyStage(str, Enum):
    """Autonomy execution stages."""
    DIRECT = "direct"
    HEURISTIC = "heuristic"
    PLANNED = "planned"
    AUTONOMOUS = "autonomous"


@dataclass
class AutonomyConfig:
    """Configuration for Agent autonomy features.
    
    Attributes:
        enabled: Whether autonomy is enabled
        max_iterations: Maximum iterations before stopping
        doom_loop_threshold: Number of repeated actions to trigger doom loop
        auto_escalate: Whether to automatically escalate complexity
        observe: Whether to emit observability events
        completion_promise: Optional string that signals completion when wrapped in <promise>TEXT</promise>
        clear_context: Whether to clear chat history between iterations
        verification_hooks: List of VerificationHook instances for output verification
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
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AutonomyConfig":
        """Create config from dictionary."""
        return cls(
            enabled=data.get("enabled", True),
            level=data.get("level", "suggest"),
            max_iterations=data.get("max_iterations", 20),
            doom_loop_threshold=data.get("doom_loop_threshold", 3),
            auto_escalate=data.get("auto_escalate", True),
            observe=data.get("observe", False),
            completion_promise=data.get("completion_promise"),
            clear_context=data.get("clear_context", False),
            verification_hooks=data.get("verification_hooks"),
        )


class AutonomySignal(str, Enum):
    """Signals detected from prompts for autonomy decisions."""
    SIMPLE_QUESTION = "simple_question"
    FILE_REFERENCES = "file_references"
    CODE_BLOCKS = "code_blocks"
    EDIT_INTENT = "edit_intent"
    TEST_INTENT = "test_intent"
    REFACTOR_INTENT = "refactor_intent"
    MULTI_STEP = "multi_step"
    COMPLEX_KEYWORDS = "complex_keywords"


class AutonomyTrigger:
    """Detects signals from prompts for autonomy decisions.
    
    Uses fast heuristics (no LLM calls) to analyze prompts.
    """
    
    # Keywords that indicate simple questions
    SIMPLE_KEYWORDS = {
        "what is", "what's", "define", "explain", "describe",
        "how does", "why is", "when was", "who is", "where is"
    }
    
    # Keywords that indicate complex tasks
    COMPLEX_KEYWORDS = {
        "analyze", "refactor", "optimize", "implement", "design",
        "architect", "debug", "fix", "modify", "update", "change",
        "create", "build", "develop", "integrate", "migrate"
    }
    
    # Keywords that indicate edit intent
    EDIT_KEYWORDS = {
        "edit", "modify", "change", "update", "fix", "add", "remove",
        "delete", "replace", "insert", "write", "rewrite"
    }
    
    # Keywords that indicate test intent
    TEST_KEYWORDS = {
        "test", "verify", "validate", "check", "assert", "ensure",
        "unit test", "integration test", "e2e", "coverage"
    }
    
    # Keywords that indicate refactor intent
    REFACTOR_KEYWORDS = {
        "refactor", "restructure", "reorganize", "clean up",
        "simplify", "extract", "inline", "rename"
    }
    
    # Multi-step indicators
    MULTI_STEP_INDICATORS = {
        "first", "then", "next", "after", "finally", "step",
        "1.", "2.", "3.", "and then", "followed by"
    }
    
    def analyze(self, prompt: str) -> Set[str]:
        """Analyze prompt and return detected signals.
        
        Args:
            prompt: The user prompt to analyze
            
        Returns:
            Set of signal names (lowercase strings)
        """
        signals: Set[str] = set()
        prompt_lower = prompt.lower()
        
        # Check for simple questions
        if any(kw in prompt_lower for kw in self.SIMPLE_KEYWORDS):
            word_count = len(prompt.split())
            if word_count < 30:
                signals.add("simple_question")
        
        # Check for file references
        import re
        file_pattern = r'[\w\-./]+\.(py|js|ts|tsx|jsx|java|go|rs|cpp|c|h|md|txt|json|yaml|yml|toml)'
        if re.search(file_pattern, prompt):
            signals.add("file_references")
        
        # Check for code blocks
        if "```" in prompt:
            signals.add("code_blocks")
        
        # Check for edit intent
        if any(kw in prompt_lower for kw in self.EDIT_KEYWORDS):
            signals.add("edit_intent")
        
        # Check for test intent
        if any(kw in prompt_lower for kw in self.TEST_KEYWORDS):
            signals.add("test_intent")
        
        # Check for refactor intent
        if any(kw in prompt_lower for kw in self.REFACTOR_KEYWORDS):
            signals.add("refactor_intent")
        
        # Check for multi-step
        if any(ind in prompt_lower for ind in self.MULTI_STEP_INDICATORS):
            signals.add("multi_step")
        
        # Check for complex keywords
        if any(kw in prompt_lower for kw in self.COMPLEX_KEYWORDS):
            signals.add("complex_keywords")
        
        return signals
    
    def recommend_stage(self, signals: Set[str]) -> AutonomyStage:
        """Recommend execution stage based on signals.
        
        Args:
            signals: Set of detected signal names
            
        Returns:
            Recommended AutonomyStage
        """
        # AUTONOMOUS: multi-step or refactor
        if "multi_step" in signals or "refactor_intent" in signals:
            return AutonomyStage.AUTONOMOUS
        
        # PLANNED: edit or test intent
        if "edit_intent" in signals or "test_intent" in signals:
            return AutonomyStage.PLANNED
        
        # HEURISTIC: file references or code blocks
        if "file_references" in signals or "code_blocks" in signals:
            return AutonomyStage.HEURISTIC
        
        # DIRECT: simple questions or no signals
        return AutonomyStage.DIRECT


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


class DoomLoopTracker:
    """Tracks actions to detect doom loops.
    
    A doom loop occurs when the agent repeats the same action
    multiple times without making progress.
    """
    
    def __init__(self, threshold: int = 3):
        """Initialize tracker.
        
        Args:
            threshold: Number of repeated actions to trigger doom loop
        """
        self.threshold = threshold
        self.actions: List[str] = []
        self.action_counts: Dict[str, int] = {}
    
    def record(self, action_type: str, args: Dict[str, Any], result: Any, success: bool) -> None:
        """Record an action.
        
        Args:
            action_type: Type of action (e.g., "read_file")
            args: Action arguments
            result: Action result
            success: Whether action succeeded
        """
        # Create action signature
        sig = f"{action_type}:{hash(str(sorted(args.items())))}"
        self.actions.append(sig)
        self.action_counts[sig] = self.action_counts.get(sig, 0) + 1
    
    def is_doom_loop(self) -> bool:
        """Check if we're in a doom loop.
        
        Returns:
            True if doom loop detected
        """
        if not self.actions:
            return False
        
        # Check if any action repeated too many times
        for count in self.action_counts.values():
            if count >= self.threshold:
                return True
        
        return False
    
    def reset(self) -> None:
        """Reset the tracker."""
        self.actions.clear()
        self.action_counts.clear()


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
