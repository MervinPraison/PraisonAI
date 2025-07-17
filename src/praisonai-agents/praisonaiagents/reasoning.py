"""
Reasoning module for advanced reasoning capabilities in PraisonAI Agents.

This module provides enhanced reasoning features including:
- ReasoningConfig for configurable reasoning parameters
- ActionState enum for flow control
- ReasoningAgent with built-in reasoning capabilities
- DualBrainAgent with separate LLMs for conversation and reasoning
- Confidence scoring and validation
- Step-by-step reasoning with flow control
"""

from typing import List, Optional, Any, Dict, Union, Literal, Callable, Tuple
from enum import Enum
from pydantic import BaseModel, Field
import time
import uuid


class ActionState(Enum):
    """Action states for reasoning flow control."""
    CONTINUE = "continue"
    VALIDATE = "validate"
    FINAL_ANSWER = "final_answer"
    RESET = "reset"


class ReasoningConfig(BaseModel):
    """Configuration for reasoning behavior."""
    min_steps: int = Field(default=2, description="Minimum number of reasoning steps")
    max_steps: int = Field(default=10, description="Maximum number of reasoning steps")
    style: Literal["analytical", "creative", "systematic"] = Field(
        default="analytical", 
        description="Reasoning style: analytical, creative, or systematic"
    )
    confidence_threshold: float = Field(
        default=0.8, 
        description="Minimum confidence threshold for proceeding"
    )
    show_internal_thoughts: bool = Field(
        default=True, 
        description="Whether to display internal reasoning thoughts"
    )
    auto_validate_critical: bool = Field(
        default=True, 
        description="Automatically validate critical reasoning steps"
    )


class ReasoningStep(BaseModel):
    """Individual reasoning step with metadata."""
    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    step_number: int
    title: str
    thought: str
    action: str
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: float = Field(default_factory=time.time)
    action_state: ActionState = ActionState.CONTINUE
    retries: int = 0


class ReasoningTrace(BaseModel):
    """Complete reasoning trace for a problem."""
    problem: str
    steps: List[ReasoningStep] = Field(default_factory=list)
    final_answer: str = ""
    overall_confidence: float = 0.0
    total_time: float = 0.0
    started_at: float = Field(default_factory=time.time)
    completed_at: Optional[float] = None


class ReasoningFlow:
    """Flow control for reasoning processes."""
    
    def __init__(
        self,
        on_validate: Optional[Callable[[ReasoningStep], bool]] = None,
        on_reset: Optional[Callable[[ReasoningStep], bool]] = None,
        auto_validate_critical: bool = True
    ):
        self.on_validate = on_validate or (lambda step: step.confidence > 0.9)
        self.on_reset = on_reset or (lambda step: step.retries < 3)
        self.auto_validate_critical = auto_validate_critical
    
    def should_validate(self, step: ReasoningStep) -> bool:
        """Determine if a step should be validated."""
        return self.on_validate(step)
    
    def should_reset(self, step: ReasoningStep) -> bool:
        """Determine if a step should be reset/retried."""
        return self.on_reset(step)


def reason_step(
    agent: Any,
    thought: str,
    action: str,
    min_confidence: float = 0.7
) -> ReasoningStep:
    """
    Create a reasoning step with confidence validation.
    
    Args:
        agent: The agent performing the reasoning
        thought: The reasoning thought/analysis
        action: The action or conclusion from the thought
        min_confidence: Minimum confidence required
        
    Returns:
        ReasoningStep with confidence scoring
    """
    # Simulate confidence calculation (in real implementation, this could use LLM)
    confidence = min(0.95, len(action) / 100.0 + 0.5)  # Simple heuristic
    
    step = ReasoningStep(
        step_number=len(getattr(agent, 'reasoning_trace', {}).get('steps', [])) + 1,
        title=f"Step {len(getattr(agent, 'reasoning_trace', {}).get('steps', [])) + 1}",
        thought=thought,
        action=action,
        confidence=confidence
    )
    
    # Validate confidence
    if confidence < min_confidence:
        step.action_state = ActionState.RESET
        
    return step