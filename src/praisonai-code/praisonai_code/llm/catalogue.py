"""
Model catalogue for discovering and validating LLM models.

Provides model metadata, capabilities, and validation with litellm integration
and graceful fallback when litellm is not available.
"""

import os
import json
import time
import difflib
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class ModelInfo:
    """Model metadata and capabilities."""
    id: str
    provider: str
    description: Optional[str] = None
    max_context: Optional[int] = None
    max_output: Optional[int] = None
    input_cost: Optional[float] = None  # Cost per 1K input tokens
    output_cost: Optional[float] = None  # Cost per 1K output tokens
    supports_tools: bool = False
    supports_vision: bool = False
    supports_reasoning: bool = False
    supports_streaming: bool = True
    notes: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


# Fallback models when litellm is not available
FALLBACK_MODELS = [
    # OpenAI
    ModelInfo(
        id="gpt-4o",
        provider="openai",
        description="Most capable GPT-4 model, multimodal",
        max_context=128000,
        max_output=16384,
        supports_tools=True,
        supports_vision=True,
        supports_reasoning=True,
    ),
    ModelInfo(
        id="gpt-4o-mini",
        provider="openai",
        description="Affordable small model for fast tasks",
        max_context=128000,
        max_output=16384,
        supports_tools=True,
        supports_vision=True,
    ),
    ModelInfo(
        id="gpt-3.5-turbo",
        provider="openai",
        description="Fast, affordable model for simple tasks",
        max_context=16385,
        max_output=4096,
        supports_tools=True,
    ),
    ModelInfo(
        id="o1",
        provider="openai",
        description="Advanced reasoning model",
        max_context=200000,
        max_output=100000,
        supports_reasoning=True,
        supports_tools=False,
        supports_streaming=False,
        notes="No streaming, tools, or system messages",
    ),
    ModelInfo(
        id="o1-mini",
        provider="openai",
        description="Faster reasoning model",
        max_context=128000,
        max_output=65536,
        supports_reasoning=True,
        supports_tools=False,
        supports_streaming=False,
        notes="No streaming, tools, or system messages",
    ),
    
    # Anthropic
    ModelInfo(
        id="claude-3-5-sonnet-latest",
        provider="anthropic",
        description="Most intelligent Claude model",
        max_context=200000,
        max_output=8192,
        supports_tools=True,
        supports_vision=True,
        supports_reasoning=True,
    ),
    ModelInfo(
        id="claude-3-5-haiku-latest",
        provider="anthropic",
        description="Fast and affordable Claude model",
        max_context=200000,
        max_output=8192,
        supports_tools=True,
        supports_vision=True,
    ),
    ModelInfo(
        id="claude-3-opus-latest",
        provider="anthropic",
        description="Powerful model for complex tasks",
        max_context=200000,
        max_output=4096,
        supports_tools=True,
        supports_vision=True,
        supports_reasoning=True,
    ),
    
    # Google
    ModelInfo(
        id="gemini-1.5-pro",
        provider="google",
        description="Advanced multimodal model",
        max_context=2000000,
        max_output=8192,
        supports_tools=True,
        supports_vision=True,
        supports_reasoning=True,
    ),
    ModelInfo(
        id="gemini-1.5-flash",
        provider="google",
        description="Fast multimodal model",
        max_context=1000000,
        max_output=8192,
        supports_tools=True,
        supports_vision=True,
    ),
    ModelInfo(
        id="gemini-2.0-flash-exp",
        provider="google",
        description="Experimental next-gen model",
        max_context=1000000,
        max_output=8192,
        supports_tools=True,
        supports_vision=True,
        supports_reasoning=True,
    ),
    
    # Groq
    ModelInfo(
        id="llama-3.3-70b-versatile",
        provider="groq",
        description="Latest Llama model, very fast",
        max_context=128000,
        max_output=32768,
        supports_tools=True,
    ),
    ModelInfo(
        id="mixtral-8x7b-32768",
        provider="groq",
        description="Fast MoE model",
        max_context=32768,
        max_output=32768,
        supports_tools=True,
    ),
    
    # Ollama (local)
    ModelInfo(
        id="llama3.2",
        provider="ollama",
        description="Local Llama model",
        max_context=128000,
        supports_tools=True,
        notes="Requires Ollama running locally",
    ),
]


class ModelCatalogue:
    """
    Model catalogue with litellm integration and caching.
    """
    
    def __init__(self, cache_dir: Optional[Path] = None, cache_ttl: int = 3600):
        """
        Initialize model catalogue.
        
        Args:
            cache_dir: Directory for caching model data
            cache_ttl: Cache TTL in seconds (default: 1 hour)
        """
        self.cache_dir = cache_dir or Path.home() / ".praison" / "cache"
        self.cache_file = self.cache_dir / "models.json"
        self.cache_ttl = cache_ttl
        self._models: Optional[List[ModelInfo]] = None
    
    def _load_from_litellm(self) -> Optional[List[ModelInfo]]:
        """
        Load model information from litellm if available.
        
        Returns:
            List of ModelInfo objects or None if litellm not available
        """
        try:
            import litellm
            
            models = []
            
            # Get model cost data (includes context limits and pricing)
            cost_data = {}
            if hasattr(litellm, 'model_cost') and litellm.model_cost:
                cost_data = litellm.model_cost
            
            # Process known models from litellm
            # model_list is a list attribute, not a callable
            model_ids = getattr(litellm, 'model_list', [])
            for model_id in model_ids:
                # Determine provider from model ID
                provider = "unknown"
                if model_id.startswith(("gpt-", "o1", "text-", "davinci", "curie", "babbage", "ada")):
                    provider = "openai"
                elif model_id.startswith(("claude-", "anthropic/")):
                    provider = "anthropic"
                elif model_id.startswith(("gemini-", "google/", "palm-")):
                    provider = "google"
                elif model_id.startswith("groq/"):
                    provider = "groq"
                elif model_id.startswith("ollama/"):
                    provider = "ollama"
                elif model_id.startswith("cohere/"):
                    provider = "cohere"
                elif "/" in model_id:
                    provider = model_id.split("/")[0]
                
                # Get cost and context info
                info = cost_data.get(model_id, {})
                
                # Determine capabilities (heuristics based on model name)
                supports_tools = not any(x in model_id for x in ["o1", "embedding", "whisper", "tts", "dall-e"])
                supports_vision = any(x in model_id for x in ["vision", "gpt-4o", "gemini", "claude-3"])
                supports_reasoning = any(x in model_id for x in ["o1", "gpt-4o", "claude-3-5", "gemini-2"])
                
                models.append(ModelInfo(
                    id=model_id,
                    provider=provider,
                    max_context=info.get("max_tokens") or info.get("max_input_tokens"),
                    max_output=info.get("max_output_tokens"),
                    input_cost=info.get("input_cost_per_token") * 1000 if info.get("input_cost_per_token") is not None else None,
                    output_cost=info.get("output_cost_per_token") * 1000 if info.get("output_cost_per_token") is not None else None,
                    supports_tools=supports_tools,
                    supports_vision=supports_vision,
                    supports_reasoning=supports_reasoning,
                ))
            
            # Merge with fallback models to ensure completeness
            model_ids = {m.id for m in models}
            for fallback in FALLBACK_MODELS:
                if fallback.id not in model_ids:
                    models.append(fallback)
            
            return models
            
        except ImportError:
            # litellm not available
            return None
        except Exception:
            # Error loading from litellm, fall back
            return None
    
    def _load_from_cache(self) -> Optional[List[ModelInfo]]:
        """
        Load models from cache if valid.
        
        Returns:
            List of ModelInfo objects or None if cache invalid/missing
        """
        if not self.cache_file.exists():
            return None
        
        try:
            # Check cache age
            cache_age = time.time() - self.cache_file.stat().st_mtime
            if cache_age > self.cache_ttl:
                return None
            
            # Load cache
            with open(self.cache_file, 'r') as f:
                data = json.load(f)
            
            models = []
            for item in data.get("models", []):
                models.append(ModelInfo(**item))
            
            return models
            
        except Exception:
            return None
    
    def _save_to_cache(self, models: List[ModelInfo]) -> None:
        """Save models to cache."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            
            data = {
                "timestamp": time.time(),
                "models": [m.to_dict() for m in models],
            }
            
            with open(self.cache_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception:
            # Ignore cache write errors
            pass
    
    def _get_models(self) -> List[ModelInfo]:
        """
        Get models from cache, litellm, or fallback.
        
        Returns:
            List of available models
        """
        if self._models is not None:
            return self._models
        
        # Try cache first
        models = self._load_from_cache()
        
        # Try litellm if cache miss
        if models is None:
            models = self._load_from_litellm()
            
            # Save to cache if loaded from litellm
            if models:
                self._save_to_cache(models)
        
        # Fall back to static list
        if models is None:
            models = FALLBACK_MODELS
        
        self._models = models
        return models
    
    def list_models(
        self,
        provider: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List available models.
        
        Args:
            provider: Filter by provider name
            search: Filter by model ID pattern
            
        Returns:
            List of model dictionaries
        """
        models = self._get_models()
        
        # Apply filters
        if provider:
            models = [m for m in models if m.provider.lower() == provider.lower()]
        
        if search:
            search_lower = search.lower()
            models = [m for m in models if search_lower in m.id.lower()]
        
        return [m.to_dict() for m in models]
    
    def describe_model(self, model_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information for a model.
        
        Args:
            model_id: Model ID to describe
            
        Returns:
            Model info dictionary or None if not found
        """
        models = self._get_models()
        
        # Find exact match first
        for model in models:
            if model.id == model_id:
                return model.to_dict()
        
        # Try case-insensitive match
        model_id_lower = model_id.lower()
        for model in models:
            if model.id.lower() == model_id_lower:
                return model.to_dict()
        
        # Try provider-qualified IDs (e.g. "groq/llama-3.3-70b-versatile")
        # against bare IDs stored in the fallback catalogue.
        if "/" in model_id_lower:
            requested_provider, requested_bare = model_id_lower.split("/", 1)
            for model in models:
                if (
                    model.provider.lower() == requested_provider
                    and model.id.lower() == requested_bare
                ):
                    return model.to_dict()
        
        return None
    
    def is_valid_model(self, model_id: str) -> bool:
        """
        Check if a model ID is valid.
        
        Args:
            model_id: Model ID to validate
            
        Returns:
            True if valid, False otherwise
        """
        return self.describe_model(model_id) is not None
    
    def get_suggestions(self, model_id: str, max_suggestions: int = 5) -> List[str]:
        """
        Get model ID suggestions for a potentially misspelled ID.
        
        Args:
            model_id: Model ID that might be misspelled
            max_suggestions: Maximum number of suggestions
            
        Returns:
            List of suggested model IDs
        """
        models = self._get_models()
        all_ids = [m.id for m in models]
        
        # Use difflib to find close matches
        suggestions = difflib.get_close_matches(
            model_id,
            all_ids,
            n=max_suggestions,
            cutoff=0.6
        )
        
        return suggestions
    
    def validate_model(self, model_id: str) -> str:
        """
        Validate a model ID and return the normalized ID.
        
        Args:
            model_id: Model ID to validate
            
        Returns:
            Normalized model ID
            
        Raises:
            ValueError: If model ID is invalid with suggestions
        """
        # Check if valid (single lookup); return the correctly cased ID
        info = self.describe_model(model_id)
        if info:
            return info["id"]
        
        # Invalid - provide suggestions
        suggestions = self.get_suggestions(model_id)
        
        if suggestions:
            suggestion_text = "Did you mean: " + ", ".join(suggestions[:3])
            raise ValueError(f"Unknown model '{model_id}'. {suggestion_text}")
        else:
            raise ValueError(f"Unknown model '{model_id}'")