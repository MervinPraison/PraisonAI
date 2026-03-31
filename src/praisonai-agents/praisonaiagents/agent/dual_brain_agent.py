"""
DualBrainAgent - A specialized agent class with fast (System-1) and deliberate (System-2) thinking modes.
This class extends the base Agent class to provide dual-mode processing based on query complexity,
using lightweight models for fast responses and powerful models for complex reasoning.
"""
from typing import Optional, Any, Dict, Union, List, Literal, Tuple
from ..agent.agent import Agent
from pydantic import BaseModel, Field
from praisonaiagents._logging import get_logger
import warnings
import re

# Filter out Pydantic warning about fields
warnings.filterwarnings("ignore", "Valid config keys have changed in V2", UserWarning)

logger = get_logger(__name__)


class DualBrainConfig(BaseModel):
    """Configuration for dual brain settings."""
    system1_model: str = Field(
        default="gpt-4o-mini", 
        description="Fast model for System-1 (quick) thinking - simple queries"
    )
    system2_model: str = Field(
        default="gpt-4o", 
        description="Powerful model for System-2 (deliberate) thinking - complex queries"
    )
    complexity_threshold: float = Field(
        default=0.5, 
        description="Threshold for complexity detection (0-1, higher = more likely System-2)"
    )
    auto_detect_complexity: bool = Field(
        default=True, 
        description="Whether to automatically detect query complexity"
    )
    fallback_to_system1: bool = Field(
        default=True, 
        description="Whether to fallback to System-1 if System-2 model unavailable"
    )
    show_mode_selection: bool = Field(
        default=False, 
        description="Whether to show which thinking mode was selected"
    )


class DualBrainAgent(Agent):
    """
    Agent with fast (System-1) and deliberate (System-2) thinking modes.
    
    This agent automatically detects query complexity and routes to appropriate thinking mode:
    - System-1 (fast): Quick responses for simple queries using lightweight model
    - System-2 (deliberate): Deep reasoning for complex queries using powerful model
    
    Features:
    - System-1 (fast): quick responses for simple queries using lightweight model
    - System-2 (deliberate): deep reasoning for complex queries using powerful model
    - Automatic complexity detection to route between modes
    - Configurable model for each mode
    - Falls back gracefully if only one model available
    """
    
    def __init__(
        self,
        name: str,
        dual_brain_config: Optional[DualBrainConfig] = None,
        **kwargs
    ):
        """
        Initialize a DualBrainAgent.
        
        Args:
            name: Name of the agent
            dual_brain_config: Configuration for dual brain behavior
            **kwargs: Additional arguments passed to base Agent class
        """
        self.dual_brain_config = dual_brain_config or DualBrainConfig()
        
        # Initialize with System-1 model by default
        if 'llm' not in kwargs:
            kwargs['llm'] = self.dual_brain_config.system1_model
        
        super().__init__(name=name, **kwargs)
        
        # Store original LLM for mode switching
        self._system1_llm = self.dual_brain_config.system1_model
        self._system2_llm = self.dual_brain_config.system2_model
        self._current_mode = "system1"
        
        logger.info(f"DualBrainAgent '{name}' initialized with System-1: {self._system1_llm}, System-2: {self._system2_llm}")
    
    def _detect_complexity(self, message: str) -> float:
        """
        Detect complexity of the input message.
        
        Args:
            message: Input message to analyze
            
        Returns:
            Complexity score between 0 and 1 (higher = more complex)
        """
        complexity_indicators = [
            # Length indicators
            (len(message) > 200, 0.1),
            (len(message) > 500, 0.2),
            
            # Question complexity
            (message.count('?') > 2, 0.15),
            ('how' in message.lower() and 'why' in message.lower(), 0.2),
            
            # Keywords indicating complex reasoning
            ('analyze' in message.lower(), 0.3),
            ('compare' in message.lower(), 0.25),
            ('explain' in message.lower(), 0.2),
            ('reasoning' in message.lower(), 0.3),
            ('complex' in message.lower(), 0.25),
            ('detailed' in message.lower(), 0.2),
            ('comprehensive' in message.lower(), 0.3),
            ('step-by-step' in message.lower(), 0.25),
            ('pros and cons' in message.lower(), 0.3),
            ('advantages and disadvantages' in message.lower(), 0.3),
            
            # Mathematical or logical indicators
            ('calculate' in message.lower(), 0.25),
            ('solve' in message.lower(), 0.2),
            ('prove' in message.lower(), 0.3),
            ('algorithm' in message.lower(), 0.25),
            
            # Multi-part questions
            (message.count('and') > 3, 0.15),
            (message.count(',') > 5, 0.1),
            
            # Code or technical content
            ('function' in message.lower(), 0.15),
            ('class' in message.lower(), 0.15),
            ('code' in message.lower(), 0.2),
            ('implement' in message.lower(), 0.25),
            
            # Research indicators
            ('research' in message.lower(), 0.3),
            ('study' in message.lower(), 0.2),
            ('investigate' in message.lower(), 0.25),
        ]
        
        score = 0.0
        for condition, weight in complexity_indicators:
            if condition:
                score += weight
        
        # Normalize to 0-1 range
        score = min(1.0, score)
        
        logger.debug(f"Complexity score for message: {score:.2f}")
        return score
    
    def _select_thinking_mode(self, message: str) -> str:
        """
        Select thinking mode based on message complexity.
        
        Args:
            message: Input message
            
        Returns:
            "system1" for fast thinking, "system2" for deliberate thinking
        """
        if not self.dual_brain_config.auto_detect_complexity:
            return "system1"  # Default to fast mode
        
        complexity = self._detect_complexity(message)
        
        if complexity >= self.dual_brain_config.complexity_threshold:
            return "system2"
        else:
            return "system1"
    
    def _switch_to_mode(self, mode: str) -> bool:
        """
        Switch to specified thinking mode.
        
        Args:
            mode: "system1" or "system2"
            
        Returns:
            True if switch successful, False if failed
        """
        try:
            if mode == "system1":
                self.llm = self._system1_llm
                self._current_mode = "system1"
                logger.debug(f"Switched to System-1 mode: {self._system1_llm}")
                return True
            elif mode == "system2":
                self.llm = self._system2_llm  
                self._current_mode = "system2"
                logger.debug(f"Switched to System-2 mode: {self._system2_llm}")
                return True
            else:
                logger.error(f"Unknown mode: {mode}")
                return False
        except Exception as e:
            logger.error(f"Failed to switch to {mode} mode: {e}")
            if self.dual_brain_config.fallback_to_system1:
                self.llm = self._system1_llm
                self._current_mode = "system1"
                logger.info("Falling back to System-1 mode")
                return True
            return False
    
    def _format_response_with_mode(self, response: str, mode: str) -> str:
        """Format response with mode information if enabled."""
        if not self.dual_brain_config.show_mode_selection:
            return response
            
        mode_name = "System-1 (Fast)" if mode == "system1" else "System-2 (Deliberate)"
        return f"[{mode_name} thinking mode]\n\n{response}"
    
    def run(self, message: str, **kwargs) -> str:
        """
        Execute the dual brain agent with appropriate thinking mode.
        
        Args:
            message: Input message/question
            **kwargs: Additional arguments
            
        Returns:
            Response from selected thinking mode
        """
        logger.debug(f"DualBrainAgent '{self.name}' processing: {message}")
        
        # Select thinking mode based on complexity
        selected_mode = self._select_thinking_mode(message)
        
        # Switch to selected mode
        switch_success = self._switch_to_mode(selected_mode)
        if not switch_success:
            logger.warning("Mode switch failed, using current mode")
        
        # Execute with selected mode
        response = super().run(message, **kwargs)
        
        # Format response with mode info if enabled
        return self._format_response_with_mode(response, self._current_mode)
    
    async def arun(self, message: str, **kwargs) -> str:
        """
        Async version of run method.
        
        Args:
            message: Input message/question
            **kwargs: Additional arguments
            
        Returns:
            Response from selected thinking mode
        """
        logger.debug(f"DualBrainAgent '{self.name}' async processing: {message}")
        
        # Select thinking mode based on complexity
        selected_mode = self._select_thinking_mode(message)
        
        # Switch to selected mode
        switch_success = self._switch_to_mode(selected_mode)
        if not switch_success:
            logger.warning("Mode switch failed, using current mode")
        
        # Execute with selected mode
        response = await super().arun(message, **kwargs)
        
        # Format response with mode info if enabled
        return self._format_response_with_mode(response, self._current_mode)
    
    def start(self, message: str, **kwargs) -> str:
        """
        Start dual brain agent session.
        
        Args:
            message: Input message/question
            **kwargs: Additional arguments
            
        Returns:
            Response from appropriate thinking mode
        """
        logger.debug(f"DualBrainAgent '{self.name}' starting session: {message}")
        return self.run(message, **kwargs)
    
    async def astart(self, message: str, **kwargs) -> str:
        """
        Async start dual brain agent session.
        
        Args:
            message: Input message/question
            **kwargs: Additional arguments
            
        Returns:
            Response from appropriate thinking mode
        """
        logger.debug(f"DualBrainAgent '{self.name}' starting async session: {message}")
        return await self.arun(message, **kwargs)
    
    def force_system1_mode(self) -> None:
        """Force agent into System-1 (fast) thinking mode."""
        self._switch_to_mode("system1")
        logger.info("Forced into System-1 mode")
    
    def force_system2_mode(self) -> None:
        """Force agent into System-2 (deliberate) thinking mode."""
        self._switch_to_mode("system2") 
        logger.info("Forced into System-2 mode")
    
    def get_current_mode(self) -> str:
        """Get current thinking mode."""
        return self._current_mode
    
    def get_complexity_threshold(self) -> float:
        """Get current complexity threshold."""
        return self.dual_brain_config.complexity_threshold
    
    def set_complexity_threshold(self, threshold: float) -> None:
        """Set complexity threshold for mode selection."""
        if 0 <= threshold <= 1:
            self.dual_brain_config.complexity_threshold = threshold
            logger.info(f"Complexity threshold set to {threshold}")
        else:
            raise ValueError("Complexity threshold must be between 0 and 1")