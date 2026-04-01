"""
DualBrainAgent - A specialized agent class with fast (System-1) and deliberate (System-2) thinking modes.
This class extends the base Agent class to provide dual-mode cognitive processing,
automatically routing between fast and deliberate thinking based on query complexity.
"""
from typing import Optional, Any, Dict, Union, List
from .agent import Agent
from pydantic import BaseModel, Field
from praisonaiagents._logging import get_logger
import warnings
import re

# Filter out Pydantic warning about fields
warnings.filterwarnings("ignore", "Valid config keys have changed in V2", UserWarning)

logger = get_logger(__name__)


class DualBrainConfig(BaseModel):
    """Configuration for dual brain settings."""
    fast_model: str = Field(
        default="gpt-4o-mini", 
        description="Lightweight model for fast System-1 thinking"
    )
    deliberate_model: str = Field(
        default="gpt-4o", 
        description="Powerful model for deliberate System-2 thinking"
    )
    complexity_threshold: float = Field(
        default=0.5, 
        description="Complexity threshold (0-1) for routing decisions"
    )
    auto_detect: bool = Field(
        default=True, 
        description="Enable automatic complexity detection"
    )
    show_mode_selection: bool = Field(
        default=True, 
        description="Show which mode was selected"
    )
    fallback_to_single: bool = Field(
        default=True, 
        description="Fallback gracefully if only one model available"
    )


class DualBrainAgent(Agent):
    """
    Agent with fast (System-1) and deliberate (System-2) thinking modes.
    
    This agent extends the base Agent class with dual cognitive processing:
    - System-1 (fast): Quick responses for simple queries using lightweight model
    - System-2 (deliberate): Deep reasoning for complex queries using powerful model
    - Automatic complexity detection to route between modes
    - Configurable model for each mode
    - Falls back gracefully if only one model available
    
    Example:
        ```python
        from praisonaiagents import DualBrainAgent
        
        agent = DualBrainAgent(
            name="dual",
            instructions="Analyze carefully and respond appropriately",
            fast_model="gpt-4o-mini",
            deliberate_model="gpt-4o"
        )
        
        # Simple query -> System-1 (fast)
        result = agent.start("What is 2 + 2?")
        
        # Complex query -> System-2 (deliberate)  
        result = agent.start("Analyze the economic implications of quantum computing on financial markets")
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
        fast_model: str = "gpt-4o-mini",
        deliberate_model: str = "gpt-4o", 
        complexity_threshold: float = 0.5,
        auto_detect: bool = True,
        show_mode_selection: bool = True,
        fallback_to_single: bool = True,
        verbose: Union[bool, int] = True,
        **kwargs
    ):
        """Initialize DualBrainAgent with dual-mode parameters."""
        # Set default role and goal if not provided
        role = role or "Dual-Mode AI Assistant"
        goal = goal or "Provide optimal responses using fast or deliberate thinking as needed"
        backstory = backstory or (
            "I am an AI assistant with dual cognitive modes: fast intuitive thinking for simple tasks "
            "and deliberate analytical thinking for complex problems. I automatically choose the "
            "appropriate mode based on the complexity of each request."
        )
        
        # Use the deliberate model as default if no llm specified
        default_llm = llm or deliberate_model
        
        # Initialize the base agent
        super().__init__(
            name=name,
            role=role,
            goal=goal,
            backstory=backstory,
            instructions=instructions,
            llm=default_llm,
            **kwargs
        )
        
        # Store dual brain configuration
        self.dual_config = DualBrainConfig(
            fast_model=fast_model,
            deliberate_model=deliberate_model,
            complexity_threshold=complexity_threshold,
            auto_detect=auto_detect,
            show_mode_selection=show_mode_selection,
            fallback_to_single=fallback_to_single
        )
        
        if verbose:
            logger.info(
                f"DualBrainAgent '{self.name}' initialized with "
                f"fast_model='{fast_model}' and deliberate_model='{deliberate_model}'"
            )

    def _detect_complexity(self, prompt: str) -> float:
        """
        Detect the complexity of a given prompt.
        
        Returns a score from 0.0 (simple) to 1.0 (complex) based on various indicators.
        """
        if not self.dual_config.auto_detect:
            return 0.5  # Default to medium complexity
        
        complexity_score = 0.0
        
        # Length indicators
        word_count = len(prompt.split())
        if word_count > 50:
            complexity_score += 0.2
        elif word_count > 100:
            complexity_score += 0.3
        
        # Question complexity indicators
        complex_question_words = [
            'analyze', 'compare', 'contrast', 'evaluate', 'explain', 'justify',
            'argue', 'discuss', 'elaborate', 'synthesize', 'critique', 'assess',
            'implications', 'consequences', 'trade-offs', 'relationships',
            'comprehensive', 'detailed', 'thorough', 'complex', 'nuanced'
        ]
        
        prompt_lower = prompt.lower()
        complex_word_count = sum(1 for word in complex_question_words if word in prompt_lower)
        complexity_score += min(complex_word_count * 0.1, 0.4)
        
        # Multiple question indicators
        question_marks = prompt.count('?')
        if question_marks > 1:
            complexity_score += 0.1
        
        # Mathematical complexity
        math_indicators = [
            'calculate', 'solve', 'equation', 'formula', 'algorithm',
            'mathematical', 'computation', 'derivative', 'integral'
        ]
        if any(word in prompt_lower for word in math_indicators):
            # Check if it's simple arithmetic vs complex math
            simple_math = re.search(r'\b\d+\s*[+\-*/]\s*\d+\b', prompt)
            if simple_math and len(prompt.split()) < 20:
                complexity_score += 0.1  # Simple math
            else:
                complexity_score += 0.3  # Complex math
        
        # Domain-specific complexity
        complex_domains = [
            'economics', 'philosophy', 'psychology', 'sociology', 'politics',
            'quantum', 'molecular', 'genetic', 'neural', 'strategic',
            'ethical', 'legal', 'financial', 'statistical', 'research'
        ]
        if any(domain in prompt_lower for domain in complex_domains):
            complexity_score += 0.2
        
        # Multi-step process indicators
        step_indicators = ['first', 'then', 'next', 'finally', 'step', 'process', 'methodology']
        if any(word in prompt_lower for word in step_indicators):
            complexity_score += 0.15
        
        # Cap at 1.0
        return min(complexity_score, 1.0)

    def _choose_thinking_mode(self, prompt: str) -> str:
        """
        Choose between fast (System-1) or deliberate (System-2) thinking mode.
        
        Returns:
            'fast' for System-1 or 'deliberate' for System-2
        """
        if not self.dual_config.auto_detect:
            return 'deliberate'  # Default to deliberate mode
        
        complexity = self._detect_complexity(prompt)
        
        if complexity >= self.dual_config.complexity_threshold:
            return 'deliberate'
        else:
            return 'fast'

    def _get_model_for_mode(self, mode: str) -> str:
        """Get the appropriate model for the given thinking mode."""
        if mode == 'fast':
            return self.dual_config.fast_model
        else:
            return self.dual_config.deliberate_model

    def start(
        self,
        prompt: str,
        force_mode: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Start processing with automatic mode selection or forced mode.
        
        Args:
            prompt: The input prompt to process
            force_mode: Force 'fast' or 'deliberate' mode, bypass auto-detection
            **kwargs: Additional arguments passed to parent start method
            
        Returns:
            The response from the appropriate thinking mode
        """
        # Determine thinking mode
        if force_mode in ['fast', 'deliberate']:
            mode = force_mode
            complexity = 0.5  # Default for display
        else:
            mode = self._choose_thinking_mode(prompt)
            complexity = self._detect_complexity(prompt)
        
        # Get model for this mode
        selected_model = self._get_model_for_mode(mode)
        
        # Show mode selection if configured
        if self.dual_config.show_mode_selection and hasattr(self, 'console'):
            mode_name = "System-1 (fast)" if mode == 'fast' else "System-2 (deliberate)"
            self.console.print(
                f"[cyan]🧠 {mode_name} thinking mode selected "
                f"(complexity: {complexity:.2f}, model: {selected_model})[/cyan]"
            )
        
        # Store original model and switch temporarily
        original_model = self.llm
        self.llm = selected_model
        
        try:
            # Enhance prompt based on mode
            enhanced_prompt = self._enhance_prompt_for_mode(prompt, mode)
            
            # Call parent start method
            result = super().start(enhanced_prompt, **kwargs)
            
            return result
            
        except Exception as e:
            # Fallback to single model if dual-model fails
            if self.dual_config.fallback_to_single and mode == 'fast':
                logger.warning(f"Fast model failed, falling back to deliberate model: {e}")
                self.llm = self.dual_config.deliberate_model
                enhanced_prompt = self._enhance_prompt_for_mode(prompt, 'deliberate')
                result = super().start(enhanced_prompt, **kwargs)
                return result
            else:
                raise
                
        finally:
            # Restore original model
            self.llm = original_model

    async def astart(
        self,
        prompt: str,
        force_mode: Optional[str] = None,
        **kwargs
    ) -> Any:
        """Async version of start method."""
        # Determine thinking mode
        if force_mode in ['fast', 'deliberate']:
            mode = force_mode
            complexity = 0.5  # Default for display
        else:
            mode = self._choose_thinking_mode(prompt)
            complexity = self._detect_complexity(prompt)
        
        # Get model for this mode
        selected_model = self._get_model_for_mode(mode)
        
        # Show mode selection if configured
        if self.dual_config.show_mode_selection and hasattr(self, 'console'):
            mode_name = "System-1 (fast)" if mode == 'fast' else "System-2 (deliberate)"
            self.console.print(
                f"[cyan]🧠 {mode_name} thinking mode selected "
                f"(complexity: {complexity:.2f}, model: {selected_model})[/cyan]"
            )
        
        # Store original model and switch temporarily
        original_model = self.llm
        self.llm = selected_model
        
        try:
            # Enhance prompt based on mode
            enhanced_prompt = self._enhance_prompt_for_mode(prompt, mode)
            
            # Call parent astart method
            result = await super().astart(enhanced_prompt, **kwargs)
            
            return result
            
        except Exception as e:
            # Fallback to single model if dual-model fails
            if self.dual_config.fallback_to_single and mode == 'fast':
                logger.warning(f"Fast model failed, falling back to deliberate model: {e}")
                self.llm = self.dual_config.deliberate_model
                enhanced_prompt = self._enhance_prompt_for_mode(prompt, 'deliberate')
                result = await super().astart(enhanced_prompt, **kwargs)
                return result
            else:
                raise
                
        finally:
            # Restore original model
            self.llm = original_model

    def _enhance_prompt_for_mode(self, prompt: str, mode: str) -> str:
        """Enhance the prompt based on the selected thinking mode."""
        if mode == 'fast':
            # System-1: Quick, intuitive responses
            enhanced_prompt = (
                "Provide a quick, direct response to this question. "
                "Use your immediate knowledge and intuition:\n\n"
                f"{prompt}"
            )
        else:
            # System-2: Deliberate, analytical thinking
            enhanced_prompt = (
                "Think carefully and analytically about this question. "
                "Consider multiple aspects, implications, and provide a thorough response:\n\n"
                f"{prompt}"
            )
        
        return enhanced_prompt

    def run(self, prompt: str, **kwargs) -> Any:
        """Run method with dual-mode processing - alias for start."""
        return self.start(prompt, **kwargs)

    async def arun(self, prompt: str, **kwargs) -> Any:
        """Async run method with dual-mode processing."""
        return await self.astart(prompt, **kwargs)

    def update_dual_config(self, **config_updates) -> None:
        """
        Update dual brain configuration dynamically.
        
        Args:
            **config_updates: New values for dual brain config fields
            
        Example:
            agent.update_dual_config(complexity_threshold=0.7, show_mode_selection=False)
        """
        for key, value in config_updates.items():
            if hasattr(self.dual_config, key):
                setattr(self.dual_config, key, value)
                logger.info(f"Updated dual brain config: {key}={value}")
            else:
                logger.warning(f"Unknown dual brain config key: {key}")

    def get_complexity_score(self, prompt: str) -> float:
        """
        Get the complexity score for a prompt without processing it.
        
        Useful for debugging and understanding mode selection.
        """
        return self._detect_complexity(prompt)