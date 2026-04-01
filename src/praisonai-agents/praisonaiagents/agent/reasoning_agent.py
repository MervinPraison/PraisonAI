"""
ReasoningAgent - A specialized agent class for chain-of-thought reasoning with self-verification.
This class extends the base Agent class to provide explicit reasoning capabilities,
including step-by-step breakdown and self-verification loops.
"""
from typing import Optional, Any, Dict, Union, List, Literal
from .agent import Agent
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
        description="Reasoning depth level"
    )
    verification: bool = Field(
        default=True, 
        description="Enable self-verification loops"
    )
    max_reasoning_steps: int = Field(
        default=5, 
        description="Maximum number of reasoning steps"
    )
    show_thinking: bool = Field(
        default=True, 
        description="Show reasoning steps in output"
    )


class ReasoningAgent(Agent):
    """
    Agent that uses chain-of-thought reasoning with self-verification.
    
    This agent extends the base Agent class with specific functionality for:
    - Automatic chain-of-thought prompting in system instructions
    - Step-by-step reasoning breakdown
    - Self-verification loop: agent checks its own reasoning before final answer
    - Configurable reasoning depth (shallow/medium/deep)
    - Works with any LLM (not dependent on model-specific features)
    
    Example:
        ```python
        from praisonaiagents import ReasoningAgent
        
        agent = ReasoningAgent(
            name="reasoner",
            instructions="Think step by step about complex problems",
            reasoning_depth="deep"
        )
        
        result = agent.start("What is 17 * 23? Show your reasoning.")
        print(result)
        ```
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        role: Optional[str] = None,
        goal: Optional[str] = None,
        backstory: Optional[str] = None,
        instructions: Optional[str] = None,
        llm: Optional[Union[str, Any]] = None,
        reasoning_depth: Literal["shallow", "medium", "deep"] = "medium",
        verification: bool = True,
        max_reasoning_steps: int = 5,
        show_thinking: bool = True,
        verbose: Union[bool, int] = True,
        **kwargs
    ):
        """Initialize ReasoningAgent with reasoning parameters."""
        # Set default role and goal if not provided
        role = role or "Reasoning Assistant"
        goal = goal or "Analyze problems systematically using step-by-step reasoning"
        backstory = backstory or (
            "I am an AI assistant specialized in analytical thinking and logical reasoning. "
            "I break down complex problems into manageable steps and verify my reasoning."
        )
        
        # Build enhanced instructions with reasoning prompts
        enhanced_instructions = self._build_reasoning_instructions(
            instructions, reasoning_depth, verification, show_thinking
        )
        
        # Initialize the base agent
        super().__init__(
            name=name,
            role=role,
            goal=goal,
            backstory=backstory,
            instructions=enhanced_instructions,
            llm=llm,
            **kwargs
        )
        
        # Store reasoning configuration
        self.reasoning_config = ReasoningConfig(
            depth=reasoning_depth,
            verification=verification,
            max_reasoning_steps=max_reasoning_steps,
            show_thinking=show_thinking
        )
        
        if verbose:
            logger.info(f"ReasoningAgent '{self.name}' initialized with {reasoning_depth} reasoning depth")

    def _build_reasoning_instructions(
        self, 
        base_instructions: Optional[str], 
        depth: str, 
        verification: bool,
        show_thinking: bool
    ) -> str:
        """Build enhanced instructions with chain-of-thought reasoning prompts."""
        reasoning_prompts = {
            "shallow": """
Think through problems step by step:
1. Understand the question
2. Apply relevant knowledge 
3. Provide a clear answer
""",
            "medium": """
Use systematic reasoning for all responses:
1. Break down the problem into key components
2. Analyze each component methodically  
3. Consider potential approaches or solutions
4. Apply logical reasoning to reach conclusions
5. Present your reasoning clearly before the final answer
""",
            "deep": """
Apply comprehensive analytical thinking:
1. Parse and understand the problem thoroughly
2. Identify all relevant factors and constraints
3. Consider multiple approaches and their trade-offs
4. Work through the logic step-by-step
5. Examine potential edge cases or exceptions
6. Cross-check your reasoning for consistency
7. Provide a well-reasoned final answer with confidence assessment
"""
        }
        
        instructions = reasoning_prompts[depth]
        
        if verification:
            instructions += "\nBEFORE providing your final answer, always verify your reasoning by asking yourself: 'Does this logic make sense? Are there any errors in my thinking?'"
        
        if show_thinking:
            instructions += "\nShow your thinking process clearly, using step numbers or bullet points to organize your reasoning."
        
        # Append base instructions if provided
        if base_instructions:
            instructions += f"\n\nAdditional instructions:\n{base_instructions}"
        
        return instructions

    def start(
        self,
        prompt: str,
        reasoning_override: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Any:
        """
        Start reasoning through the given prompt with enhanced chain-of-thought.
        
        Args:
            prompt: The input prompt to reason about
            reasoning_override: Temporary override for reasoning config
            **kwargs: Additional arguments passed to parent start method
            
        Returns:
            The reasoned response from the agent
        """
        # Apply any temporary reasoning overrides
        if reasoning_override:
            original_config = self.reasoning_config.dict()
            for key, value in reasoning_override.items():
                if hasattr(self.reasoning_config, key):
                    setattr(self.reasoning_config, key, value)
        
        try:
            # Enhance the prompt for reasoning if needed
            enhanced_prompt = self._enhance_prompt_for_reasoning(prompt)
            
            # Call parent start method with enhanced prompt
            result = super().start(enhanced_prompt, **kwargs)
            
            return result
            
        finally:
            # Restore original config if it was overridden
            if reasoning_override:
                for key, value in original_config.items():
                    setattr(self.reasoning_config, key, value)

    async def astart(
        self,
        prompt: str,
        reasoning_override: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Any:
        """Async version of start method."""
        # Apply any temporary reasoning overrides
        if reasoning_override:
            original_config = self.reasoning_config.dict()
            for key, value in reasoning_override.items():
                if hasattr(self.reasoning_config, key):
                    setattr(self.reasoning_config, key, value)
        
        try:
            # Enhance the prompt for reasoning if needed
            enhanced_prompt = self._enhance_prompt_for_reasoning(prompt)
            
            # Call parent astart method with enhanced prompt
            result = await super().astart(enhanced_prompt, **kwargs)
            
            return result
            
        finally:
            # Restore original config if it was overridden
            if reasoning_override:
                for key, value in original_config.items():
                    setattr(self.reasoning_config, key, value)

    def _enhance_prompt_for_reasoning(self, prompt: str) -> str:
        """Enhance the user prompt with reasoning cues based on configuration."""
        if not self.reasoning_config.show_thinking:
            return prompt
        
        depth_cues = {
            "shallow": "Think through this step by step:",
            "medium": "Please reason through this systematically:",
            "deep": "Apply comprehensive analytical thinking to this problem:"
        }
        
        cue = depth_cues[self.reasoning_config.depth]
        enhanced_prompt = f"{cue}\n\n{prompt}"
        
        if self.reasoning_config.verification:
            enhanced_prompt += "\n\nPlease verify your reasoning before providing the final answer."
        
        return enhanced_prompt

    def run(self, prompt: str, **kwargs) -> Any:
        """Run method with reasoning enhancement - alias for start."""
        return self.start(prompt, **kwargs)

    async def arun(self, prompt: str, **kwargs) -> Any:
        """Async run method with reasoning enhancement."""
        return await self.astart(prompt, **kwargs)

    def update_reasoning_config(self, **config_updates) -> None:
        """
        Update reasoning configuration dynamically.
        
        Args:
            **config_updates: New values for reasoning config fields
            
        Example:
            agent.update_reasoning_config(depth="deep", verification=True)
        """
        for key, value in config_updates.items():
            if hasattr(self.reasoning_config, key):
                setattr(self.reasoning_config, key, value)
                logger.info(f"Updated reasoning config: {key}={value}")
            else:
                logger.warning(f"Unknown reasoning config key: {key}")
        
        # Rebuild instructions with new config
        self.instructions = self._build_reasoning_instructions(
            None,  # No base instructions to preserve 
            self.reasoning_config.depth,
            self.reasoning_config.verification,
            self.reasoning_config.show_thinking
        )