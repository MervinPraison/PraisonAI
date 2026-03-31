"""Reasoning module for advanced AI agent reasoning capabilities.

This module provides step-by-step reasoning, confidence scoring, and flow control
for agents requiring structured analytical thinking.

Following AGENTS.md:
- Protocol-driven design with XProtocol naming
- Lazy imports for performance
- Centralized logging
- Agent-centric patterns
"""

from typing import List, Optional, Dict, Any, Union
from enum import Enum
from datetime import datetime

try:
    from pydantic import BaseModel, Field
except ImportError:
    # Fallback for environments without pydantic
    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
    
    def Field(**kwargs):
        return kwargs.get('default', None)
from praisonaiagents._logging import get_logger

logger = get_logger(__name__)


class ActionState(Enum):
    """Flow control states for reasoning steps."""
    CONTINUE = "continue"
    VALIDATE = "validate"
    RESET = "reset"
    FINAL_ANSWER = "final_answer"


class ReasoningConfig(BaseModel):
    """Configuration for reasoning capabilities."""
    min_steps: int = Field(default=2, ge=1, description="Minimum reasoning steps required")
    max_steps: int = Field(default=10, ge=1, description="Maximum reasoning steps allowed")
    style: str = Field(default="analytical", description="Reasoning style: analytical, creative, systematic")
    min_confidence: float = Field(default=0.7, ge=0.0, le=1.0, description="Minimum confidence threshold")
    show_internal_thoughts: bool = Field(default=True, description="Whether to show reasoning process")
    temperature: float = Field(default=0.1, ge=0.0, le=2.0, description="Temperature for reasoning LLM")
    system_prompt: Optional[str] = Field(default=None, description="Custom system prompt for reasoning")


class ReasoningStep(BaseModel):
    """Individual reasoning step with confidence scoring."""
    step_number: int = Field(description="Step number in the reasoning process")
    title: str = Field(description="Brief title for this step")
    thought: str = Field(description="Internal thought process")
    action: str = Field(description="Action taken in this step")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence level for this step")
    timestamp: datetime = Field(default_factory=datetime.now)
    state: ActionState = Field(default=ActionState.CONTINUE, description="Flow control state")


class ReasoningTrace(BaseModel):
    """Complete reasoning trace for a task."""
    task_id: str = Field(description="Unique identifier for the task")
    steps: List[ReasoningStep] = Field(default_factory=list, description="List of reasoning steps")
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Overall confidence score")
    final_answer: str = Field(default="", description="Final answer after reasoning")
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: Optional[datetime] = Field(default=None)
    meta: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ReasoningFlow(BaseModel):
    """Flow control configuration for reasoning process."""
    on_validate: Optional[str] = Field(default=None, description="Validation callback function")
    on_reset: Optional[str] = Field(default=None, description="Reset callback function") 
    auto_validate_critical: bool = Field(default=True, description="Auto-validate critical steps")
    max_retries: int = Field(default=3, description="Maximum retries for failed steps")


def reason_step(
    agent: Any,
    thought: str,
    action: str,
    confidence: Optional[float] = None,
    state: ActionState = ActionState.CONTINUE
) -> ReasoningStep:
    """Create a reasoning step and add it to the agent's trace.
    
    Args:
        agent: Agent instance with reasoning capabilities
        thought: Internal thought process for this step
        action: Action taken in this step
        confidence: Confidence level (0.0-1.0), auto-calculated if None
        state: Flow control state for this step
        
    Returns:
        ReasoningStep: The created reasoning step
    """
    # Get current step number from agent's trace
    trace = getattr(agent, 'reasoning_trace', None)
    if trace is None:
        steps = []
    elif hasattr(trace, 'steps'):
        steps = trace.steps
    elif isinstance(trace, dict):
        steps = trace.get('steps', [])
    else:
        steps = []
    
    step_number = len(steps) + 1
    
    # Auto-calculate confidence if not provided
    if confidence is None:
        # Use a simple heuristic based on step complexity and agent history
        confidence = min(0.8, 0.5 + (0.1 * len(action.split())))
    
    step = ReasoningStep(
        step_number=step_number,
        title=f"Step {step_number}",
        thought=thought,
        action=action,
        confidence=confidence,
        state=state
    )
    
    # Add step to agent's trace if it has reasoning capabilities
    if hasattr(agent, 'add_reasoning_step'):
        agent.add_reasoning_step(step)
    
    logger.debug(f"Created reasoning step {step_number} with confidence {confidence}")
    return step