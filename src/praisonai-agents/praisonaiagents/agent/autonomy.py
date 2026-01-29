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
import time
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
    """
    enabled: bool = True
    max_iterations: int = 20
    doom_loop_threshold: int = 3
    auto_escalate: bool = True
    observe: bool = False
    completion_promise: Optional[str] = None
    clear_context: bool = False
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AutonomyConfig":
        """Create config from dictionary."""
        return cls(
            enabled=data.get("enabled", True),
            max_iterations=data.get("max_iterations", 20),
            doom_loop_threshold=data.get("doom_loop_threshold", 3),
            auto_escalate=data.get("auto_escalate", True),
            observe=data.get("observe", False),
            completion_promise=data.get("completion_promise"),
            clear_context=data.get("clear_context", False),
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
    """Mixin class that adds autonomy capabilities to Agent.
    
    This mixin provides:
    - Signal detection from prompts
    - Stage recommendation
    - Doom loop detection
    - Observability hooks
    """
    
    def _init_autonomy(self, autonomy: Any, verification_hooks: Optional[List[Any]] = None) -> None:
        """Initialize autonomy features.
        
        Args:
            autonomy: True, False, dict config, or AutonomyConfig
            verification_hooks: Optional list of verification hooks
        """
        # Initialize verification hooks (always available, even without autonomy)
        self._verification_hooks = verification_hooks or []
        
        if autonomy is None or autonomy is False:
            self.autonomy_enabled = False
            self.autonomy_config = {}
            self._autonomy_trigger = None
            self._doom_loop_tracker = None
            return
        
        self.autonomy_enabled = True
        
        if autonomy is True:
            self.autonomy_config = {}
            config = AutonomyConfig()
        elif isinstance(autonomy, dict):
            self.autonomy_config = autonomy.copy()
            config = AutonomyConfig.from_dict(autonomy)
            # Extract verification_hooks from dict if provided
            if "verification_hooks" in autonomy and not verification_hooks:
                self._verification_hooks = autonomy.get("verification_hooks", [])
        elif isinstance(autonomy, AutonomyConfig):
            self.autonomy_config = {
                "max_iterations": autonomy.max_iterations,
                "doom_loop_threshold": autonomy.doom_loop_threshold,
                "auto_escalate": autonomy.auto_escalate,
            }
            config = autonomy
        else:
            self.autonomy_enabled = False
            self.autonomy_config = {}
            self._autonomy_trigger = None
            self._doom_loop_tracker = None
            return
        
        self._autonomy_trigger = AutonomyTrigger()
        self._doom_loop_tracker = DoomLoopTracker(threshold=config.doom_loop_threshold)
    
    def analyze_prompt(self, prompt: str) -> Set[str]:
        """Analyze prompt for autonomy signals.
        
        Args:
            prompt: The user prompt
            
        Returns:
            Set of detected signal names
        """
        if not self.autonomy_enabled or self._autonomy_trigger is None:
            return set()
        return self._autonomy_trigger.analyze(prompt)
    
    def get_recommended_stage(self, prompt: str) -> str:
        """Get recommended execution stage for prompt.
        
        Args:
            prompt: The user prompt
            
        Returns:
            Stage name as string (direct, heuristic, planned, autonomous)
        """
        if not self.autonomy_enabled or self._autonomy_trigger is None:
            return "direct"
        
        signals = self._autonomy_trigger.analyze(prompt)
        stage = self._autonomy_trigger.recommend_stage(signals)
        return stage.value
    
    def _record_action(self, action_type: str, args: Dict[str, Any], result: Any, success: bool) -> None:
        """Record an action for doom loop tracking.
        
        Args:
            action_type: Type of action
            args: Action arguments
            result: Action result
            success: Whether action succeeded
        """
        if self._doom_loop_tracker is not None:
            self._doom_loop_tracker.record(action_type, args, result, success)
    
    def _is_doom_loop(self) -> bool:
        """Check if we're in a doom loop.
        
        Returns:
            True if doom loop detected
        """
        if self._doom_loop_tracker is None:
            return False
        return self._doom_loop_tracker.is_doom_loop()
    
    def _reset_doom_loop(self) -> None:
        """Reset doom loop tracking."""
        if self._doom_loop_tracker is not None:
            self._doom_loop_tracker.reset()
    
    def run_autonomous(
        self,
        prompt: str,
        max_iterations: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        completion_promise: Optional[str] = None,
        clear_context: bool = False,
    ) -> AutonomyResult:
        """Run an autonomous task execution loop.
        
        This method executes a task autonomously, using the agent's tools
        and capabilities to complete the task. It handles:
        - Progressive escalation based on task complexity
        - Doom loop detection and recovery
        - Iteration limits and timeouts
        - Completion detection (keyword-based or promise-based)
        - Optional context clearing between iterations
        
        Args:
            prompt: The task to execute
            max_iterations: Override max iterations (default from config)
            timeout_seconds: Timeout in seconds (default: no timeout)
            completion_promise: Optional string that signals completion when 
                wrapped in <promise>TEXT</promise> tags in the response
            clear_context: Whether to clear chat history between iterations
                (forces agent to rely on external state like files)
            
        Returns:
            AutonomyResult with success status, output, and metadata
            
        Raises:
            ValueError: If autonomy is not enabled
            
        Example:
            agent = Agent(instructions="...", autonomy=True)
            result = agent.run_autonomous(
                "Refactor the auth module",
                completion_promise="DONE",
                clear_context=True
            )
            if result.success:
                print(result.output)
        """
        if not self.autonomy_enabled:
            raise ValueError(
                "Autonomy must be enabled to use run_autonomous(). "
                "Create agent with autonomy=True or autonomy={...}"
            )
        
        start_time = time.time()
        iterations = 0
        actions_taken: List[Dict[str, Any]] = []
        
        # Get config values
        config_max_iter = self.autonomy_config.get("max_iterations", 20)
        effective_max_iter = max_iterations if max_iterations is not None else config_max_iter
        
        # Get completion_promise from config if not provided as param
        effective_promise = completion_promise
        if effective_promise is None:
            effective_promise = self.autonomy_config.get("completion_promise")
        
        # Get clear_context from config if not explicitly set
        effective_clear_context = clear_context
        if not clear_context:
            effective_clear_context = self.autonomy_config.get("clear_context", False)
        
        # Analyze prompt and get recommended stage
        stage = self.get_recommended_stage(prompt)
        
        # Reset doom loop tracker for new task
        self._reset_doom_loop()
        
        try:
            # Execute the autonomous loop
            while iterations < effective_max_iter:
                iterations += 1
                
                # Check timeout
                if timeout_seconds and (time.time() - start_time) > timeout_seconds:
                    return AutonomyResult(
                        success=False,
                        output="Task timed out",
                        completion_reason="timeout",
                        iterations=iterations,
                        stage=stage,
                        actions=actions_taken,
                        duration_seconds=time.time() - start_time,
                    )
                
                # Check doom loop
                if self._is_doom_loop():
                    logger.warning(f"Doom loop detected after {iterations} iterations")
                    return AutonomyResult(
                        success=False,
                        output="Task stopped due to repeated actions (doom loop)",
                        completion_reason="doom_loop",
                        iterations=iterations,
                        stage=stage,
                        actions=actions_taken,
                        duration_seconds=time.time() - start_time,
                    )
                
                # Execute one turn using the agent's chat method
                # Always use the original prompt (prompt re-injection)
                try:
                    response = self.chat(prompt)
                except Exception as e:
                    logger.error(f"Error during autonomous execution: {e}")
                    return AutonomyResult(
                        success=False,
                        output=str(e),
                        completion_reason="error",
                        iterations=iterations,
                        stage=stage,
                        actions=actions_taken,
                        duration_seconds=time.time() - start_time,
                        error=str(e),
                    )
                
                # Record the action
                actions_taken.append({
                    "iteration": iterations,
                    "response": str(response)[:500],  # Truncate for storage
                })
                
                response_str = str(response)
                
                # Check for completion promise FIRST (structured signal)
                if effective_promise:
                    promise_tag = f"<promise>{effective_promise}</promise>"
                    if promise_tag in response_str:
                        return AutonomyResult(
                            success=True,
                            output=response_str,
                            completion_reason="promise",
                            iterations=iterations,
                            stage=stage,
                            actions=actions_taken,
                            duration_seconds=time.time() - start_time,
                        )
                
                # Check for keyword-based completion signals (fallback)
                response_lower = response_str.lower()
                completion_signals = [
                    "task completed",
                    "task complete",
                    "done",
                    "finished",
                    "completed successfully",
                ]
                
                if any(signal in response_lower for signal in completion_signals):
                    return AutonomyResult(
                        success=True,
                        output=response_str,
                        completion_reason="goal",
                        iterations=iterations,
                        stage=stage,
                        actions=actions_taken,
                        duration_seconds=time.time() - start_time,
                    )
                
                # For DIRECT stage, complete after first response
                if stage == "direct":
                    return AutonomyResult(
                        success=True,
                        output=response_str,
                        completion_reason="goal",
                        iterations=iterations,
                        stage=stage,
                        actions=actions_taken,
                        duration_seconds=time.time() - start_time,
                    )
                
                # Clear context between iterations if enabled
                if effective_clear_context:
                    self.clear_history()
            
            # Max iterations reached
            return AutonomyResult(
                success=False,
                output="Max iterations reached",
                completion_reason="max_iterations",
                iterations=iterations,
                stage=stage,
                actions=actions_taken,
                duration_seconds=time.time() - start_time,
            )
            
        except Exception as e:
            logger.error(f"Unexpected error in run_autonomous: {e}")
            return AutonomyResult(
                success=False,
                output=str(e),
                completion_reason="error",
                iterations=iterations,
                stage=stage,
                actions=actions_taken,
                duration_seconds=time.time() - start_time,
                error=str(e),
            )
    
    def delegate(
        self,
        task: str,
        profile: str = "general",
        timeout_seconds: float = 300.0,
        context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Delegate a task to a subagent.
        
        Args:
            task: Task description for the subagent
            profile: Agent profile to use (explorer, coder, tester, etc.)
            timeout_seconds: Timeout for the delegated task
            context: Additional context to pass to subagent
            
        Returns:
            Result from the subagent
        """
        subagent = self._create_subagent(profile, context)
        return subagent.chat(task)
    
    def _create_subagent(
        self,
        profile: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Create a subagent with the specified profile.
        
        Args:
            profile: Agent profile name
            context: Additional context
            
        Returns:
            Configured Agent instance
        """
        # Import here to avoid circular imports
        from .agent import Agent
        from ..agents.profiles import get_profile, BUILTIN_PROFILES
        
        # Get profile config
        profile_config = get_profile(profile) if profile in BUILTIN_PROFILES else None
        
        if profile_config:
            return Agent(
                name=f"subagent_{profile}",
                instructions=profile_config.system_prompt,
                tools=profile_config.tools if hasattr(profile_config, 'tools') else None,
            )
        else:
            # Default subagent
            return Agent(
                name=f"subagent_{profile}",
                instructions=f"You are a {profile} assistant.",
            )
    
    def _run_verification_hooks(self) -> List[Dict[str, Any]]:
        """Run all registered verification hooks.
        
        Returns:
            List of verification results
        """
        results = []
        if hasattr(self, '_verification_hooks') and self._verification_hooks:
            for hook in self._verification_hooks:
                try:
                    result = hook.run()
                    results.append({
                        "hook": hook.name,
                        "success": result.get("success", False),
                        "output": result.get("output", ""),
                    })
                except Exception as e:
                    results.append({
                        "hook": getattr(hook, 'name', 'unknown'),
                        "success": False,
                        "error": str(e),
                    })
        return results
