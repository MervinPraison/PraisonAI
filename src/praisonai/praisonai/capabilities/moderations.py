"""
Moderations Capabilities Module

Provides content moderation functionality via LiteLLM.
"""

from dataclasses import dataclass, field
from typing import Optional, Union, List, Any, Dict


@dataclass
class ModerationResult:
    """Result from content moderation."""
    flagged: bool
    categories: Dict[str, bool] = field(default_factory=dict)
    category_scores: Dict[str, float] = field(default_factory=dict)
    model: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def moderate(
    input: Union[str, List[str]],
    model: str = "omni-moderation-latest",
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> List[ModerationResult]:
    """
    Check content for policy violations.
    
    Args:
        input: Text or list of texts to moderate
        model: Model name (e.g., "text-moderation-latest", "text-moderation-stable")
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        metadata: Optional metadata for tracing
        
    Returns:
        List of ModerationResult objects
        
    Example:
        >>> results = moderate("Some text to check")
        >>> if results[0].flagged:
        ...     print("Content flagged!")
    """
    import litellm
    
    call_kwargs = {
        'input': input,
        'model': model,
        'timeout': timeout,
    }
    
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    if metadata:
        call_kwargs['metadata'] = metadata
    
    response = litellm.moderation(**call_kwargs)
    
    results = []
    if hasattr(response, 'results'):
        for item in response.results:
            categories = {}
            category_scores = {}
            
            if hasattr(item, 'categories'):
                for cat_name in dir(item.categories):
                    if not cat_name.startswith('_'):
                        categories[cat_name] = getattr(item.categories, cat_name, False)
            
            if hasattr(item, 'category_scores'):
                for cat_name in dir(item.category_scores):
                    if not cat_name.startswith('_'):
                        category_scores[cat_name] = getattr(item.category_scores, cat_name, 0.0)
            
            results.append(ModerationResult(
                flagged=getattr(item, 'flagged', False),
                categories=categories,
                category_scores=category_scores,
                model=model,
                metadata=metadata or {},
            ))
    
    return results


async def amoderate(
    input: Union[str, List[str]],
    model: str = "text-moderation-latest",
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> List[ModerationResult]:
    """
    Async: Check content for policy violations.
    
    See moderate() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'input': input,
        'model': model,
        'timeout': timeout,
    }
    
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    if metadata:
        call_kwargs['metadata'] = metadata
    
    response = await litellm.amoderation(**call_kwargs)
    
    results = []
    if hasattr(response, 'results'):
        for item in response.results:
            categories = {}
            category_scores = {}
            
            if hasattr(item, 'categories'):
                for cat_name in dir(item.categories):
                    if not cat_name.startswith('_'):
                        categories[cat_name] = getattr(item.categories, cat_name, False)
            
            if hasattr(item, 'category_scores'):
                for cat_name in dir(item.category_scores):
                    if not cat_name.startswith('_'):
                        category_scores[cat_name] = getattr(item.category_scores, cat_name, 0.0)
            
            results.append(ModerationResult(
                flagged=getattr(item, 'flagged', False),
                categories=categories,
                category_scores=category_scores,
                model=model,
                metadata=metadata or {},
            ))
    
    return results
