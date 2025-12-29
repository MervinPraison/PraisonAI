"""
Recipe Runtime Bridge.

Provides unified recipe resolution and execution for operational runtimes:
- Background tasks
- Async jobs
- Scheduled execution

This module bridges the gap between recipes and operational features,
keeping all glue code in the wrapper (praisonai) without modifying core SDK.
"""

import uuid
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ResolvedRecipe:
    """
    A fully resolved recipe ready for execution.
    
    Contains all information needed to execute a recipe in any runtime mode.
    """
    name: str
    version: str
    description: str
    path: Path
    
    # Workflow/agents configuration
    workflow_config: Dict[str, Any] = field(default_factory=dict)
    agents_config: Dict[str, Any] = field(default_factory=dict)
    
    # User-provided input and config
    input_data: Any = None
    config: Dict[str, Any] = field(default_factory=dict)
    
    # Runtime configuration
    runtime_config: Optional[Any] = None  # RuntimeConfig
    
    # Execution context
    session_id: Optional[str] = None
    run_id: str = field(default_factory=lambda: f"run_{uuid.uuid4().hex[:12]}")
    
    # Options
    options: Dict[str, Any] = field(default_factory=dict)
    
    def get_timeout_sec(self, default: int = 300) -> int:
        """Get timeout from runtime config or options."""
        if self.options.get('timeout_sec'):
            return self.options['timeout_sec']
        if self.runtime_config and hasattr(self.runtime_config, 'schedule'):
            return self.runtime_config.schedule.timeout_sec
        return default
    
    def get_max_cost_usd(self, default: float = 1.00) -> float:
        """Get max cost from runtime config or options."""
        if self.options.get('max_cost_usd'):
            return self.options['max_cost_usd']
        if self.runtime_config and hasattr(self.runtime_config, 'schedule'):
            return self.runtime_config.schedule.max_cost_usd
        return default


def resolve(
    name: str,
    input_data: Any = None,
    config: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    options: Optional[Dict[str, Any]] = None,
) -> ResolvedRecipe:
    """
    Resolve a recipe name into a fully executable ResolvedRecipe.
    
    Args:
        name: Recipe name or path
        input_data: User input for the recipe
        config: Configuration overrides
        session_id: Session ID for conversation continuity
        options: Execution options (timeout_sec, verbose, etc.)
        
    Returns:
        ResolvedRecipe ready for execution
        
    Raises:
        RecipeNotFoundError: If recipe cannot be found
        RecipeValidationError: If recipe is invalid
    """
    from praisonai.templates import TemplateLoader
    from praisonai.recipe.exceptions import RecipeNotFoundError
    
    options = options or {}
    config = config or {}
    
    loader = TemplateLoader(offline=options.get('offline', False))
    
    try:
        # Load template configuration
        template_config = loader.load(name, config=config, offline=options.get('offline', False))
    except Exception as e:
        # Try to find similar recipes for helpful error message
        try:
            from praisonai.recipe.core import list_recipes
            available = list_recipes()
            suggestions = _find_similar_recipes(name, [r.name for r in available])
            if suggestions:
                raise RecipeNotFoundError(
                    f"Recipe '{name}' not found. Did you mean: {', '.join(suggestions[:3])}?"
                )
        except Exception:
            pass
        raise RecipeNotFoundError(f"Recipe '{name}' not found: {e}")
    
    # Load workflow and agents configs
    try:
        workflow_config = loader.load_workflow_config(template_config)
    except Exception:
        workflow_config = {}
    
    try:
        agents_config = loader.load_agents_config(template_config)
    except Exception:
        agents_config = {}
    
    # Generate session_id if not provided
    if not session_id:
        session_id = f"session_{uuid.uuid4().hex[:8]}"
    
    return ResolvedRecipe(
        name=template_config.name,
        version=template_config.version,
        description=template_config.description,
        path=template_config.path,
        workflow_config=workflow_config,
        agents_config=agents_config,
        input_data=input_data,
        config={**template_config.defaults, **config},
        runtime_config=template_config.runtime,
        session_id=session_id,
        options=options,
    )


def execute_resolved_recipe(
    resolved: ResolvedRecipe,
    progress_callback: Optional[callable] = None,
) -> Any:
    """
    Execute a resolved recipe and return the result.
    
    This is the canonical execution function used by all runtime modes.
    
    Args:
        resolved: Resolved recipe to execute
        progress_callback: Optional callback for progress updates
        
    Returns:
        Recipe execution result
    """
    from praisonai.recipe.core import run
    
    # Build options dict
    options = {
        'timeout_sec': resolved.get_timeout_sec(),
        'verbose': resolved.options.get('verbose', False),
        'dry_run': resolved.options.get('dry_run', False),
        **resolved.options,
    }
    
    # Execute using core recipe.run
    result = run(
        resolved.name,
        input=resolved.input_data,
        config=resolved.config,
        session_id=resolved.session_id,
        options=options,
    )
    
    return result


def execute_resolved_recipe_stream(
    resolved: ResolvedRecipe,
    progress_callback: Optional[callable] = None,
) -> Iterator[Any]:
    """
    Execute a resolved recipe with streaming output.
    
    Args:
        resolved: Resolved recipe to execute
        progress_callback: Optional callback for progress updates
        
    Yields:
        RecipeEvent objects during execution
    """
    from praisonai.recipe.core import run_stream
    
    # Build options dict
    options = {
        'timeout_sec': resolved.get_timeout_sec(),
        'verbose': resolved.options.get('verbose', False),
        **resolved.options,
    }
    
    # Execute using core recipe.run_stream
    for event in run_stream(
        resolved.name,
        input=resolved.input_data,
        config=resolved.config,
        session_id=resolved.session_id,
        options=options,
    ):
        if progress_callback:
            try:
                progress_callback(event)
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")
        yield event


def _find_similar_recipes(name: str, available: List[str], max_results: int = 5) -> List[str]:
    """Find recipes with similar names using simple string matching."""
    name_lower = name.lower()
    
    # Exact prefix match
    prefix_matches = [r for r in available if r.lower().startswith(name_lower)]
    
    # Contains match
    contains_matches = [r for r in available if name_lower in r.lower() and r not in prefix_matches]
    
    # Levenshtein-like similarity (simplified)
    def similarity(a: str, b: str) -> float:
        a, b = a.lower(), b.lower()
        if a == b:
            return 1.0
        if a in b or b in a:
            return 0.8
        # Count common characters
        common = sum(1 for c in a if c in b)
        return common / max(len(a), len(b))
    
    other_matches = sorted(
        [r for r in available if r not in prefix_matches and r not in contains_matches],
        key=lambda r: similarity(name, r),
        reverse=True
    )
    
    results = prefix_matches + contains_matches + other_matches
    return results[:max_results]


# Convenience functions for different runtime modes

def get_recipe_task_description(resolved: ResolvedRecipe) -> str:
    """Get a task description suitable for scheduler/background."""
    if resolved.input_data:
        if isinstance(resolved.input_data, str):
            return resolved.input_data
        elif isinstance(resolved.input_data, dict):
            return str(resolved.input_data.get('prompt', resolved.input_data.get('task', str(resolved.input_data))))
    return f"Execute recipe: {resolved.name}"


def get_recipe_metadata(resolved: ResolvedRecipe) -> Dict[str, Any]:
    """Get metadata dict for job/scheduler state persistence."""
    return {
        'recipe_name': resolved.name,
        'recipe_version': resolved.version,
        'recipe_path': str(resolved.path) if resolved.path else None,
        'session_id': resolved.session_id,
        'run_id': resolved.run_id,
        'config': resolved.config,
        'options': resolved.options,
    }
