"""
PraisonAI Recipe Module

Provides a minimal, client-friendly API for running Agent Recipes.
All imports are lazy to ensure zero performance impact on Core SDK.

Usage:
    from praisonai import recipe
    result = recipe.run("support-reply-drafter", input={"ticket": "T-123"})
    
    # Or with streaming
    for event in recipe.run_stream("transcript-generator", input="audio.mp3"):
        print(event)
"""

__all__ = [
    # Core API
    "run",
    "run_stream",
    "validate",
    "list_recipes",
    "describe",
    # Runtime Bridge API
    "resolve",
    "run_background",
    "submit_job",
    "schedule",
    # Data classes
    "RecipeResult",
    "RecipeEvent",
    "RecipeConfig",
    "ResolvedRecipe",
    "RuntimeConfig",
    # Exceptions
    "RecipeError",
    "RecipeNotFoundError",
    "RecipeDependencyError",
    "RecipePolicyError",
    "RecipeValidationError",
    # Exit codes
    "ExitCode",
]

# Lazy loading implementation
_module_cache = {}


def __getattr__(name):
    """Lazy load recipe components."""
    if name in _module_cache:
        return _module_cache[name]
    
    if name == "run":
        from .core import run
        _module_cache[name] = run
        return run
    elif name == "run_stream":
        from .core import run_stream
        _module_cache[name] = run_stream
        return run_stream
    elif name == "validate":
        from .core import validate
        _module_cache[name] = validate
        return validate
    elif name == "list_recipes":
        from .core import list_recipes
        _module_cache[name] = list_recipes
        return list_recipes
    elif name == "describe":
        from .core import describe
        _module_cache[name] = describe
        return describe
    elif name == "RecipeResult":
        from .models import RecipeResult
        _module_cache[name] = RecipeResult
        return RecipeResult
    elif name == "RecipeEvent":
        from .models import RecipeEvent
        _module_cache[name] = RecipeEvent
        return RecipeEvent
    elif name == "RecipeConfig":
        from .models import RecipeConfig
        _module_cache[name] = RecipeConfig
        return RecipeConfig
    elif name == "RecipeError":
        from .exceptions import RecipeError
        _module_cache[name] = RecipeError
        return RecipeError
    elif name == "RecipeNotFoundError":
        from .exceptions import RecipeNotFoundError
        _module_cache[name] = RecipeNotFoundError
        return RecipeNotFoundError
    elif name == "RecipeDependencyError":
        from .exceptions import RecipeDependencyError
        _module_cache[name] = RecipeDependencyError
        return RecipeDependencyError
    elif name == "RecipePolicyError":
        from .exceptions import RecipePolicyError
        _module_cache[name] = RecipePolicyError
        return RecipePolicyError
    elif name == "RecipeValidationError":
        from .exceptions import RecipeValidationError
        _module_cache[name] = RecipeValidationError
        return RecipeValidationError
    elif name == "ExitCode":
        from .models import ExitCode
        _module_cache[name] = ExitCode
        return ExitCode
    elif name == "resolve":
        from .bridge import resolve
        _module_cache[name] = resolve
        return resolve
    elif name == "run_background":
        from .operations import run_background
        _module_cache[name] = run_background
        return run_background
    elif name == "submit_job":
        from .operations import submit_job
        _module_cache[name] = submit_job
        return submit_job
    elif name == "schedule":
        from .operations import schedule
        _module_cache[name] = schedule
        return schedule
    elif name == "ResolvedRecipe":
        from .bridge import ResolvedRecipe
        _module_cache[name] = ResolvedRecipe
        return ResolvedRecipe
    elif name == "RuntimeConfig":
        from .runtime import RuntimeConfig
        _module_cache[name] = RuntimeConfig
        return RuntimeConfig
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
