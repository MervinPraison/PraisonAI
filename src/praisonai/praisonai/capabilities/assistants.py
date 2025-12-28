"""
Assistants Capabilities Module

Provides OpenAI-style assistants functionality via LiteLLM.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Any, Dict, Literal


@dataclass
class AssistantResult:
    """Result from assistant operations."""
    id: str
    object: str = "assistant"
    name: Optional[str] = None
    description: Optional[str] = None
    model: Optional[str] = None
    instructions: Optional[str] = None
    tools: Optional[List[Dict[str, Any]]] = None
    created_at: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def assistant_create(
    model: str = "gpt-4o-mini",
    name: Optional[str] = None,
    description: Optional[str] = None,
    instructions: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    file_ids: Optional[List[str]] = None,
    custom_llm_provider: Literal["openai", "azure"] = "openai",
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    assistant_metadata: Optional[Dict[str, str]] = None,
    **kwargs
) -> AssistantResult:
    """
    Create an assistant.
    
    Args:
        model: Model to use for the assistant
        name: Name of the assistant
        description: Description of the assistant
        instructions: System instructions for the assistant
        tools: List of tools (e.g., [{"type": "code_interpreter"}])
        file_ids: List of file IDs to attach
        custom_llm_provider: Provider ("openai", "azure")
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        assistant_metadata: Optional metadata for the assistant
        
    Returns:
        AssistantResult with assistant ID
        
    Example:
        >>> result = assistant_create(
        ...     name="Math Tutor",
        ...     instructions="You are a helpful math tutor."
        ... )
        >>> print(result.id)
    """
    import litellm
    
    call_kwargs = {
        'model': model,
        'custom_llm_provider': custom_llm_provider,
        'timeout': timeout,
    }
    
    if name:
        call_kwargs['name'] = name
    if description:
        call_kwargs['description'] = description
    if instructions:
        call_kwargs['instructions'] = instructions
    if tools:
        call_kwargs['tools'] = tools
    if file_ids:
        call_kwargs['file_ids'] = file_ids
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    if assistant_metadata:
        call_kwargs['metadata'] = assistant_metadata
    
    call_kwargs.update(kwargs)
    
    response = litellm.create_assistants(**call_kwargs)
    
    return AssistantResult(
        id=getattr(response, 'id', ''),
        object=getattr(response, 'object', 'assistant'),
        name=getattr(response, 'name', name),
        description=getattr(response, 'description', description),
        model=getattr(response, 'model', model),
        instructions=getattr(response, 'instructions', instructions),
        tools=getattr(response, 'tools', tools),
        created_at=getattr(response, 'created_at', None),
        metadata=assistant_metadata or {},
    )


async def aassistant_create(
    model: str = "gpt-4o-mini",
    name: Optional[str] = None,
    description: Optional[str] = None,
    instructions: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    file_ids: Optional[List[str]] = None,
    custom_llm_provider: Literal["openai", "azure"] = "openai",
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    assistant_metadata: Optional[Dict[str, str]] = None,
    **kwargs
) -> AssistantResult:
    """
    Async: Create an assistant.
    
    See assistant_create() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'model': model,
        'custom_llm_provider': custom_llm_provider,
        'timeout': timeout,
    }
    
    if name:
        call_kwargs['name'] = name
    if description:
        call_kwargs['description'] = description
    if instructions:
        call_kwargs['instructions'] = instructions
    if tools:
        call_kwargs['tools'] = tools
    if file_ids:
        call_kwargs['file_ids'] = file_ids
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    if assistant_metadata:
        call_kwargs['metadata'] = assistant_metadata
    
    call_kwargs.update(kwargs)
    
    response = await litellm.acreate_assistants(**call_kwargs)
    
    return AssistantResult(
        id=getattr(response, 'id', ''),
        object=getattr(response, 'object', 'assistant'),
        name=getattr(response, 'name', name),
        description=getattr(response, 'description', description),
        model=getattr(response, 'model', model),
        instructions=getattr(response, 'instructions', instructions),
        tools=getattr(response, 'tools', tools),
        created_at=getattr(response, 'created_at', None),
        metadata=assistant_metadata or {},
    )


def assistant_list(
    custom_llm_provider: Literal["openai", "azure"] = "openai",
    limit: int = 20,
    order: str = "desc",
    after: Optional[str] = None,
    before: Optional[str] = None,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> List[AssistantResult]:
    """
    List assistants.
    
    Args:
        custom_llm_provider: Provider
        limit: Maximum number of assistants to return
        order: Sort order ("asc" or "desc")
        after: Cursor for pagination
        before: Cursor for pagination
        api_key: Optional API key override
        api_base: Optional API base URL override
        
    Returns:
        List of AssistantResult objects
    """
    import litellm
    
    call_kwargs = {
        'custom_llm_provider': custom_llm_provider,
        'limit': limit,
        'order': order,
    }
    
    if after:
        call_kwargs['after'] = after
    if before:
        call_kwargs['before'] = before
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    response = litellm.get_assistants(**call_kwargs)
    
    results = []
    data = getattr(response, 'data', response) if hasattr(response, 'data') else response
    if isinstance(data, list):
        for item in data:
            results.append(AssistantResult(
                id=getattr(item, 'id', ''),
                object=getattr(item, 'object', 'assistant'),
                name=getattr(item, 'name', None),
                description=getattr(item, 'description', None),
                model=getattr(item, 'model', None),
                instructions=getattr(item, 'instructions', None),
                tools=getattr(item, 'tools', None),
                created_at=getattr(item, 'created_at', None),
            ))
    
    return results


async def aassistant_list(
    custom_llm_provider: Literal["openai", "azure"] = "openai",
    limit: int = 20,
    order: str = "desc",
    after: Optional[str] = None,
    before: Optional[str] = None,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    **kwargs
) -> List[AssistantResult]:
    """
    Async: List assistants.
    
    See assistant_list() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'custom_llm_provider': custom_llm_provider,
        'limit': limit,
        'order': order,
    }
    
    if after:
        call_kwargs['after'] = after
    if before:
        call_kwargs['before'] = before
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    response = await litellm.aget_assistants(**call_kwargs)
    
    results = []
    data = getattr(response, 'data', response) if hasattr(response, 'data') else response
    if isinstance(data, list):
        for item in data:
            results.append(AssistantResult(
                id=getattr(item, 'id', ''),
                object=getattr(item, 'object', 'assistant'),
                name=getattr(item, 'name', None),
                description=getattr(item, 'description', None),
                model=getattr(item, 'model', None),
                instructions=getattr(item, 'instructions', None),
                tools=getattr(item, 'tools', None),
                created_at=getattr(item, 'created_at', None),
            ))
    
    return results
