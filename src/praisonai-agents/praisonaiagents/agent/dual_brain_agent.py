"""
DualBrainAgent - An agent with separate LLMs for conversation and reasoning.

This agent extends the base Agent class with dual LLM capabilities:
- Main LLM for conversational responses
- Separate reasoning LLM for analytical thinking
- Configurable models for different purposes
- Reasoning coordination between the two models
"""

from typing import List, Optional, Any, Dict, Union, Literal, TYPE_CHECKING
from ..agent import Agent
from ..reasoning import (
    ReasoningConfig, 
    ReasoningTrace, 
    ReasoningStep, 
    ActionState,
    ReasoningFlow
)
import time

if TYPE_CHECKING:
    from ..task.task import Task


class DualBrainAgent(Agent):
    """
    Agent with separate LLMs for conversation and reasoning.
    
    This agent uses two different language models:
    - Main LLM for conversational interaction and response generation
    - Reasoning LLM for analytical thinking and problem decomposition
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        role: Optional[str] = None,
        goal: Optional[str] = None,
        backstory: Optional[str] = None,
        instructions: Optional[str] = None,
        llm: Optional[Union[str, Any]] = None,
        reasoning_llm: Optional[Union[str, Any]] = None,
        reasoning: bool = True,
        reasoning_config: Optional[Union[ReasoningConfig, Dict[str, Any]]] = None,
        llm_config: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """
        Initialize a DualBrainAgent.
        
        Args:
            name: Agent name
            role: Agent role
            goal: Agent goal
            backstory: Agent backstory
            instructions: Direct instructions
            llm: Main conversational model (e.g., "gpt-4-turbo")
            reasoning_llm: Analytical reasoning model (e.g., "o1-preview")
            reasoning: Enable reasoning capabilities
            reasoning_config: Reasoning configuration or dict
            llm_config: Configuration for main LLM
            **kwargs: Additional Agent parameters
        """
        # Set up main LLM
        if llm_config and isinstance(llm_config, dict):
            main_llm = llm_config.get('model', llm)
            # Apply LLM config parameters as needed
        else:
            main_llm = llm or "gpt-4o"
        
        # Force reasoning to be enabled and set reflect_llm
        kwargs['reasoning_steps'] = True
        kwargs['self_reflect'] = kwargs.get('self_reflect', True)
        kwargs['reflect_llm'] = reasoning_llm or "o1-preview"
        
        super().__init__(
            name=name,
            role=role,
            goal=goal,
            backstory=backstory,
            instructions=instructions,
            llm=main_llm,
            **kwargs
        )
        
        # Set up reasoning LLM
        self.reasoning_llm = reasoning_llm or "o1-preview"
        self.main_llm = main_llm
        
        # Initialize reasoning configuration
        if isinstance(reasoning_config, dict):
            self.reasoning_config = ReasoningConfig(**reasoning_config)
        elif reasoning_config is None:
            self.reasoning_config = ReasoningConfig()
        else:
            self.reasoning_config = reasoning_config
        
        # Store LLM configurations
        self.llm_config = llm_config or {}
        self.reasoning_llm_config = {
            "model": self.reasoning_llm,
            "temperature": 0.1,
            "system_prompt": "You are a step-by-step analytical reasoner"
        }
        
        # Update reasoning LLM config if provided in reasoning_config
        if isinstance(reasoning_config, dict) and 'model' in reasoning_config:
            self.reasoning_llm_config.update(reasoning_config)
        
        self.reasoning_trace: Optional[ReasoningTrace] = None
        self.last_reasoning_steps: List[ReasoningStep] = []
        
        # Update instructions to include dual-brain guidance
        self._enhance_instructions_for_dual_brain()
    
    def _enhance_instructions_for_dual_brain(self):
        """Enhance agent instructions with dual-brain guidance."""
        dual_brain_guidance = f"""

DUAL-BRAIN INSTRUCTIONS:
- You have access to two specialized models:
  * Main LLM ({self.main_llm}): For conversational responses and final output
  * Reasoning LLM ({self.reasoning_llm}): For analytical reasoning and problem decomposition
- Use the reasoning LLM for complex analysis, then generate responses with the main LLM
- Coordinate between both models for optimal problem-solving
- Show the reasoning process from the analytical model in your final response
        """
        
        if self.instructions:
            self.instructions += dual_brain_guidance
        else:
            base_instructions = f"You are {self.role or 'an assistant'}"
            if self.goal:
                base_instructions += f" with the goal: {self.goal}"
            self.instructions = base_instructions + dual_brain_guidance
    
    def _reason_with_analytical_brain(self, problem: str) -> str:
        """
        Use the reasoning LLM for analytical thinking.
        
        Args:
            problem: Problem to analyze
            
        Returns:
            Analytical reasoning result
        """
        reasoning_prompt = f"""
You are an analytical reasoning specialist. Break down this problem step-by-step:

Problem: {problem}

Please provide:
1. Problem decomposition
2. Step-by-step analysis
3. Key insights and conclusions
4. Confidence assessment for each step
5. Reasoning strategy used

Format your response clearly with numbered steps and confidence scores.
        """
        
        # Store original LLM temporarily
        original_llm = self.llm
        
        try:
            # Switch to reasoning LLM
            self.llm = self.reasoning_llm
            
            # Use parent chat method with reasoning LLM
            reasoning_result = super().chat(reasoning_prompt)
            
            return reasoning_result
            
        finally:
            # Restore original LLM
            self.llm = original_llm
    
    def _generate_response_with_main_brain(
        self, 
        original_query: str, 
        reasoning_analysis: str
    ) -> str:
        """
        Use the main LLM to generate the final conversational response.
        
        Args:
            original_query: Original user query
            reasoning_analysis: Analysis from reasoning LLM
            
        Returns:
            Final conversational response
        """
        response_prompt = f"""
Based on the analytical reasoning provided, generate a clear and helpful response to the user's query.

Original Query: {original_query}

Analytical Reasoning:
{reasoning_analysis}

Please provide a comprehensive response that:
1. Addresses the user's query directly
2. Incorporates insights from the analytical reasoning
3. Is clear and conversational
4. Shows confidence in the conclusions
5. Acknowledges any reasoning steps taken

Format your response naturally while incorporating the analytical insights.
        """
        
        # Use main LLM for response generation
        return super().chat(response_prompt)
    
    def chat(
        self, 
        message: str,
        **kwargs
    ) -> str:
        """
        Enhanced chat method using dual-brain approach.
        
        Args:
            message: Input message
            **kwargs: Additional chat parameters
            
        Returns:
            Response coordinated between both LLMs
        """
        # Start reasoning trace
        self.reasoning_trace = ReasoningTrace(problem=message, started_at=time.time())
        
        # Step 1: Use reasoning LLM for analysis
        reasoning_analysis = self._reason_with_analytical_brain(message)
        
        # Add reasoning step
        reasoning_step = ReasoningStep(
            step_number=1,
            title="Analytical Brain Reasoning",
            thought=f"Using {self.reasoning_llm} for analytical thinking",
            action=reasoning_analysis,
            confidence=0.9  # High confidence in reasoning LLM analysis
        )
        self.reasoning_trace.steps.append(reasoning_step)
        self.last_reasoning_steps.append(reasoning_step)
        
        # Step 2: Use main LLM for response generation
        final_response = self._generate_response_with_main_brain(message, reasoning_analysis)
        
        # Add response generation step
        response_step = ReasoningStep(
            step_number=2,
            title="Main Brain Response Generation",
            thought=f"Using {self.main_llm} for conversational response",
            action=final_response,
            confidence=0.85
        )
        self.reasoning_trace.steps.append(response_step)
        self.last_reasoning_steps.append(response_step)
        
        # Complete reasoning trace
        self.reasoning_trace.final_answer = final_response
        self.reasoning_trace.completed_at = time.time()
        self.reasoning_trace.total_time = (
            self.reasoning_trace.completed_at - self.reasoning_trace.started_at
        )
        self.reasoning_trace.overall_confidence = sum(
            step.confidence for step in self.reasoning_trace.steps
        ) / len(self.reasoning_trace.steps)
        
        return final_response
    
    def execute(self, task: 'Task', **kwargs) -> Any:
        """
        Enhanced execute method using dual-brain approach.
        
        Args:
            task: Task to execute
            **kwargs: Additional execution parameters
            
        Returns:
            Task result with dual-brain processing
        """
        # Start reasoning trace for the task
        self.reasoning_trace = ReasoningTrace(
            problem=task.description, 
            started_at=time.time()
        )
        
        # Use reasoning LLM for task analysis
        task_analysis = self._reason_with_analytical_brain(task.description)
        
        # Create enhanced task description
        enhanced_description = f"""
{task.description}

Analytical Insights:
{task_analysis}

Please use these insights to complete the task effectively.
        """
        
        # Store original task description
        original_description = task.description
        task.description = enhanced_description
        
        try:
            # Execute the task with main LLM
            result = super().execute(task, **kwargs)
            
            # Complete reasoning trace
            if hasattr(result, 'raw'):
                self.reasoning_trace.final_answer = result.raw
            else:
                self.reasoning_trace.final_answer = str(result)
            
            self.reasoning_trace.completed_at = time.time()
            self.reasoning_trace.total_time = (
                self.reasoning_trace.completed_at - self.reasoning_trace.started_at
            )
            
            return result
            
        finally:
            # Restore original task description
            task.description = original_description
    
    def get_brain_status(self) -> Dict[str, Any]:
        """Get status of both brain models."""
        return {
            "main_llm": {
                "model": self.main_llm,
                "config": self.llm_config,
                "purpose": "Conversational responses and final output generation"
            },
            "reasoning_llm": {
                "model": self.reasoning_llm,
                "config": self.reasoning_llm_config,
                "purpose": "Analytical reasoning and problem decomposition"
            },
            "last_reasoning_steps": len(self.last_reasoning_steps),
            "reasoning_config": self.reasoning_config.model_dump() if self.reasoning_config else None
        }
    
    def switch_reasoning_llm(self, new_reasoning_llm: str, config: Optional[Dict[str, Any]] = None):
        """
        Switch the reasoning LLM to a different model.
        
        Args:
            new_reasoning_llm: New reasoning model name
            config: Optional configuration for the new model
        """
        self.reasoning_llm = new_reasoning_llm
        self.reflect_llm = new_reasoning_llm  # Update reflect_llm as well
        
        if config:
            self.reasoning_llm_config.update(config)
        else:
            self.reasoning_llm_config["model"] = new_reasoning_llm
    
    def switch_main_llm(self, new_main_llm: str, config: Optional[Dict[str, Any]] = None):
        """
        Switch the main LLM to a different model.
        
        Args:
            new_main_llm: New main model name
            config: Optional configuration for the new model
        """
        self.main_llm = new_main_llm
        self.llm = new_main_llm
        
        if config:
            self.llm_config.update(config)