"""
Fine-tuning Capabilities Module

Provides model fine-tuning functionality via LiteLLM.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Any, Dict, Literal


@dataclass
class FineTuningResult:
    """Result from fine-tuning operations."""
    id: str
    object: str = "fine_tuning.job"
    model: Optional[str] = None
    status: Optional[str] = None
    training_file: Optional[str] = None
    validation_file: Optional[str] = None
    fine_tuned_model: Optional[str] = None
    created_at: Optional[int] = None
    finished_at: Optional[int] = None
    trained_tokens: Optional[int] = None
    error: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def fine_tuning_create(
    training_file: str,
    model: str = "gpt-4o-mini-2024-07-18",
    validation_file: Optional[str] = None,
    hyperparameters: Optional[Dict[str, Any]] = None,
    suffix: Optional[str] = None,
    custom_llm_provider: Literal["openai", "azure"] = "openai",
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> FineTuningResult:
    """
    Create a fine-tuning job.
    
    Args:
        training_file: ID of the training file
        model: Base model to fine-tune
        validation_file: Optional validation file ID
        hyperparameters: Training hyperparameters
        suffix: Suffix for the fine-tuned model name
        custom_llm_provider: Provider ("openai", "azure")
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        
    Returns:
        FineTuningResult with job ID
        
    Example:
        >>> result = fine_tuning_create("file-abc123")
        >>> print(result.id, result.status)
    """
    import litellm
    
    call_kwargs = {
        'training_file': training_file,
        'model': model,
        'custom_llm_provider': custom_llm_provider,
        'timeout': timeout,
    }
    
    if validation_file:
        call_kwargs['validation_file'] = validation_file
    if hyperparameters:
        call_kwargs['hyperparameters'] = hyperparameters
    if suffix:
        call_kwargs['suffix'] = suffix
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    response = litellm.create_fine_tuning_job(**call_kwargs)
    
    error = None
    if hasattr(response, 'error') and response.error:
        error = {
            'code': getattr(response.error, 'code', None),
            'message': getattr(response.error, 'message', None),
        }
    
    return FineTuningResult(
        id=getattr(response, 'id', ''),
        object=getattr(response, 'object', 'fine_tuning.job'),
        model=getattr(response, 'model', model),
        status=getattr(response, 'status', None),
        training_file=getattr(response, 'training_file', training_file),
        validation_file=getattr(response, 'validation_file', validation_file),
        fine_tuned_model=getattr(response, 'fine_tuned_model', None),
        created_at=getattr(response, 'created_at', None),
        finished_at=getattr(response, 'finished_at', None),
        trained_tokens=getattr(response, 'trained_tokens', None),
        error=error,
    )


async def afine_tuning_create(
    training_file: str,
    model: str = "gpt-4o-mini-2024-07-18",
    validation_file: Optional[str] = None,
    hyperparameters: Optional[Dict[str, Any]] = None,
    suffix: Optional[str] = None,
    custom_llm_provider: Literal["openai", "azure"] = "openai",
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> FineTuningResult:
    """
    Async: Create a fine-tuning job.
    
    See fine_tuning_create() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'training_file': training_file,
        'model': model,
        'custom_llm_provider': custom_llm_provider,
        'timeout': timeout,
    }
    
    if validation_file:
        call_kwargs['validation_file'] = validation_file
    if hyperparameters:
        call_kwargs['hyperparameters'] = hyperparameters
    if suffix:
        call_kwargs['suffix'] = suffix
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    response = await litellm.acreate_fine_tuning_job(**call_kwargs)
    
    error = None
    if hasattr(response, 'error') and response.error:
        error = {
            'code': getattr(response.error, 'code', None),
            'message': getattr(response.error, 'message', None),
        }
    
    return FineTuningResult(
        id=getattr(response, 'id', ''),
        object=getattr(response, 'object', 'fine_tuning.job'),
        model=getattr(response, 'model', model),
        status=getattr(response, 'status', None),
        training_file=getattr(response, 'training_file', training_file),
        validation_file=getattr(response, 'validation_file', validation_file),
        fine_tuned_model=getattr(response, 'fine_tuned_model', None),
        created_at=getattr(response, 'created_at', None),
        finished_at=getattr(response, 'finished_at', None),
        trained_tokens=getattr(response, 'trained_tokens', None),
        error=error,
    )


def fine_tuning_list(
    custom_llm_provider: Literal["openai", "azure"] = "openai",
    after: Optional[str] = None,
    limit: int = 20,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> List[FineTuningResult]:
    """
    List fine-tuning jobs.
    
    Args:
        custom_llm_provider: Provider
        after: Cursor for pagination
        limit: Maximum number of jobs to return
        api_key: Optional API key override
        api_base: Optional API base URL override
        
    Returns:
        List of FineTuningResult objects
    """
    import litellm
    
    call_kwargs = {
        'custom_llm_provider': custom_llm_provider,
        'limit': limit,
    }
    
    if after:
        call_kwargs['after'] = after
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    response = litellm.list_fine_tuning_jobs(**call_kwargs)
    
    results = []
    data = getattr(response, 'data', response) if hasattr(response, 'data') else response
    if isinstance(data, list):
        for item in data:
            error = None
            if hasattr(item, 'error') and item.error:
                error = {
                    'code': getattr(item.error, 'code', None),
                    'message': getattr(item.error, 'message', None),
                }
            
            results.append(FineTuningResult(
                id=getattr(item, 'id', ''),
                object=getattr(item, 'object', 'fine_tuning.job'),
                model=getattr(item, 'model', None),
                status=getattr(item, 'status', None),
                training_file=getattr(item, 'training_file', None),
                validation_file=getattr(item, 'validation_file', None),
                fine_tuned_model=getattr(item, 'fine_tuned_model', None),
                created_at=getattr(item, 'created_at', None),
                finished_at=getattr(item, 'finished_at', None),
                trained_tokens=getattr(item, 'trained_tokens', None),
                error=error,
            ))
    
    return results


async def afine_tuning_list(
    custom_llm_provider: Literal["openai", "azure"] = "openai",
    after: Optional[str] = None,
    limit: int = 20,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> List[FineTuningResult]:
    """
    Async: List fine-tuning jobs.
    
    See fine_tuning_list() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'custom_llm_provider': custom_llm_provider,
        'limit': limit,
    }
    
    if after:
        call_kwargs['after'] = after
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    response = await litellm.alist_fine_tuning_jobs(**call_kwargs)
    
    results = []
    data = getattr(response, 'data', response) if hasattr(response, 'data') else response
    if isinstance(data, list):
        for item in data:
            error = None
            if hasattr(item, 'error') and item.error:
                error = {
                    'code': getattr(item.error, 'code', None),
                    'message': getattr(item.error, 'message', None),
                }
            
            results.append(FineTuningResult(
                id=getattr(item, 'id', ''),
                object=getattr(item, 'object', 'fine_tuning.job'),
                model=getattr(item, 'model', None),
                status=getattr(item, 'status', None),
                training_file=getattr(item, 'training_file', None),
                validation_file=getattr(item, 'validation_file', None),
                fine_tuned_model=getattr(item, 'fine_tuned_model', None),
                created_at=getattr(item, 'created_at', None),
                finished_at=getattr(item, 'finished_at', None),
                trained_tokens=getattr(item, 'trained_tokens', None),
                error=error,
            ))
    
    return results
