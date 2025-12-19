"""
Router Handler for CLI.

Provides smart model selection based on task complexity.
Usage: praisonai "Complex task" --router

Supports custom model configuration from agents.yaml/workflow.yaml:

models:
  gpt-4o-mini:
    provider: openai
    complexity: [simple, moderate]
    cost_per_1k: 0.00075
    capabilities: [text, function-calling]
"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import IntEnum
from .base import FlagHandler


class TaskComplexity(IntEnum):
    """Enum for task complexity levels."""
    SIMPLE = 1
    MODERATE = 2
    COMPLEX = 3
    VERY_COMPLEX = 4


@dataclass
class ModelProfile:
    """Profile for an LLM model with its characteristics."""
    name: str
    provider: str
    complexity_range: Tuple[TaskComplexity, TaskComplexity]
    cost_per_1k_tokens: float
    capabilities: List[str]
    context_window: int = 128000
    supports_tools: bool = True
    supports_streaming: bool = True
    strengths: Optional[List[str]] = None


class RouterHandler(FlagHandler):
    """
    Handler for --router flag.
    
    Automatically selects the best model based on task complexity.
    
    Example:
        praisonai "Simple question" --router
        praisonai "Complex analysis" --router
    """
    
    # Default model tiers for routing (used when no custom models configured)
    # Note: Use full model names for API compatibility
    DEFAULT_MODEL_TIERS = {
        'simple': ['gpt-4o-mini', 'anthropic/claude-3-haiku-20240307', 'gemini/gemini-1.5-flash'],
        'medium': ['gpt-4o', 'anthropic/claude-3-5-sonnet-20241022', 'gemini/gemini-1.5-pro'],
        'complex': ['gpt-4-turbo', 'anthropic/claude-3-opus-20240229', 'o1-preview'],
    }
    
    # Default model profiles
    DEFAULT_MODELS: List[ModelProfile] = [
        ModelProfile(
            name="gpt-4o-mini",
            provider="openai",
            complexity_range=(TaskComplexity.SIMPLE, TaskComplexity.MODERATE),
            cost_per_1k_tokens=0.00075,
            capabilities=["text", "function-calling"],
            context_window=128000
        ),
        ModelProfile(
            name="gpt-4o",
            provider="openai",
            complexity_range=(TaskComplexity.MODERATE, TaskComplexity.COMPLEX),
            cost_per_1k_tokens=0.0075,
            capabilities=["text", "vision", "function-calling"],
            context_window=128000
        ),
        ModelProfile(
            name="anthropic/claude-3-haiku-20240307",
            provider="anthropic",
            complexity_range=(TaskComplexity.SIMPLE, TaskComplexity.MODERATE),
            cost_per_1k_tokens=0.0008,
            capabilities=["text", "function-calling"],
            context_window=200000
        ),
        ModelProfile(
            name="anthropic/claude-3-5-sonnet-20241022",
            provider="anthropic",
            complexity_range=(TaskComplexity.MODERATE, TaskComplexity.VERY_COMPLEX),
            cost_per_1k_tokens=0.009,
            capabilities=["text", "vision", "function-calling"],
            context_window=200000,
            strengths=["reasoning", "code-generation", "analysis"]
        ),
        ModelProfile(
            name="gemini/gemini-1.5-flash",
            provider="google",
            complexity_range=(TaskComplexity.SIMPLE, TaskComplexity.MODERATE),
            cost_per_1k_tokens=0.000125,
            capabilities=["text", "vision", "function-calling"],
            context_window=1048576
        ),
        ModelProfile(
            name="gemini/gemini-1.5-pro",
            provider="google",
            complexity_range=(TaskComplexity.COMPLEX, TaskComplexity.VERY_COMPLEX),
            cost_per_1k_tokens=0.00625,
            capabilities=["text", "vision", "function-calling"],
            context_window=2097152
        ),
    ]
    
    def __init__(self, verbose: bool = False):
        """Initialize RouterHandler with model routing support."""
        super().__init__(verbose=verbose)
        self._model_router: Optional[List[ModelProfile]] = None
        self._custom_models: Dict[str, ModelProfile] = {}
        self._cost_threshold: Optional[float] = None
        self._model_tiers = self.DEFAULT_MODEL_TIERS.copy()
    
    @property
    def model_router(self) -> List[ModelProfile]:
        """Get the list of available model profiles."""
        if self._model_router is None:
            return self.DEFAULT_MODELS.copy()
        return self._model_router
    
    @property
    def feature_name(self) -> str:
        return "router"
    
    @property
    def flag_name(self) -> str:
        return "router"
    
    @property
    def flag_help(self) -> str:
        return "Auto-select best model based on task complexity"
    
    def check_dependencies(self) -> Tuple[bool, str]:
        """Router is built-in, always available."""
        return True, ""
    
    def analyze_complexity(self, prompt: str) -> str:
        """
        Analyze prompt complexity.
        
        Args:
            prompt: The task prompt
            
        Returns:
            Complexity level: 'simple', 'medium', or 'complex'
        """
        # Simple heuristics for complexity
        prompt_lower = prompt.lower()
        word_count = len(prompt.split())
        
        # Complex indicators
        complex_keywords = [
            'analyze', 'research', 'comprehensive', 'detailed',
            'compare', 'evaluate', 'synthesize', 'multi-step',
            'code review', 'architecture', 'design pattern',
            'optimize', 'debug', 'refactor'
        ]
        
        # Simple indicators
        simple_keywords = [
            'what is', 'define', 'list', 'name', 'when',
            'where', 'who', 'simple', 'quick', 'brief'
        ]
        
        complex_count = sum(1 for kw in complex_keywords if kw in prompt_lower)
        simple_count = sum(1 for kw in simple_keywords if kw in prompt_lower)
        
        # Determine complexity
        if complex_count >= 2 or word_count > 100:
            return 'complex'
        elif simple_count >= 2 or word_count < 20:
            return 'simple'
        else:
            return 'medium'
    
    def select_model(self, prompt: str, preferred_provider: str = None) -> str:
        """
        Select the best model for the prompt.
        
        Args:
            prompt: The task prompt
            preferred_provider: Optional preferred provider (openai, anthropic, google)
            
        Returns:
            Selected model name
        """
        complexity = self.analyze_complexity(prompt)
        
        # If custom models are loaded, use ModelProfile-based selection
        if self._custom_models:
            return self._select_from_profiles(prompt, complexity, preferred_provider)
        
        # Otherwise use tier-based selection
        models = self._model_tiers.get(complexity, self._model_tiers['medium'])
        
        # Filter by provider if specified
        if preferred_provider:
            provider_prefixes = {
                'openai': ['gpt-', 'o1-'],
                'anthropic': ['anthropic/', 'claude-'],
                'google': ['gemini/', 'gemini-']
            }
            prefixes = provider_prefixes.get(preferred_provider.lower(), [])
            filtered = [m for m in models if any(p in m for p in prefixes)]
            if filtered:
                models = filtered
        
        # Apply cost threshold if set
        if self._cost_threshold:
            filtered = [m for m in models if self.get_model_cost(m) <= self._cost_threshold]
            if filtered:
                models = filtered
        
        selected = models[0] if models else 'gpt-4o-mini'
        
        self.print_status(f"🎯 Task complexity: {complexity}", "info")
        self.print_status(f"🤖 Selected model: {selected}", "success")
        
        return selected
    
    def _select_from_profiles(
        self, 
        prompt: str, 
        complexity: str, 
        preferred_provider: str = None
    ) -> str:
        """Select model from custom ModelProfile objects."""
        # Map string complexity to TaskComplexity enum
        complexity_map = {
            'simple': TaskComplexity.SIMPLE,
            'medium': TaskComplexity.MODERATE,
            'complex': TaskComplexity.COMPLEX,
        }
        task_complexity = complexity_map.get(complexity, TaskComplexity.MODERATE)
        
        # Get all models that support this complexity level
        candidates = []
        for name, profile in self._custom_models.items():
            min_c, max_c = profile.complexity_range
            if min_c.value <= task_complexity.value <= max_c.value:
                candidates.append(profile)
        
        if not candidates:
            return 'gpt-4o-mini'
        
        # Filter by provider if specified
        if preferred_provider:
            filtered = [m for m in candidates if m.provider == preferred_provider]
            if filtered:
                candidates = filtered
        
        # Filter by cost threshold if set
        if self._cost_threshold:
            filtered = [m for m in candidates if m.cost_per_1k_tokens <= self._cost_threshold]
            if filtered:
                candidates = filtered
        
        # Sort by cost (cheapest first)
        candidates.sort(key=lambda m: m.cost_per_1k_tokens)
        
        return candidates[0].name if candidates else 'gpt-4o-mini'
    
    def apply_to_agent_config(self, config: Dict[str, Any], flag_value: Any) -> Dict[str, Any]:
        """
        Apply router configuration.
        
        Args:
            config: Agent configuration dictionary
            flag_value: Boolean or dict with provider preference
            
        Returns:
            Modified configuration with selected model
        """
        if not flag_value:
            return config
        
        # Get prompt from config if available
        prompt = config.get('prompt', config.get('goal', ''))
        
        preferred_provider = None
        if isinstance(flag_value, dict):
            preferred_provider = flag_value.get('provider')
        
        if prompt:
            selected_model = self.select_model(prompt, preferred_provider)
            config['llm'] = selected_model
        
        config['use_router'] = True
        return config
    
    def execute(self, prompt: str = None, provider: str = None, **kwargs) -> str:
        """
        Execute model selection.
        
        Args:
            prompt: Task prompt
            provider: Preferred provider
            
        Returns:
            Selected model name
        """
        if not prompt:
            return 'gpt-4o-mini'  # Default
        
        return self.select_model(prompt, provider)
    
    # =========================================================================
    # Custom Model Configuration Methods
    # =========================================================================
    
    def yaml_to_model_profile(self, name: str, config: Dict[str, Any]) -> ModelProfile:
        """
        Convert YAML model configuration to ModelProfile object.
        
        Args:
            name: Model name
            config: Model configuration from YAML
            
        Returns:
            ModelProfile object
        """
        # Parse complexity strings to TaskComplexity enum
        complexity_list = config.get('complexity', ['moderate'])
        complexity_map = {
            'simple': TaskComplexity.SIMPLE,
            'moderate': TaskComplexity.MODERATE,
            'complex': TaskComplexity.COMPLEX,
            'very_complex': TaskComplexity.VERY_COMPLEX,
        }
        
        complexities = [complexity_map.get(c.lower(), TaskComplexity.MODERATE) for c in complexity_list]
        min_complexity = min(complexities, key=lambda x: x.value)
        max_complexity = max(complexities, key=lambda x: x.value)
        
        return ModelProfile(
            name=name,
            provider=config.get('provider', 'unknown'),
            complexity_range=(min_complexity, max_complexity),
            cost_per_1k_tokens=config.get('cost_per_1k', 0.001),
            capabilities=config.get('capabilities', ['text']),
            context_window=config.get('context_window', 128000),
            supports_tools=config.get('supports_tools', True),
            supports_streaming=config.get('supports_streaming', True),
            strengths=config.get('strengths', None)
        )
    
    def load_models_from_config(
        self, 
        models_config: Dict[str, Dict[str, Any]], 
        merge_with_defaults: bool = False
    ) -> None:
        """
        Load custom models from YAML configuration.
        
        Args:
            models_config: Dictionary of model configurations from YAML
            merge_with_defaults: If True, merge with default models
        """
        # Start with defaults if merging
        if merge_with_defaults:
            for profile in self.DEFAULT_MODELS:
                self._custom_models[profile.name] = profile
        
        # Add custom models
        for name, config in models_config.items():
            profile = self.yaml_to_model_profile(name, config)
            self._custom_models[name] = profile
        
        # Rebuild model tiers from profiles
        self._rebuild_model_tiers()
    
    def _rebuild_model_tiers(self) -> None:
        """Rebuild MODEL_TIERS from custom model profiles."""
        self._model_tiers = {
            'simple': [],
            'medium': [],
            'complex': [],
        }
        
        for name, profile in self._custom_models.items():
            min_c, max_c = profile.complexity_range
            
            if min_c.value <= TaskComplexity.SIMPLE.value <= max_c.value:
                self._model_tiers['simple'].append(name)
            if min_c.value <= TaskComplexity.MODERATE.value <= max_c.value:
                self._model_tiers['medium'].append(name)
            if min_c.value <= TaskComplexity.COMPLEX.value <= max_c.value:
                self._model_tiers['complex'].append(name)
        
        # Sort by cost (cheapest first)
        for tier in self._model_tiers:
            self._model_tiers[tier].sort(
                key=lambda n: self._custom_models[n].cost_per_1k_tokens
            )
    
    def get_available_models(self) -> List[str]:
        """
        Get list of available model names.
        
        Returns:
            List of model names
        """
        if self._custom_models:
            return list(self._custom_models.keys())
        return [p.name for p in self.DEFAULT_MODELS]
    
    def get_model_cost(self, model_name: str) -> float:
        """
        Get cost per 1k tokens for a model.
        
        Args:
            model_name: Name of the model
            
        Returns:
            Cost per 1k tokens
        """
        # Check custom models first
        if model_name in self._custom_models:
            return self._custom_models[model_name].cost_per_1k_tokens
        
        # Check default models
        for profile in self.DEFAULT_MODELS:
            if profile.name == model_name:
                return profile.cost_per_1k_tokens
        
        # Default cost for unknown models
        return 0.01
    
    def set_cost_threshold(self, threshold: float) -> None:
        """
        Set maximum cost per 1k tokens for model selection.
        
        Args:
            threshold: Maximum cost per 1k tokens
        """
        self._cost_threshold = threshold
    
    def get_model_profile(self, model_name: str) -> Optional[ModelProfile]:
        """
        Get ModelProfile for a model.
        
        Args:
            model_name: Name of the model
            
        Returns:
            ModelProfile or None if not found
        """
        if model_name in self._custom_models:
            return self._custom_models[model_name]
        
        for profile in self.DEFAULT_MODELS:
            if profile.name == model_name:
                return profile
        
        return None
