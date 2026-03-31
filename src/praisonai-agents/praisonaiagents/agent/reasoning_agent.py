"""ReasoningAgent - Agent with built-in step-by-step reasoning capabilities.

Extends the base Agent class with reasoning trace lifecycle management,
configurable reasoning parameters, and confidence scoring integration.

Following AGENTS.md:
- Inherits from existing Agent class for backward compatibility
- Uses lazy imports for performance
- Protocol-driven design
- Centralized logging
"""

from typing import Optional, List, Dict, Any, Union
from datetime import datetime
import uuid

from praisonaiagents._logging import get_logger
from praisonaiagents.reasoning import (
    ReasoningConfig, ReasoningStep, ReasoningTrace, ReasoningFlow, ActionState
)

logger = get_logger(__name__)


class ReasoningAgent:
    """Agent class with built-in reasoning capabilities.
    
    Provides step-by-step reasoning, confidence scoring, and reasoning trace tracking
    while maintaining full backward compatibility with the base Agent API.
    """
    
    def __init__(
        self,
        reasoning: bool = True,  # Parameter for signature compatibility  
        reasoning_config: Optional[Union[ReasoningConfig, Dict[str, Any]]] = None,
        reasoning_flow: Optional[Union[ReasoningFlow, Dict[str, Any]]] = None,
        **kwargs
    ):
        """Initialize ReasoningAgent with reasoning capabilities.
        
        Args:
            reasoning: Enable reasoning (kept for API compatibility)
            reasoning_config: Configuration for reasoning behavior
            reasoning_flow: Flow control configuration
            **kwargs: Additional arguments passed to base Agent
        """
        # Import Agent lazily to avoid circular imports
        from praisonaiagents.agent.agent import Agent
        
        # Enable reflection for reasoning capabilities
        if 'reflection' not in kwargs:
            kwargs['reflection'] = True
        if 'planning' not in kwargs:
            kwargs['planning'] = True
        
        # Create base agent instance
        self._base_agent = Agent(**kwargs)
        
        # Copy key attributes for compatibility
        self.name = getattr(self._base_agent, 'name', 'ReasoningAgent')
        self.instructions = getattr(self._base_agent, 'instructions', '')
        self.llm = getattr(self._base_agent, 'llm', 'gpt-4o-mini')
        
        # Initialize reasoning configuration
        if isinstance(reasoning_config, dict):
            self.reasoning_config = ReasoningConfig(**reasoning_config)
        elif reasoning_config is None:
            self.reasoning_config = ReasoningConfig()
        else:
            self.reasoning_config = reasoning_config
        
        # Initialize reasoning flow
        if isinstance(reasoning_flow, dict):
            self.reasoning_flow = ReasoningFlow(**reasoning_flow)
        elif reasoning_flow is None:
            self.reasoning_flow = ReasoningFlow()
        else:
            self.reasoning_flow = reasoning_flow
        
        # Initialize reasoning state
        self.reasoning_trace: Optional[ReasoningTrace] = None
        self.last_reasoning_steps: List[ReasoningStep] = []
        
        # Enhance instructions for reasoning
        self._enhance_instructions_for_reasoning()
        
        logger.debug(f"Initialized ReasoningAgent with config: {self.reasoning_config}")
    
    def _enhance_instructions_for_reasoning(self) -> None:
        """Enhance agent instructions to include reasoning guidance."""
        thought_instruction = (
            "Show your thinking process explicitly"
            if self.reasoning_config.show_internal_thoughts
            else "Keep internal reasoning hidden; provide concise answers."
        )
        
        reasoning_guidance = f"""

REASONING INSTRUCTIONS:
- Use step-by-step reasoning for all complex problems
- {thought_instruction}
- Assess confidence for each reasoning step (0.0-1.0)
- Minimum {self.reasoning_config.min_steps} steps, maximum {self.reasoning_config.max_steps} steps
- Use {self.reasoning_config.style} reasoning style
- Maintain confidence above {self.reasoning_config.min_confidence}

"""
        
        if hasattr(self, 'instructions') and self.instructions:
            self.instructions += reasoning_guidance
        elif hasattr(self, 'role') and self.role:
            self.instructions = self.role + reasoning_guidance
        else:
            self.instructions = reasoning_guidance.strip()
    
    def start_reasoning_trace(self, task_description: str) -> str:
        """Start a new reasoning trace for a task.
        
        Args:
            task_description: Description of the task to reason about
            
        Returns:
            str: Unique task ID for the reasoning trace
        """
        task_id = str(uuid.uuid4())
        self.reasoning_trace = ReasoningTrace(
            task_id=task_id,
            meta={"task_description": task_description}
        )
        self.last_reasoning_steps.clear()
        
        logger.debug(f"Started reasoning trace for task: {task_id}")
        return task_id
    
    def add_reasoning_step(self, step: ReasoningStep) -> None:
        """Add a reasoning step to the current trace.
        
        Args:
            step: ReasoningStep to add to the trace
        """
        if self.reasoning_trace is None:
            # Auto-start trace if not already started
            self.start_reasoning_trace("Auto-started reasoning")
        
        self.reasoning_trace.steps.append(step)
        self.last_reasoning_steps.append(step)
        
        # Update overall confidence (running average)
        if self.reasoning_trace.steps:
            total_confidence = sum(s.confidence for s in self.reasoning_trace.steps)
            self.reasoning_trace.overall_confidence = total_confidence / len(self.reasoning_trace.steps)
        
        logger.debug(f"Added reasoning step {step.step_number}, overall confidence: {self.reasoning_trace.overall_confidence}")
    
    def complete_reasoning_trace(self, final_answer: str) -> ReasoningTrace:
        """Complete the current reasoning trace with a final answer.
        
        Args:
            final_answer: The final answer after reasoning
            
        Returns:
            ReasoningTrace: The completed reasoning trace
        """
        if self.reasoning_trace is None:
            logger.warning("No active reasoning trace to complete")
            return None
        
        self.reasoning_trace.final_answer = final_answer or ""
        self.reasoning_trace.end_time = datetime.now()
        
        logger.debug(f"Completed reasoning trace with {len(self.reasoning_trace.steps)} steps")
        return self.reasoning_trace
    
    def chat(self, message: str, **kwargs) -> str:
        """Chat with step-by-step reasoning enabled.
        
        Args:
            message: User message
            **kwargs: Additional chat parameters
            
        Returns:
            str: Agent response with reasoning applied
        """
        # Start reasoning trace
        task_id = self.start_reasoning_trace(message)
        
        try:
            # Get response from base agent with enhanced reasoning instructions
            response = self._base_agent.chat(message, **kwargs)
            
            # Complete reasoning trace
            self.complete_reasoning_trace(response or "No response generated")
            
            return response
            
        except Exception as e:
            logger.error(f"Error in reasoning chat: {e}")
            # Still complete the trace on error
            self.complete_reasoning_trace(f"Error occurred: {str(e)}")
            raise
    
    def execute(self, task_description: str = None, **kwargs) -> str:
        """Execute a task with reasoning enabled.
        
        Args:
            task_description: Description of the task to execute
            **kwargs: Additional execution parameters
            
        Returns:
            str: Task execution result
        """
        # Start reasoning trace for task execution
        description = task_description or "Task execution"
        task_id = self.start_reasoning_trace(description)
        
        try:
            # Execute with base agent
            if hasattr(self._base_agent, 'execute'):
                result = self._base_agent.execute(task_description, **kwargs)
            else:
                # Fallback to chat if execute not available
                result = self._base_agent.chat(description, **kwargs)
            
            # Complete reasoning trace
            self.complete_reasoning_trace(result or "No result generated")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in reasoning execute: {e}")
            self.complete_reasoning_trace(f"Error occurred: {str(e)}")
            raise
    
    def get_reasoning_summary(self) -> Dict[str, Any]:
        """Get a summary of the current reasoning state.
        
        Returns:
            dict: Summary of reasoning trace and statistics
        """
        if self.reasoning_trace is None:
            return {"status": "no_trace", "steps": 0}
        
        return {
            "task_id": self.reasoning_trace.task_id,
            "steps": len(self.reasoning_trace.steps),
            "overall_confidence": self.reasoning_trace.overall_confidence,
            "status": "completed" if self.reasoning_trace.end_time else "in_progress",
            "duration_seconds": (
                (self.reasoning_trace.end_time or datetime.now()) - 
                self.reasoning_trace.start_time
            ).total_seconds() if self.reasoning_trace.start_time else 0
        }