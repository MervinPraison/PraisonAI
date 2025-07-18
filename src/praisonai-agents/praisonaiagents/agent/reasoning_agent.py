"""
ReasoningAgent - An enhanced agent with built-in reasoning capabilities.

This agent extends the base Agent class with advanced reasoning features including:
- Configurable reasoning parameters
- Step-by-step reasoning with confidence scoring
- Flow control with action states
- Reasoning trace tracking
"""

from typing import List, Optional, Any, Dict, Union, Literal, TYPE_CHECKING
from ..agent import Agent
from ..reasoning import (
    ReasoningConfig, 
    ReasoningTrace, 
    ReasoningStep, 
    ActionState,
    ReasoningFlow,
    reason_step
)
import time

if TYPE_CHECKING:
    from ..task.task import Task


class ReasoningAgent(Agent):
    """
    Enhanced agent with built-in reasoning capabilities.
    
    This agent provides step-by-step reasoning with configurable parameters,
    confidence scoring, and reasoning trace tracking.
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        role: Optional[str] = None,
        goal: Optional[str] = None,
        backstory: Optional[str] = None,
        instructions: Optional[str] = None,
        reasoning: bool = True,
        reasoning_config: Optional[Union[ReasoningConfig, Dict[str, Any]]] = None,
        min_confidence: float = 0.7,
        reasoning_flow: Optional[ReasoningFlow] = None,
        **kwargs
    ):
        """
        Initialize a ReasoningAgent.
        
        Args:
            name: Agent name
            role: Agent role  
            goal: Agent goal
            backstory: Agent backstory
            instructions: Direct instructions
            reasoning: Enable reasoning (always True for ReasoningAgent)
            reasoning_config: Reasoning configuration
            min_confidence: Minimum confidence threshold
            reasoning_flow: Flow control configuration
            **kwargs: Additional Agent parameters
        """
        # Force reasoning to be enabled
        kwargs['reasoning_steps'] = True
        kwargs['self_reflect'] = kwargs.get('self_reflect', True)
        
        super().__init__(
            name=name,
            role=role,
            goal=goal,
            backstory=backstory,
            instructions=instructions,
            **kwargs
        )
        
        # Initialize reasoning configuration
        if isinstance(reasoning_config, dict):
            self.reasoning_config = ReasoningConfig(**reasoning_config)
        elif reasoning_config is None:
            self.reasoning_config = ReasoningConfig()
        else:
            self.reasoning_config = reasoning_config
            
        self.min_confidence = min_confidence
        self.reasoning_flow = reasoning_flow or ReasoningFlow()
        self.reasoning_trace: Optional[ReasoningTrace] = None
        self.last_reasoning_steps: List[ReasoningStep] = []
        
        # Update instructions to include reasoning guidance
        self._enhance_instructions_for_reasoning()
    
    def _enhance_instructions_for_reasoning(self):
        """Enhance agent instructions with reasoning guidance."""
        reasoning_guidance = f"""
        
REASONING INSTRUCTIONS:
- Use step-by-step reasoning for all complex problems
- Show your thinking process explicitly
- Assess confidence for each reasoning step (0.0-1.0)
- Minimum {self.reasoning_config.min_steps} steps, maximum {self.reasoning_config.max_steps} steps
- Reasoning style: {self.reasoning_config.style}
- Minimum confidence threshold: {self.min_confidence}
        """
        
        if self.instructions:
            self.instructions += reasoning_guidance
        else:
            base_instructions = f"You are {self.role or 'an assistant'}"
            if self.goal:
                base_instructions += f" with the goal: {self.goal}"
            self.instructions = base_instructions + reasoning_guidance
    
    def start_reasoning_trace(self, problem: str) -> ReasoningTrace:
        """Start a new reasoning trace for a problem."""
        self.reasoning_trace = ReasoningTrace(problem=problem)
        self.last_reasoning_steps = []
        return self.reasoning_trace
    
    def add_reasoning_step(
        self, 
        thought: str, 
        action: str, 
        confidence: Optional[float] = None
    ) -> ReasoningStep:
        """Add a reasoning step to the current trace."""
        if not self.reasoning_trace:
            self.start_reasoning_trace("Current problem")
        
        # Calculate confidence if not provided
        if confidence is None:
            confidence = min(0.95, len(action) / 100.0 + 0.6)
        
        step = ReasoningStep(
            step_number=len(self.reasoning_trace.steps) + 1,
            title=f"Step {len(self.reasoning_trace.steps) + 1}",
            thought=thought,
            action=action,
            confidence=confidence
        )
        
        # Apply flow control
        if confidence < self.min_confidence:
            step.action_state = ActionState.RESET
        elif self.reasoning_flow.should_validate(step):
            step.action_state = ActionState.VALIDATE
        
        self.reasoning_trace.steps.append(step)
        self.last_reasoning_steps.append(step)
        
        return step
    
    def complete_reasoning_trace(self, final_answer: str) -> ReasoningTrace:
        """Complete the current reasoning trace."""
        if not self.reasoning_trace:
            return None
            
        self.reasoning_trace.final_answer = final_answer
        self.reasoning_trace.completed_at = time.time()
        self.reasoning_trace.total_time = (
            self.reasoning_trace.completed_at - self.reasoning_trace.started_at
        )
        
        # Calculate overall confidence as average of step confidences
        if self.reasoning_trace.steps:
            self.reasoning_trace.overall_confidence = sum(
                step.confidence for step in self.reasoning_trace.steps
            ) / len(self.reasoning_trace.steps)
        
        return self.reasoning_trace
    
    def chat(
        self, 
        message: str,
        **kwargs
    ) -> str:
        """
        Enhanced chat method with reasoning capabilities.
        
        Args:
            message: Input message
            **kwargs: Additional chat parameters
            
        Returns:
            Response with reasoning trace
        """
        # Start reasoning trace
        self.start_reasoning_trace(message)
        
        # Enhance message with reasoning instructions
        enhanced_message = f"""
{message}

Please solve this step-by-step using the following reasoning process:
1. Break down the problem into logical steps
2. For each step, show your thought process
3. State your confidence level (0.0-1.0) for each step
4. Ensure minimum {self.reasoning_config.min_steps} reasoning steps
5. Use {self.reasoning_config.style} reasoning style
6. Provide a clear final answer

Format your response to show each reasoning step clearly.
        """
        
        # Call parent chat method
        response = super().chat(enhanced_message, **kwargs)
        
        # Complete reasoning trace
        self.complete_reasoning_trace(response)
        
        return response
    
    def execute(self, task: 'Task', **kwargs) -> Any:
        """
        Enhanced execute method with reasoning capabilities.
        
        Args:
            task: Task to execute
            **kwargs: Additional execution parameters
            
        Returns:
            Task result with reasoning trace
        """
        # Start reasoning trace for the task
        self.start_reasoning_trace(task.description)
        
        # Execute the task
        result = super().execute(task, **kwargs)
        
        # Complete reasoning trace
        if hasattr(result, 'raw'):
            self.complete_reasoning_trace(result.raw)
        else:
            self.complete_reasoning_trace(str(result))
        
        return result
    
    def get_reasoning_summary(self) -> Dict[str, Any]:
        """Get a summary of the last reasoning process."""
        if not self.reasoning_trace:
            return {"status": "No reasoning trace available"}
        
        return {
            "problem": self.reasoning_trace.problem,
            "total_steps": len(self.reasoning_trace.steps),
            "overall_confidence": self.reasoning_trace.overall_confidence,
            "total_time": self.reasoning_trace.total_time,
            "final_answer": self.reasoning_trace.final_answer,
            "steps_summary": [
                {
                    "step": step.step_number,
                    "confidence": step.confidence,
                    "action_state": step.action_state.value
                }
                for step in self.reasoning_trace.steps
            ]
        }