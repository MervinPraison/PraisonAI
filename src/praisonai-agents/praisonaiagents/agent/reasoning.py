"""
Reasoning configuration and support classes for PraisonAI Agents.

This module provides configuration classes and utilities for enhanced reasoning
capabilities in agents, including step-by-step reasoning, confidence scoring,
and reasoning flow control.
"""

from typing import Dict, Optional, Any, Literal, Callable, List
from dataclasses import dataclass, field
from enum import Enum
import uuid
import time
import logging

logger = logging.getLogger(__name__)


class ActionState(Enum):
    """Action states for reasoning flow control."""
    CONTINUE = "continue"
    VALIDATE = "validate"
    RESET = "reset"
    FINAL_ANSWER = "final_answer"


@dataclass
class ReasoningStep:
    """Represents a single step in the reasoning process."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str = ""
    action: str = ""
    thought: str = ""
    confidence: float = 0.0
    timestamp: float = field(default_factory=time.time)
    retries: int = 0
    validation_passed: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReasoningConfig:
    """Configuration for reasoning capabilities."""
    min_steps: int = 2
    max_steps: int = 10
    style: Literal["analytical", "creative", "systematic"] = "analytical"
    confidence_threshold: float = 0.7
    enable_validation: bool = True
    enable_improvement: bool = True
    enable_error_detection: bool = True
    temperature: float = 0.3
    max_retries: int = 3
    validation_model: Optional[str] = None
    system_prompt: Optional[str] = None


@dataclass
class ReasoningFlow:
    """Configuration for reasoning flow control."""
    on_validate: Optional[Callable[[ReasoningStep], bool]] = None
    on_reset: Optional[Callable[[ReasoningStep], bool]] = None
    auto_validate_critical: bool = True
    validation_rules: Dict[str, Callable] = field(default_factory=dict)
    
    def should_validate(self, step: ReasoningStep) -> bool:
        """Determine if a step should be validated."""
        if self.on_validate:
            return self.on_validate(step)
        return step.confidence < 0.9
    
    def should_reset(self, step: ReasoningStep) -> bool:
        """Determine if reasoning should reset."""
        if self.on_reset:
            return self.on_reset(step)
        return step.retries >= 3
    
    def apply_validation_rules(self, step: ReasoningStep) -> bool:
        """Apply custom validation rules to a step."""
        for rule_name, rule_func in self.validation_rules.items():
            try:
                if not rule_func(step):
                    logger.debug(f"Validation rule '{rule_name}' failed for step {step.id}")
                    return False
            except Exception as e:
                logger.warning(f"Validation rule '{rule_name}' raised exception: {e}")
                return False
        return True


class ReasoningEngine:
    """Core reasoning engine that orchestrates the reasoning process."""
    
    def __init__(self, config: ReasoningConfig, flow: Optional[ReasoningFlow] = None):
        self.config = config
        self.flow = flow or ReasoningFlow()
        self.reasoning_steps: List[ReasoningStep] = []
        self.current_step = 0
        
    def create_step(self, title: str, action: str, thought: str = "", confidence: float = 0.0) -> ReasoningStep:
        """Create a new reasoning step."""
        step = ReasoningStep(
            title=title,
            action=action,
            thought=thought,
            confidence=confidence
        )
        self.reasoning_steps.append(step)
        return step
    
    def update_step(self, step_id: str, **kwargs) -> bool:
        """Update an existing reasoning step."""
        for step in self.reasoning_steps:
            if step.id == step_id:
                for key, value in kwargs.items():
                    if hasattr(step, key):
                        setattr(step, key, value)
                return True
        return False
    
    def get_step(self, step_id: str) -> Optional[ReasoningStep]:
        """Get a reasoning step by ID."""
        for step in self.reasoning_steps:
            if step.id == step_id:
                return step
        return None
    
    def validate_step(self, step: ReasoningStep) -> bool:
        """Validate a reasoning step."""
        if not self.config.enable_validation:
            return True
            
        # Check confidence threshold
        if step.confidence < self.config.confidence_threshold:
            logger.debug(f"Step {step.id} failed confidence threshold: {step.confidence} < {self.config.confidence_threshold}")
            return False
        
        # Apply flow validation rules
        if not self.flow.apply_validation_rules(step):
            return False
        
        step.validation_passed = True
        return True
    
    def should_continue(self) -> ActionState:
        """Determine the next action based on current reasoning state."""
        if len(self.reasoning_steps) < self.config.min_steps:
            return ActionState.CONTINUE
            
        if len(self.reasoning_steps) >= self.config.max_steps:
            return ActionState.FINAL_ANSWER
            
        last_step = self.reasoning_steps[-1] if self.reasoning_steps else None
        if last_step:
            if self.flow.should_reset(last_step):
                return ActionState.RESET
            elif self.flow.should_validate(last_step):
                return ActionState.VALIDATE
                
        return ActionState.CONTINUE
    
    def get_reasoning_trace(self) -> List[Dict[str, Any]]:
        """Get the full reasoning trace as a serializable format."""
        return [
            {
                "id": step.id,
                "title": step.title,
                "action": step.action,
                "thought": step.thought,
                "confidence": step.confidence,
                "timestamp": step.timestamp,
                "retries": step.retries,
                "validation_passed": step.validation_passed,
                "metadata": step.metadata
            }
            for step in self.reasoning_steps
        ]
    
    def reset(self):
        """Reset the reasoning engine."""
        self.reasoning_steps.clear()
        self.current_step = 0
    
    def get_reasoning_summary(self) -> Dict[str, Any]:
        """Get a summary of the reasoning process."""
        if not self.reasoning_steps:
            return {
                "total_steps": 0,
                "avg_confidence": 0.0,
                "total_retries": 0,
                "validation_rate": 0.0
            }
        
        total_confidence = sum(step.confidence for step in self.reasoning_steps)
        total_retries = sum(step.retries for step in self.reasoning_steps)
        validated_steps = sum(1 for step in self.reasoning_steps if step.validation_passed)
        
        return {
            "total_steps": len(self.reasoning_steps),
            "avg_confidence": total_confidence / len(self.reasoning_steps),
            "total_retries": total_retries,
            "validation_rate": validated_steps / len(self.reasoning_steps),
            "min_confidence": min(step.confidence for step in self.reasoning_steps),
            "max_confidence": max(step.confidence for step in self.reasoning_steps)
        }