"""
Escalation Triggers for PraisonAI Agents.

Detects signals that indicate escalation or de-escalation is needed.
Uses heuristics only - no extra LLM calls for signal detection.
"""

import re
from typing import Set, Optional, Dict, Any
from .types import EscalationSignal, EscalationStage, EscalationConfig


class EscalationTrigger:
    """
    Detects escalation signals from prompts and context.
    
    Uses fast heuristics to determine task complexity without
    making additional LLM calls. This ensures zero overhead
    for simple tasks.
    
    Example:
        trigger = EscalationTrigger()
        signals = trigger.analyze("Refactor the auth module")
        stage = trigger.recommend_stage(signals)
    """
    
    # Keywords indicating complex tasks
    COMPLEX_KEYWORDS = [
        "analyze", "research", "comprehensive", "detailed",
        "compare", "evaluate", "synthesize", "multi-step",
        "code review", "architecture", "design pattern",
        "optimize", "debug", "refactor", "implement",
        "build", "create", "develop", "integrate",
    ]
    
    # Keywords indicating simple tasks
    SIMPLE_KEYWORDS = [
        "what is", "define", "list", "name", "when",
        "where", "who", "simple", "quick", "brief",
        "explain", "describe", "tell me", "show me",
    ]
    
    # Keywords indicating edit intent
    EDIT_KEYWORDS = [
        "edit", "modify", "change", "update", "fix",
        "add", "remove", "delete", "replace", "rename",
        "write", "create file", "save",
    ]
    
    # Keywords indicating test intent
    TEST_KEYWORDS = [
        "test", "run tests", "pytest", "unittest",
        "verify", "check", "validate", "assert",
    ]
    
    # Keywords indicating build intent
    BUILD_KEYWORDS = [
        "build", "compile", "make", "npm", "pip install",
        "cargo build", "go build", "mvn", "gradle",
    ]
    
    # Keywords indicating refactor intent
    REFACTOR_KEYWORDS = [
        "refactor", "restructure", "reorganize", "clean up",
        "improve", "optimize", "simplify", "extract",
        "move", "split", "merge", "consolidate",
    ]
    
    # File path patterns
    FILE_PATTERN = re.compile(
        r'(?:^|[\s\'"(])([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)(?:[\s\'")]|$)',
        re.MULTILINE
    )
    
    # Code block pattern
    CODE_BLOCK_PATTERN = re.compile(r'```[\s\S]*?```|`[^`]+`')
    
    def __init__(self, config: Optional[EscalationConfig] = None):
        """Initialize trigger with optional config."""
        self.config = config or EscalationConfig()
    
    def analyze(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Set[EscalationSignal]:
        """
        Analyze prompt and context for escalation signals.
        
        Args:
            prompt: User prompt to analyze
            context: Optional context (workspace, history, etc.)
            
        Returns:
            Set of detected signals
        """
        signals: Set[EscalationSignal] = set()
        prompt_lower = prompt.lower()
        word_count = len(prompt.split())
        
        # Check prompt length
        if word_count > self.config.long_prompt_threshold:
            signals.add(EscalationSignal.LONG_PROMPT)
        
        # Check for complex keywords
        complex_count = sum(
            1 for kw in self.COMPLEX_KEYWORDS
            if kw in prompt_lower
        )
        if complex_count >= self.config.complex_keyword_threshold:
            signals.add(EscalationSignal.COMPLEX_KEYWORDS)
        
        # Check for simple keywords
        simple_count = sum(
            1 for kw in self.SIMPLE_KEYWORDS
            if kw in prompt_lower
        )
        if simple_count >= 1 and complex_count == 0 and word_count < 30:
            signals.add(EscalationSignal.SIMPLE_QUESTION)
        
        # Check for multi-step intent (multiple questions or "and then")
        if self._has_multi_step_intent(prompt):
            signals.add(EscalationSignal.MULTI_STEP_INTENT)
        
        # Check for file references
        if self.FILE_PATTERN.search(prompt):
            signals.add(EscalationSignal.FILE_REFERENCES)
        
        # Check for code blocks
        if self.CODE_BLOCK_PATTERN.search(prompt):
            signals.add(EscalationSignal.CODE_BLOCKS)
        
        # Check for edit intent
        if any(kw in prompt_lower for kw in self.EDIT_KEYWORDS):
            signals.add(EscalationSignal.EDIT_INTENT)
        
        # Check for test intent
        if any(kw in prompt_lower for kw in self.TEST_KEYWORDS):
            signals.add(EscalationSignal.TEST_INTENT)
        
        # Check for build intent
        if any(kw in prompt_lower for kw in self.BUILD_KEYWORDS):
            signals.add(EscalationSignal.BUILD_INTENT)
        
        # Check for refactor intent
        if any(kw in prompt_lower for kw in self.REFACTOR_KEYWORDS):
            signals.add(EscalationSignal.REFACTOR_INTENT)
        
        # Check context for repo signals
        if context:
            if context.get("is_git_repo") or context.get("workspace"):
                signals.add(EscalationSignal.REPO_CONTEXT)
        
        return signals
    
    def _has_multi_step_intent(self, prompt: str) -> bool:
        """Check if prompt implies multiple steps."""
        prompt_lower = prompt.lower()
        
        # Multiple questions
        question_count = prompt.count("?")
        if question_count > 1:
            return True
        
        # Sequential indicators
        sequential_patterns = [
            "and then", "after that", "next,", "finally,",
            "first,", "second,", "third,", "step 1", "step 2",
            "1.", "2.", "3.",
        ]
        if any(p in prompt_lower for p in sequential_patterns):
            return True
        
        # Multiple action verbs
        action_verbs = ["create", "update", "delete", "add", "remove", "fix", "change"]
        verb_count = sum(1 for v in action_verbs if v in prompt_lower)
        if verb_count > 2:
            return True
        
        return False
    
    def recommend_stage(
        self,
        signals: Set[EscalationSignal],
        current_stage: Optional[EscalationStage] = None
    ) -> EscalationStage:
        """
        Recommend an escalation stage based on signals.
        
        Args:
            signals: Set of detected signals
            current_stage: Current stage (for escalation/de-escalation)
            
        Returns:
            Recommended stage
        """
        # Start with direct response
        stage = EscalationStage.DIRECT
        
        # Check for simple question (stay at DIRECT)
        if EscalationSignal.SIMPLE_QUESTION in signals:
            if not self._has_escalation_signals(signals):
                return EscalationStage.DIRECT
        
        # Check for heuristic-level signals
        heuristic_signals = {
            EscalationSignal.FILE_REFERENCES,
            EscalationSignal.CODE_BLOCKS,
            EscalationSignal.REPO_CONTEXT,
        }
        if signals & heuristic_signals:
            stage = max(stage, EscalationStage.HEURISTIC)
        
        # Check for planned-level signals
        planned_signals = {
            EscalationSignal.EDIT_INTENT,
            EscalationSignal.TEST_INTENT,
            EscalationSignal.BUILD_INTENT,
            EscalationSignal.COMPLEX_KEYWORDS,
        }
        if signals & planned_signals:
            stage = max(stage, EscalationStage.PLANNED)
        
        # Check for autonomous-level signals
        autonomous_signals = {
            EscalationSignal.MULTI_STEP_INTENT,
            EscalationSignal.REFACTOR_INTENT,
            EscalationSignal.LONG_PROMPT,
        }
        if signals & autonomous_signals:
            stage = max(stage, EscalationStage.AUTONOMOUS)
        
        # Handle escalation from current stage
        if current_stage is not None:
            # Failure signals always escalate
            failure_signals = {
                EscalationSignal.TOOL_FAILURE,
                EscalationSignal.INCOMPLETE_TASK,
                EscalationSignal.AMBIGUOUS_RESULT,
            }
            if signals & failure_signals:
                stage = max(stage, EscalationStage(min(current_stage + 1, 3)))
        
        return stage
    
    def _has_escalation_signals(self, signals: Set[EscalationSignal]) -> bool:
        """Check if any escalation-triggering signals are present."""
        escalation_signals = {
            EscalationSignal.COMPLEX_KEYWORDS,
            EscalationSignal.MULTI_STEP_INTENT,
            EscalationSignal.EDIT_INTENT,
            EscalationSignal.REFACTOR_INTENT,
            EscalationSignal.TOOL_FAILURE,
        }
        return bool(signals & escalation_signals)
    
    def should_escalate(
        self,
        signals: Set[EscalationSignal],
        current_stage: EscalationStage,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Check if escalation is recommended.
        
        Args:
            signals: Current signals
            current_stage: Current execution stage
            context: Optional execution context
            
        Returns:
            True if escalation is recommended
        """
        recommended = self.recommend_stage(signals, current_stage)
        return recommended > current_stage
    
    def should_deescalate(
        self,
        signals: Set[EscalationSignal],
        current_stage: EscalationStage,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Check if de-escalation is appropriate.
        
        Args:
            signals: Current signals
            current_stage: Current execution stage
            context: Optional execution context
            
        Returns:
            True if de-escalation is appropriate
        """
        # Don't de-escalate from DIRECT
        if current_stage == EscalationStage.DIRECT:
            return False
        
        # De-escalate if only simple signals remain
        if EscalationSignal.SIMPLE_QUESTION in signals:
            if not self._has_escalation_signals(signals):
                return True
        
        # De-escalate if task appears complete
        if context:
            if context.get("task_complete", False):
                return True
            
            # De-escalate if recent steps all succeeded
            recent_steps = context.get("recent_steps", [])
            if len(recent_steps) >= 3:
                if all(s.get("success", True) for s in recent_steps):
                    return True
        
        return False
    
    def get_stage_description(self, stage: EscalationStage) -> str:
        """Get human-readable description of a stage."""
        descriptions = {
            EscalationStage.DIRECT: "Direct response (no tools)",
            EscalationStage.HEURISTIC: "Heuristic tool selection",
            EscalationStage.PLANNED: "Lightweight planning",
            EscalationStage.AUTONOMOUS: "Full autonomous execution",
        }
        return descriptions.get(stage, "Unknown stage")
