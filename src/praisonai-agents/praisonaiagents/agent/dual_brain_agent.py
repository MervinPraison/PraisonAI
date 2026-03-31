"""DualBrainAgent - Agent with separate LLMs for conversation and analytical reasoning.

Uses dual-brain architecture with separate models:
- Main LLM for conversational responses  
- Reasoning LLM for analytical breakdown and insights

Following AGENTS.md:
- Inherits from Agent for backward compatibility
- Uses lazy imports for performance
- Protocol-driven design
- Thread-safe LLM switching
- Centralized logging
"""

from typing import Optional, List, Dict, Any, Union, Tuple
from datetime import datetime
import threading
import uuid

from praisonaiagents._logging import get_logger
from praisonaiagents.reasoning import (
    ReasoningConfig, ReasoningStep, ReasoningTrace, ReasoningFlow, ActionState
)

logger = get_logger(__name__)


class DualBrainAgent:
    """Agent with dual-brain architecture using separate LLMs.
    
    Orchestrates two LLMs:
    - Main LLM: Conversational responses and final answers
    - Reasoning LLM: Analytical reasoning and problem breakdown
    """
    
    def __init__(
        self,
        llm: str = "gpt-4o",
        reasoning_llm: str = "o1-preview", 
        llm_config: Optional[Dict[str, Any]] = None,
        reasoning_config: Optional[Union[ReasoningConfig, Dict[str, Any]]] = None,
        reasoning_flow: Optional[Union[ReasoningFlow, Dict[str, Any]]] = None,
        reasoning: bool = True,  # Parameter for signature compatibility
        **kwargs
    ):
        """Initialize DualBrainAgent with dual LLM setup.
        
        Args:
            llm: Main conversational model
            reasoning_llm: Analytical reasoning model  
            llm_config: Configuration for main LLM
            reasoning_config: Configuration for reasoning LLM and behavior
            reasoning_flow: Flow control configuration
            reasoning: Enable reasoning (kept for API compatibility)
            **kwargs: Additional arguments passed to base Agent
        """
        # Import Agent lazily to avoid circular imports
        from praisonaiagents.agent.agent import Agent
        
        # Set up main LLM
        main_llm = llm or "gpt-4o"
        if llm_config and isinstance(llm_config, dict):
            self.main_llm_config = llm_config.copy()
            self.main_llm_config["model"] = main_llm
        else:
            self.main_llm_config = {"model": main_llm}
        
        # Set up reasoning LLM configuration
        self.reasoning_llm = reasoning_llm or "o1-preview"
        self.reasoning_llm_config = {
            "model": self.reasoning_llm,
            "temperature": 0.1,
            "system_prompt": "You are a step-by-step analytical reasoner. Break down complex problems methodically."
        }
        
        # Update reasoning LLM config if provided
        if isinstance(reasoning_config, dict):
            llm_config_keys = {"model", "temperature", "system_prompt"}
            llm_specific_config = {k: v for k, v in reasoning_config.items() if k in llm_config_keys}
            if llm_specific_config:
                self.reasoning_llm_config.update(llm_specific_config)
        
        # Initialize reasoning configuration
        if isinstance(reasoning_config, dict):
            self.reasoning_config = ReasoningConfig(**{k: v for k, v in reasoning_config.items() 
                                                     if k not in {"model", "temperature", "system_prompt"}})
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
        
        # Create base agent with main LLM
        kwargs['llm'] = main_llm
        if 'reflection' not in kwargs:
            kwargs['reflection'] = True
        if 'planning' not in kwargs:
            kwargs['planning'] = True
        
        self._base_agent = Agent(**kwargs)
        
        # Copy key attributes for compatibility
        self.name = getattr(self._base_agent, 'name', 'DualBrainAgent')
        self.instructions = getattr(self._base_agent, 'instructions', '')
        
        # Store references for LLM switching
        self.main_llm = main_llm
        self.llm = main_llm
        self.llm_config = self.main_llm_config
        
        # Initialize reasoning state
        self.reasoning_trace: Optional[ReasoningTrace] = None
        self.last_reasoning_steps: List[ReasoningStep] = []
        
        # Thread safety for LLM switching
        self._llm_lock = threading.Lock()
        
        logger.debug(f"Initialized DualBrainAgent: main={main_llm}, reasoning={self.reasoning_llm}")
    
    def _reason_with_analytical_brain(self, problem: str) -> Tuple[str, float]:
        """Use reasoning LLM for analytical breakdown.
        
        Args:
            problem: Problem to analyze
            
        Returns:
            Tuple of (reasoning_analysis, confidence_score)
        """
        with self._llm_lock:
            # Temporarily switch to reasoning LLM with proper config handling
            original_llm = getattr(self._base_agent, 'llm', None)
            original_config = getattr(self._base_agent, 'llm_config', {})
            
            try:
                # Create a temporary agent instance for reasoning to avoid conflicts
                from praisonaiagents.agent.agent import Agent
                reasoning_agent = Agent(
                    llm=self.reasoning_llm,
                    llm_config=self.reasoning_llm_config,
                    name=f"{self.name}_reasoning_brain" if hasattr(self, 'name') else "reasoning_brain",
                    instructions=self.reasoning_llm_config.get('system_prompt', '')
                )
                
                # Analytical prompt for reasoning LLM
                analysis_prompt = f"""
                Analyze this problem step by step:
                
                Problem: {problem}
                
                Please provide:
                1. Problem decomposition
                2. Key insights and considerations  
                3. Analytical approach
                4. Confidence assessment (0.0-1.0)
                
                Format your response clearly with reasoning steps.
                """
                
                reasoning_analysis = reasoning_agent.chat(analysis_prompt)
                
                # Extract confidence score (simple heuristic)
                confidence = 0.8  # Default confidence
                if "confidence" in reasoning_analysis.lower():
                    # Try to extract confidence score
                    import re
                    confidence_match = re.search(r'confidence[:\s]+([0-9.]+)', reasoning_analysis.lower())
                    if confidence_match:
                        try:
                            confidence = float(confidence_match.group(1))
                            confidence = max(0.0, min(1.0, confidence))
                        except ValueError:
                            confidence = 0.8
                
                return reasoning_analysis, confidence
                
            except Exception as e:
                logger.error(f"Error in analytical reasoning: {e}")
                return f"Analysis error: {str(e)}", 0.3
    
    def _generate_response_with_main_brain(
        self, 
        original_query: str, 
        reasoning_analysis: str,
        **kwargs
    ) -> str:
        """Generate final response using main LLM with reasoning insights.
        
        Args:
            original_query: Original user query
            reasoning_analysis: Analysis from reasoning LLM
            **kwargs: Additional chat parameters
            
        Returns:
            str: Final response from main LLM
        """
        # Construct enhanced prompt with analytical insights
        response_prompt = f"""
        User Query: {original_query}
        
        Analytical Insights:
        {reasoning_analysis}
        
        Based on the analytical breakdown above, provide a helpful and comprehensive response to the user's query.
        Incorporate the key insights while maintaining a natural, conversational tone.
        """
        
        # Use main LLM for final response
        return self._base_agent.chat(response_prompt, **kwargs)
    
    def chat(self, message: str, **kwargs) -> str:
        """Chat with dual-brain reasoning enabled.
        
        Args:
            message: User message
            **kwargs: Additional chat parameters
            
        Returns:
            str: Agent response after dual-brain processing
        """
        # Start reasoning trace
        task_id = str(uuid.uuid4())
        self.reasoning_trace = ReasoningTrace(
            task_id=task_id,
            meta={"original_query": message}
        )
        self.last_reasoning_steps.clear()
        
        try:
            # Step 1: Analytical reasoning with reasoning brain
            reasoning_analysis, confidence = self._reason_with_analytical_brain(message)
            
            # Create reasoning step
            step = ReasoningStep(
                step_number=1,
                title="Analytical Breakdown",
                thought=f"Using reasoning LLM ({self.reasoning_llm}) to analyze the problem",
                action=reasoning_analysis,
                confidence=confidence
            )
            self.reasoning_trace.steps.append(step)
            self.last_reasoning_steps.append(step)
            
            # Step 2: Generate response with main brain
            final_response = self._generate_response_with_main_brain(
                message, reasoning_analysis, **kwargs
            )
            
            # Complete reasoning trace
            self.reasoning_trace.final_answer = final_response or ""
            self.reasoning_trace.end_time = datetime.now()
            if self.reasoning_trace.steps:
                self.reasoning_trace.overall_confidence = sum(
                    step.confidence for step in self.reasoning_trace.steps
                ) / len(self.reasoning_trace.steps)
            else:
                self.reasoning_trace.overall_confidence = 0.0
            
            logger.debug(f"Dual-brain chat completed with confidence {self.reasoning_trace.overall_confidence}")
            return final_response
            
        except Exception as e:
            logger.error(f"Error in dual-brain chat: {e}")
            # Complete trace on error
            self.reasoning_trace.final_answer = f"Error occurred: {str(e)}"
            self.reasoning_trace.end_time = datetime.now()
            raise
    
    def execute(self, task_description: str = None, **kwargs) -> str:
        """Execute a task with dual-brain reasoning.
        
        Args:
            task_description: Description of the task to execute
            **kwargs: Additional execution parameters
            
        Returns:
            str: Task execution result
        """
        # Start reasoning trace for task execution
        description = task_description or "Task execution"
        task_id = str(uuid.uuid4())
        self.reasoning_trace = ReasoningTrace(
            task_id=task_id,
            meta={"task_description": description}
        )
        
        try:
            # Perform analytical reasoning on the task
            reasoning_analysis, confidence = self._reason_with_analytical_brain(description)
            
            # Execute with base agent using reasoning insights
            if hasattr(self._base_agent, 'execute'):
                result = self._base_agent.execute(task_description, **kwargs)
            else:
                # Fallback to chat with enhanced prompt
                enhanced_prompt = f"""
                Task: {description}
                
                Analytical Approach:
                {reasoning_analysis}
                
                Execute this task following the analytical approach above.
                """
                result = self._base_agent.chat(enhanced_prompt, **kwargs)
            
            # Complete reasoning trace
            self.reasoning_trace.final_answer = result or ""
            self.reasoning_trace.end_time = datetime.now()
            
            return result
            
        except Exception as e:
            logger.error(f"Error in dual-brain execute: {e}")
            self.reasoning_trace.final_answer = f"Error occurred: {str(e)}"
            self.reasoning_trace.end_time = datetime.now()
            raise
    
    def switch_reasoning_llm(self, new_reasoning_llm: str, config: Optional[Dict[str, Any]] = None):
        """Switch the reasoning LLM to a different model.
        
        Args:
            new_reasoning_llm: New reasoning model name
            config: Optional configuration for the new model
        """
        self.reasoning_llm = new_reasoning_llm
        self.reflect_llm = new_reasoning_llm  # Update reflect_llm as well
        self.reasoning_llm_config["model"] = new_reasoning_llm
        if config:
            self.reasoning_llm_config.update(config)
        
        logger.debug(f"Switched reasoning LLM to: {new_reasoning_llm}")
    
    def switch_main_llm(self, new_main_llm: str, config: Optional[Dict[str, Any]] = None):
        """Switch the main LLM to a different model.
        
        Args:
            new_main_llm: New main model name
            config: Optional configuration for the new model
        """
        self.main_llm = new_main_llm
        self.llm = new_main_llm
        self.llm_config["model"] = new_main_llm
        if config:
            self.llm_config.update(config)
        
        # Update base agent LLM
        self._base_agent.llm = new_main_llm
        if hasattr(self._base_agent, 'llm_config'):
            self._base_agent.llm_config.update(self.llm_config)
        
        logger.debug(f"Switched main LLM to: {new_main_llm}")
    
    def get_brain_status(self) -> Dict[str, Any]:
        """Get status of both brains and reasoning state.
        
        Returns:
            dict: Status information for dual-brain setup
        """
        return {
            "main_llm": self.main_llm,
            "reasoning_llm": self.reasoning_llm,
            "reasoning_steps": len(self.last_reasoning_steps),
            "overall_confidence": (
                self.reasoning_trace.overall_confidence 
                if self.reasoning_trace else 0.0
            ),
            "active_trace": self.reasoning_trace.task_id if self.reasoning_trace else None
        }