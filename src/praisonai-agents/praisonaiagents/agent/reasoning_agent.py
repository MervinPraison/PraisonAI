"""
ReasoningAgent - Enhanced agent with advanced reasoning capabilities.

This agent extends the base Agent class with structured reasoning, confidence
scoring, and step-by-step problem solving using the existing Chain of Thought
infrastructure.
"""

import logging
from typing import Optional, Dict, Any, Union, List, Callable, Tuple
from .agent import Agent
from .reasoning import ReasoningConfig, ReasoningFlow, ReasoningEngine, ActionState
from ..tools.train.data.generatecot import GenerateCOT

logger = logging.getLogger(__name__)


class ReasoningAgent(Agent):
    """
    Agent with enhanced reasoning capabilities including step-by-step thinking,
    confidence scoring, and reasoning flow control.
    
    Inherits all functionality from the base Agent class while adding:
    - Configurable reasoning steps
    - Confidence-based validation
    - Chain of thought integration
    - Reasoning flow control
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        role: Optional[str] = None,
        goal: Optional[str] = None,
        backstory: Optional[str] = None,
        instructions: Optional[str] = None,
        llm: Optional[Union[str, Any]] = None,
        tools: Optional[List[Any]] = None,
        
        # Reasoning-specific parameters
        reasoning: bool = True,
        reasoning_config: Optional[Union[ReasoningConfig, Dict[str, Any]]] = None,
        reasoning_flow: Optional[ReasoningFlow] = None,
        min_confidence: float = 0.7,
        show_reasoning: bool = True,
        
        # Pass through all other Agent parameters
        **kwargs
    ):
        """
        Initialize a ReasoningAgent.
        
        Args:
            reasoning: Enable reasoning capabilities (default: True)
            reasoning_config: Configuration for reasoning behavior
            reasoning_flow: Flow control for reasoning process
            min_confidence: Minimum confidence threshold for steps
            show_reasoning: Whether to display reasoning steps
            **kwargs: All other parameters passed to base Agent
        """
        
        # Force enable reasoning steps and self-reflection if reasoning is enabled
        if reasoning:
            kwargs.setdefault('reasoning_steps', True)
            kwargs.setdefault('self_reflect', True)
            
        # Initialize base Agent
        super().__init__(
            name=name or "ReasoningAgent",
            role=role,
            goal=goal,
            backstory=backstory,
            instructions=instructions,
            llm=llm,
            tools=tools,
            **kwargs
        )
        
        # Setup reasoning capabilities
        self.reasoning_enabled = reasoning
        self.min_confidence = min_confidence
        self.show_reasoning = show_reasoning
        
        # Initialize reasoning config
        if isinstance(reasoning_config, dict):
            self.reasoning_config = ReasoningConfig(**reasoning_config)
        elif reasoning_config is None:
            self.reasoning_config = ReasoningConfig(
                confidence_threshold=min_confidence,
                style="analytical"
            )
        else:
            self.reasoning_config = reasoning_config
            
        # Initialize reasoning flow
        self.reasoning_flow = reasoning_flow or ReasoningFlow()
        
        # Initialize reasoning engine
        self.reasoning_engine = ReasoningEngine(
            config=self.reasoning_config,
            flow=self.reasoning_flow
        )
        
        # Initialize Chain of Thought generator
        self.cot_generator = None
        if self.reasoning_enabled:
            try:
                self.cot_generator = GenerateCOT(
                    model=self.llm if isinstance(self.llm, str) else "gpt-4o-mini",
                    temperature=self.reasoning_config.temperature,
                    verbose=self.show_reasoning
                )
            except Exception as e:
                logger.warning(f"Could not initialize COT generator: {e}")
        
        # Store reasoning trace
        self.last_reasoning_steps = []
        self.reasoning_trace = []
        
    def chat(
        self,
        message: str,
        temperature: float = 0.1,
        tools: Optional[List[Any]] = None,
        task_name: Optional[str] = None,
        task_description: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> str:
        """
        Enhanced chat method with reasoning capabilities.
        
        Args:
            message: The input message/problem to solve
            temperature: Temperature for LLM calls
            tools: Available tools for the agent
            task_name: Optional task name for context
            task_description: Optional task description
            task_id: Optional task ID for tracking
            
        Returns:
            Response with reasoning trace included
        """
        
        if not self.reasoning_enabled:
            return super().chat(message, temperature, tools, task_name, task_description, task_id)
        
        try:
            # Reset reasoning engine for new conversation
            self.reasoning_engine.reset()
            
            # Generate reasoning-enhanced response
            response = self._chat_with_reasoning(
                message, temperature, tools, task_name, task_description, task_id
            )
            
            # Store reasoning trace
            self.last_reasoning_steps = self.reasoning_engine.reasoning_steps.copy()
            self.reasoning_trace.append({
                "message": message,
                "response": response,
                "steps": self.reasoning_engine.get_reasoning_trace(),
                "summary": self.reasoning_engine.get_reasoning_summary()
            })
            
            return response
            
        except Exception as e:
            logger.error(f"Error in reasoning chat: {e}")
            # Fallback to base agent chat
            return super().chat(message, temperature, tools, task_name, task_description, task_id)
    
    def _chat_with_reasoning(
        self,
        message: str,
        temperature: float,
        tools: Optional[List[Any]],
        task_name: Optional[str],
        task_description: Optional[str],
        task_id: Optional[str]
    ) -> str:
        """
        Internal method to handle reasoning-enhanced chat.
        """
        
        # Initial reasoning step: problem analysis
        analysis_step = self.reasoning_engine.create_step(
            title="Problem Analysis",
            action="Analyze the problem and break it down",
            thought=f"Analyzing: {message}"
        )
        
        # Use Chain of Thought if available
        if self.cot_generator:
            try:
                cot_result = self.cot_generator.cot_generate_dict(message)
                analysis_step.thought = cot_result.get("thought_process", "")
                analysis_step.confidence = 0.8  # Default confidence for COT
                
                # Update step with COT results
                self.reasoning_engine.update_step(
                    analysis_step.id,
                    thought=analysis_step.thought,
                    confidence=analysis_step.confidence
                )
                
            except Exception as e:
                logger.warning(f"COT generation failed: {e}")
                analysis_step.confidence = 0.5
        
        # Determine next action
        action_state = self.reasoning_engine.should_continue()
        
        # Process based on action state
        response = ""
        step_count = 0
        max_reasoning_steps = self.reasoning_config.max_steps
        
        while step_count < max_reasoning_steps:
            step_count += 1
            
            if action_state == ActionState.FINAL_ANSWER:
                # Generate final response using base agent
                response = super().chat(
                    self._build_reasoning_prompt(message),
                    temperature,
                    tools,
                    task_name,
                    task_description,
                    task_id
                )
                
                # Create final step
                final_step = self.reasoning_engine.create_step(
                    title="Final Answer",
                    action="Generate final response",
                    thought=response,
                    confidence=0.9
                )
                
                break
                
            elif action_state == ActionState.VALIDATE:
                # Validate current reasoning
                last_step = self.reasoning_engine.reasoning_steps[-1]
                is_valid = self.reasoning_engine.validate_step(last_step)
                
                if is_valid:
                    action_state = ActionState.CONTINUE
                else:
                    # Retry or improve
                    last_step.retries += 1
                    if last_step.retries >= self.reasoning_config.max_retries:
                        action_state = ActionState.RESET
                    else:
                        action_state = ActionState.CONTINUE
                        
            elif action_state == ActionState.RESET:
                # Reset reasoning and start over
                self.reasoning_engine.reset()
                analysis_step = self.reasoning_engine.create_step(
                    title="Problem Re-analysis",
                    action="Re-analyze the problem with a different approach",
                    thought=f"Re-analyzing: {message}",
                    confidence=0.6
                )
                action_state = ActionState.CONTINUE
                
            elif action_state == ActionState.CONTINUE:
                # Continue with next reasoning step
                next_step = self.reasoning_engine.create_step(
                    title=f"Reasoning Step {step_count}",
                    action="Continue reasoning process",
                    thought="",
                    confidence=0.7
                )
                
                # Use base agent for intermediate reasoning
                intermediate_prompt = self._build_intermediate_reasoning_prompt(message, step_count)
                intermediate_response = super().chat(
                    intermediate_prompt,
                    temperature,
                    tools,
                    task_name,
                    task_description,
                    task_id
                )
                
                next_step.thought = intermediate_response
                next_step.confidence = self._estimate_confidence(intermediate_response)
                
                # Determine next action
                action_state = self.reasoning_engine.should_continue()
        
        # If we haven't generated a response yet, generate it now
        if not response:
            response = super().chat(
                self._build_reasoning_prompt(message),
                temperature,
                tools,
                task_name,
                task_description,
                task_id
            )
        
        # Add reasoning summary to response if enabled
        if self.show_reasoning:
            reasoning_summary = self._format_reasoning_summary()
            response = f"{response}\n\n--- Reasoning Process ---\n{reasoning_summary}"
        
        return response
    
    def _build_reasoning_prompt(self, original_message: str) -> str:
        """Build a prompt that includes reasoning context."""
        reasoning_context = ""
        
        if self.reasoning_engine.reasoning_steps:
            reasoning_context = "\n\nReasoning Process:\n"
            for i, step in enumerate(self.reasoning_engine.reasoning_steps, 1):
                reasoning_context += f"{i}. {step.title}: {step.action}\n"
                if step.thought:
                    reasoning_context += f"   Thought: {step.thought[:200]}...\n"
                reasoning_context += f"   Confidence: {step.confidence:.2f}\n\n"
        
        return f"{original_message}{reasoning_context}\n\nBased on the above reasoning, provide your final answer:"
    
    def _build_intermediate_reasoning_prompt(self, original_message: str, step_number: int) -> str:
        """Build a prompt for intermediate reasoning steps."""
        return f"""Continue reasoning about this problem step by step:

Original Problem: {original_message}

This is step {step_number} of your reasoning process. Consider what you've analyzed so far and continue with the next logical step. Be specific and show your thinking process.

Focus on: {"analytical thinking" if self.reasoning_config.style == "analytical" else "creative exploration" if self.reasoning_config.style == "creative" else "systematic breakdown"}"""
    
    def _estimate_confidence(self, response: str) -> float:
        """Estimate confidence based on response characteristics."""
        # Simple heuristic - can be enhanced
        confidence = 0.5
        
        # Increase confidence for longer, more detailed responses
        if len(response) > 100:
            confidence += 0.1
        if len(response) > 300:
            confidence += 0.1
            
        # Look for certainty indicators
        certainty_words = ["definitely", "clearly", "obviously", "certainly", "confirmed"]
        uncertainty_words = ["maybe", "perhaps", "possibly", "might", "unclear"]
        
        certainty_count = sum(1 for word in certainty_words if word in response.lower())
        uncertainty_count = sum(1 for word in uncertainty_words if word in response.lower())
        
        confidence += (certainty_count * 0.1) - (uncertainty_count * 0.1)
        
        return max(0.0, min(1.0, confidence))
    
    def _format_reasoning_summary(self) -> str:
        """Format the reasoning process for display."""
        if not self.reasoning_engine.reasoning_steps:
            return "No reasoning steps recorded."
        
        summary = []
        for i, step in enumerate(self.reasoning_engine.reasoning_steps, 1):
            summary.append(f"{i}. {step.title}: {step.action} (confidence: {step.confidence:.2f})")
            if step.retries > 0:
                summary.append(f"   └─ Retries: {step.retries}")
        
        stats = self.reasoning_engine.get_reasoning_summary()
        summary.append(f"\nSummary: {stats['total_steps']} steps, avg confidence: {stats['avg_confidence']:.2f}")
        
        return "\n".join(summary)
    
    async def achat(
        self,
        message: str,
        temperature: float = 0.1,
        tools: Optional[List[Any]] = None,
        task_name: Optional[str] = None,
        task_description: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> str:
        """Async version of reasoning chat."""
        # For now, use sync version - can be enhanced for true async reasoning
        return self.chat(message, temperature, tools, task_name, task_description, task_id)
    
    @property
    def reasoning_summary(self) -> Dict[str, Any]:
        """Get current reasoning summary."""
        return self.reasoning_engine.get_reasoning_summary()
    
    def get_reasoning_trace(self) -> List[Dict[str, Any]]:
        """Get the full reasoning trace for all conversations."""
        return self.reasoning_trace.copy()
    
    def clear_reasoning_history(self):
        """Clear reasoning history."""
        self.reasoning_trace.clear()
        self.last_reasoning_steps.clear()
        self.reasoning_engine.reset()