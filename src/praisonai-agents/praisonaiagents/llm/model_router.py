"""
Model Router for intelligent model selection based on task characteristics.

This module provides functionality to automatically select the most appropriate
LLM model/provider based on task complexity, cost considerations, and model capabilities.
"""

import os
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import IntEnum

logger = logging.getLogger(__name__)


class TaskComplexity(IntEnum):
    """Enum for task complexity levels"""
    SIMPLE = 1          # Basic queries, math, factual questions
    MODERATE = 2        # Summarization, basic analysis
    COMPLEX = 3         # Code generation, deep reasoning
    VERY_COMPLEX = 4    # Multi-step reasoning, complex analysis


@dataclass
class ModelProfile:
    """Profile for an LLM model with its characteristics"""
    name: str
    provider: str
    complexity_range: Tuple[TaskComplexity, TaskComplexity]
    cost_per_1k_tokens: float  # Average of input/output costs
    strengths: List[str]
    capabilities: List[str]
    context_window: int
    supports_tools: bool = True
    supports_streaming: bool = True


class ModelRouter:
    """
    Intelligent model router that selects the best model based on task requirements.
    
    This router implements a strategy pattern for model selection, considering:
    - Task complexity
    - Cost optimization
    - Model capabilities
    - Specific strengths for different task types
    """
    
    # Default model profiles - can be customized via configuration
    DEFAULT_MODELS = [
        # Lightweight/cheap models for simple tasks
        ModelProfile(
            name="gpt-4o-mini",
            provider="openai",
            complexity_range=(TaskComplexity.SIMPLE, TaskComplexity.MODERATE),
            cost_per_1k_tokens=0.00075,  # Average of $0.00015 input, $0.0006 output
            strengths=["speed", "cost-effective", "basic-reasoning"],
            capabilities=["text", "function-calling"],
            context_window=128000
        ),
        ModelProfile(
            name="gemini/gemini-1.5-flash",
            provider="google",
            complexity_range=(TaskComplexity.SIMPLE, TaskComplexity.MODERATE),
            cost_per_1k_tokens=0.000125,  # Very cost-effective
            strengths=["speed", "cost-effective", "multimodal"],
            capabilities=["text", "vision", "function-calling"],
            context_window=1048576
        ),
        ModelProfile(
            name="claude-3-haiku-20240307",
            provider="anthropic",
            complexity_range=(TaskComplexity.SIMPLE, TaskComplexity.MODERATE),
            cost_per_1k_tokens=0.0008,  # Average of $0.00025 input, $0.00125 output
            strengths=["speed", "instruction-following"],
            capabilities=["text", "function-calling"],
            context_window=200000
        ),
        
        # Mid-tier models for moderate complexity
        ModelProfile(
            name="gpt-4o",
            provider="openai",
            complexity_range=(TaskComplexity.MODERATE, TaskComplexity.COMPLEX),
            cost_per_1k_tokens=0.0075,  # Average of $0.0025 input, $0.01 output
            strengths=["reasoning", "code-generation", "general-purpose"],
            capabilities=["text", "vision", "function-calling"],
            context_window=128000
        ),
        ModelProfile(
            name="claude-3-5-sonnet-20241022",
            provider="anthropic",
            complexity_range=(TaskComplexity.MODERATE, TaskComplexity.VERY_COMPLEX),
            cost_per_1k_tokens=0.009,  # Average of $0.003 input, $0.015 output
            strengths=["reasoning", "code-generation", "analysis", "writing"],
            capabilities=["text", "vision", "function-calling"],
            context_window=200000
        ),
        
        # High-end models for complex tasks
        ModelProfile(
            name="gemini/gemini-1.5-pro",
            provider="google",
            complexity_range=(TaskComplexity.COMPLEX, TaskComplexity.VERY_COMPLEX),
            cost_per_1k_tokens=0.00625,  # Average of $0.00125 input, $0.005 output
            strengths=["reasoning", "long-context", "multimodal"],
            capabilities=["text", "vision", "function-calling"],
            context_window=2097152  # 2M context
        ),
        ModelProfile(
            name="claude-3-opus-20240229",
            provider="anthropic",
            complexity_range=(TaskComplexity.COMPLEX, TaskComplexity.VERY_COMPLEX),
            cost_per_1k_tokens=0.045,  # Average of $0.015 input, $0.075 output
            strengths=["deep-reasoning", "complex-analysis", "creative-writing"],
            capabilities=["text", "vision", "function-calling"],
            context_window=200000
        ),
        ModelProfile(
            name="deepseek-chat",
            provider="deepseek",
            complexity_range=(TaskComplexity.COMPLEX, TaskComplexity.VERY_COMPLEX),
            cost_per_1k_tokens=0.0014,  # Very cost-effective for capability
            strengths=["reasoning", "code-generation", "mathematics"],
            capabilities=["text", "function-calling"],
            context_window=128000
        ),
    ]
    
    def __init__(
        self,
        models: Optional[List[ModelProfile]] = None,
        default_model: Optional[str] = None,
        cost_threshold: Optional[float] = None,
        preferred_providers: Optional[List[str]] = None
    ):
        """
        Initialize the ModelRouter.
        
        Args:
            models: Custom list of model profiles to use
            default_model: Default model to use if no suitable model found
            cost_threshold: Maximum cost per 1k tokens to consider
            preferred_providers: List of preferred providers in order
        """
        self.models = models or self.DEFAULT_MODELS
        self.default_model = default_model or os.getenv('OPENAI_MODEL_NAME', 'gpt-4o')
        self.cost_threshold = cost_threshold
        self.preferred_providers = preferred_providers or []
        
        # Build lookup indices for efficient access
        self._model_by_name = {m.name: m for m in self.models}
        self._models_by_complexity = self._build_complexity_index()
        
    def _build_complexity_index(self) -> Dict[TaskComplexity, List[ModelProfile]]:
        """Build an index of models by complexity level"""
        index = {level: [] for level in TaskComplexity}
        
        for model in self.models:
            min_complexity, max_complexity = model.complexity_range
            for level in TaskComplexity:
                if min_complexity.value <= level.value <= max_complexity.value:
                    index[level].append(model)
        
        return index
    
    def analyze_task_complexity(
        self,
        task_description: str,
        tools_required: Optional[List[str]] = None,
        context_size: Optional[int] = None
    ) -> TaskComplexity:
        """
        Analyze task description to determine complexity level.
        
        This is a simple heuristic-based approach. In production, this could be
        replaced with a more sophisticated ML-based classifier.
        """
        description_lower = task_description.lower()
        
        # Keywords indicating different complexity levels
        simple_keywords = [
            "calculate", "compute", "what is", "define", "list", "count",
            "simple", "basic", "check", "verify", "yes or no", "true or false"
        ]
        
        moderate_keywords = [
            "summarize", "explain", "compare", "describe", "analyze briefly",
            "find", "search", "extract", "classify", "categorize"
        ]
        
        complex_keywords = [
            "implement", "code", "develop", "design", "create algorithm",
            "optimize", "debug", "refactor", "architect", "solve"
        ]
        
        very_complex_keywords = [
            "multi-step", "comprehensive analysis", "deep dive", "research",
            "strategic", "framework", "system design", "proof", "theorem"
        ]
        
        # Check for keyword matches
        if any(keyword in description_lower for keyword in very_complex_keywords):
            return TaskComplexity.VERY_COMPLEX
        elif any(keyword in description_lower for keyword in complex_keywords):
            return TaskComplexity.COMPLEX
        elif any(keyword in description_lower for keyword in moderate_keywords):
            return TaskComplexity.MODERATE
        elif any(keyword in description_lower for keyword in simple_keywords):
            return TaskComplexity.SIMPLE
        
        # Consider tool requirements
        if tools_required and len(tools_required) > 3:
            return TaskComplexity.COMPLEX
        
        # Consider context size requirements
        if context_size and context_size > 50000:
            return TaskComplexity.COMPLEX
        
        # Default to moderate
        return TaskComplexity.MODERATE
    
    def select_model(
        self,
        task_description: str,
        required_capabilities: Optional[List[str]] = None,
        tools_required: Optional[List[str]] = None,
        context_size: Optional[int] = None,
        budget_conscious: bool = True
    ) -> str:
        """
        Select the most appropriate model for a given task.
        
        Args:
            task_description: Description of the task to perform
            required_capabilities: List of required capabilities (e.g., ["vision", "function-calling"])
            tools_required: List of tools that will be used
            context_size: Estimated context size needed
            budget_conscious: Whether to optimize for cost
            
        Returns:
            Model name string to use
        """
        # Analyze task complexity
        complexity = self.analyze_task_complexity(task_description, tools_required, context_size)
        
        # Get candidate models for this complexity level
        candidates = self._models_by_complexity.get(complexity, [])
        
        if not candidates:
            logger.warning(f"No models found for complexity {complexity}, using default")
            return self.default_model
        
        # Filter by required capabilities
        if required_capabilities:
            candidates = [
                m for m in candidates
                if all(cap in m.capabilities for cap in required_capabilities)
            ]
        
        # Filter by tool support if needed
        if tools_required:
            candidates = [m for m in candidates if m.supports_tools]
        
        # Filter by context window if specified
        if context_size:
            candidates = [m for m in candidates if m.context_window >= context_size]
        
        # Filter by cost threshold if specified
        if self.cost_threshold:
            candidates = [m for m in candidates if m.cost_per_1k_tokens <= self.cost_threshold]
        
        if not candidates:
            logger.warning("No models meet all criteria, using default")
            return self.default_model
        
        # Sort by selection criteria
        if budget_conscious:
            # Sort by cost (ascending)
            candidates.sort(key=lambda m: m.cost_per_1k_tokens)
        else:
            # Sort by capability (descending complexity)
            candidates.sort(key=lambda m: m.complexity_range[1].value, reverse=True)
        
        # Apply provider preferences
        if self.preferred_providers:
            for provider in self.preferred_providers:
                for model in candidates:
                    if model.provider == provider:
                        logger.info(f"Selected model: {model.name} (complexity: {complexity}, cost: ${model.cost_per_1k_tokens}/1k tokens)")
                        return model.name
        
        # Return the best candidate
        selected = candidates[0]
        logger.info(f"Selected model: {selected.name} (complexity: {complexity}, cost: ${selected.cost_per_1k_tokens}/1k tokens)")
        return selected.name
    
    def get_model_info(self, model_name: str) -> Optional[ModelProfile]:
        """Get profile information for a specific model"""
        return self._model_by_name.get(model_name)
    
    def estimate_cost(self, model_name: str, estimated_tokens: int) -> float:
        """Estimate the cost for a given model and token count"""
        model = self._model_by_name.get(model_name)
        if not model:
            return 0.0
        return (model.cost_per_1k_tokens * estimated_tokens) / 1000


def create_routing_agent(
    models: Optional[List[str]] = None,
    router: Optional[ModelRouter] = None,
    **agent_kwargs
) -> 'Agent':
    """
    Create a specialized routing agent that can select models dynamically.
    
    Args:
        models: List of model names to route between
        router: Custom ModelRouter instance
        **agent_kwargs: Additional arguments to pass to Agent constructor
        
    Returns:
        Agent configured for model routing
    """
    from ..agent import Agent
    
    if not router:
        router = ModelRouter()
    
    routing_agent = Agent(
        name=agent_kwargs.pop('name', 'ModelRouter'),
        role=agent_kwargs.pop('role', 'Intelligent Model Router'),
        goal=agent_kwargs.pop('goal', 'Select the most appropriate AI model based on task requirements'),
        backstory=agent_kwargs.pop('backstory', 
            'I analyze tasks and route them to the most suitable AI model, '
            'optimizing for performance, cost, and capability requirements.'
        ),
        **agent_kwargs
    )
    
    # TODO: Consider creating a proper RoutingAgent subclass instead of setting private attributes
    # For now, store the router on the agent for use in execution
    routing_agent._model_router = router
    routing_agent._available_models = models or [m.name for m in router.models]
    
    return routing_agent