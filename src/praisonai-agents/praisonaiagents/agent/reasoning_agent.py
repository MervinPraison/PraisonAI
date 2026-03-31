"""
ReasoningAgent - A specialized agent class that uses chain-of-thought reasoning with self-verification.
This class extends the base Agent class to provide step-by-step reasoning breakdown with
automatic self-verification loop for higher accuracy.
"""
from typing import Optional, Any, Dict, Union, List, Literal
from ..agent.agent import Agent
from pydantic import BaseModel, Field
from praisonaiagents._logging import get_logger
import warnings

# Filter out Pydantic warning about fields
warnings.filterwarnings("ignore", "Valid config keys have changed in V2", UserWarning)

logger = get_logger(__name__)


class ReasoningConfig(BaseModel):
    """Configuration for reasoning settings."""
    depth: Literal["shallow", "medium", "deep"] = Field(
        default="medium", 
        description="Depth of reasoning - shallow: 2-3 steps, medium: 4-6 steps, deep: 7+ steps"
    )
    self_verify: bool = Field(
        default=True, 
        description="Whether to perform self-verification of reasoning before final answer"
    )
    show_steps: bool = Field(
        default=True, 
        description="Whether to show reasoning steps in the output"
    )
    verification_prompt: str = Field(
        default="Please review your reasoning above. Is it logical and correct? If you find any errors, explain them and provide the corrected reasoning.",
        description="Prompt used for self-verification"
    )


class ReasoningAgent(Agent):
    """
    Agent that uses chain-of-thought reasoning with self-verification.
    
    This agent automatically applies chain-of-thought prompting to break down problems
    into logical steps, then optionally verifies its own reasoning before providing
    the final answer. Works with any LLM model.
    
    Features:
    - Automatic chain-of-thought prompting in system instructions
    - Step-by-step reasoning breakdown  
    - Self-verification loop: agent checks its own reasoning before final answer
    - Configurable reasoning depth (shallow/medium/deep)
    - Works with any LLM (not dependent on model-specific features)
    """
    
    def __init__(
        self,
        name: str,
        reasoning_config: Optional[ReasoningConfig] = None,
        **kwargs
    ):
        """
        Initialize a ReasoningAgent.
        
        Args:
            name: Name of the agent
            reasoning_config: Configuration for reasoning behavior
            **kwargs: Additional arguments passed to base Agent class
        """
        self.reasoning_config = reasoning_config or ReasoningConfig()
        
        # Enhance system instructions with chain-of-thought prompting
        original_instructions = kwargs.get('instructions', 'You are a helpful assistant.')
        enhanced_instructions = self._build_reasoning_instructions(original_instructions)
        kwargs['instructions'] = enhanced_instructions
        
        super().__init__(name=name, **kwargs)
        
        logger.info(f"ReasoningAgent '{name}' initialized with {self.reasoning_config.depth} reasoning depth")
    
    def _build_reasoning_instructions(self, original_instructions: str) -> str:
        """Build enhanced system instructions with chain-of-thought prompting."""
        
        depth_instructions = {
            "shallow": "Break down your thinking into 2-3 clear steps before answering.",
            "medium": "Think through this step-by-step using 4-6 logical steps, explaining your reasoning at each stage.",
            "deep": "Provide detailed reasoning with 7 or more comprehensive steps, thoroughly analyzing all aspects."
        }
        
        reasoning_instruction = depth_instructions[self.reasoning_config.depth]
        
        enhanced = f"""{original_instructions}

REASONING FRAMEWORK:
You must use chain-of-thought reasoning for all responses. {reasoning_instruction}

Format your responses as:
1. REASONING:
   [Your step-by-step thinking process]

2. ANSWER:
   [Your final answer or response]

Always show your reasoning process clearly and logically."""

        if self.reasoning_config.self_verify:
            enhanced += f"""

3. VERIFICATION:
   After providing your reasoning and answer, review your work by asking: "{self.reasoning_config.verification_prompt}"
   If you find any issues, correct them and provide the updated reasoning and answer."""
        
        return enhanced
    
    def run(self, message: str, **kwargs) -> str:
        """
        Execute the reasoning agent with chain-of-thought processing.
        
        Args:
            message: Input message/question
            **kwargs: Additional arguments
            
        Returns:
            Response with reasoning steps and verified answer
        """
        logger.debug(f"ReasoningAgent '{self.name}' processing: {message}")
        
        # Call parent run method with enhanced prompting
        response = super().run(message, **kwargs)
        
        if self.reasoning_config.show_steps:
            return response
        else:
            # Extract just the final answer if steps should be hidden
            return self._extract_final_answer(response)
    
    async def arun(self, message: str, **kwargs) -> str:
        """
        Async version of run method.
        
        Args:
            message: Input message/question  
            **kwargs: Additional arguments
            
        Returns:
            Response with reasoning steps and verified answer
        """
        logger.debug(f"ReasoningAgent '{self.name}' async processing: {message}")
        
        # Call parent arun method with enhanced prompting
        response = await super().arun(message, **kwargs)
        
        if self.reasoning_config.show_steps:
            return response
        else:
            # Extract just the final answer if steps should be hidden
            return self._extract_final_answer(response)
    
    def start(self, message: str, **kwargs) -> str:
        """
        Start reasoning agent session.
        
        Args:
            message: Input message/question
            **kwargs: Additional arguments
            
        Returns:
            Response with reasoning and answer
        """
        logger.debug(f"ReasoningAgent '{self.name}' starting session: {message}")
        return self.run(message, **kwargs)
    
    async def astart(self, message: str, **kwargs) -> str:
        """
        Async start reasoning agent session.
        
        Args:
            message: Input message/question
            **kwargs: Additional arguments
            
        Returns:
            Response with reasoning and answer
        """
        logger.debug(f"ReasoningAgent '{self.name}' starting async session: {message}")
        return await self.arun(message, **kwargs)
    
    def _extract_final_answer(self, response: str) -> str:
        """Extract just the final answer from a reasoned response."""
        try:
            # Look for ANSWER: section
            if "ANSWER:" in response:
                parts = response.split("ANSWER:")
                if len(parts) > 1:
                    answer = parts[1].split("VERIFICATION:")[0].strip()
                    return answer
            
            # Fallback: return full response if no clear structure
            return response
            
        except Exception as e:
            logger.warning(f"Failed to extract final answer: {e}")
            return response