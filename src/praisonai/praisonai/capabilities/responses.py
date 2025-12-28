"""
Responses Capabilities Module

Provides response management functionality via LiteLLM.
"""

from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List


@dataclass
class ResponseResult:
    """Result from response operations."""
    id: str
    object: str = "response"
    output: Optional[List[Dict[str, Any]]] = None
    status: Optional[str] = None
    model: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def responses_create(
    model: str,
    input: str,
    instructions: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    temperature: float = 1.0,
    max_output_tokens: Optional[int] = None,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> ResponseResult:
    """
    Create a response using the Responses API.
    
    Args:
        model: Model to use
        input: Input text or messages
        instructions: System instructions
        tools: List of tools
        temperature: Sampling temperature
        max_output_tokens: Maximum output tokens
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        metadata: Optional metadata for tracing
        
    Returns:
        ResponseResult with response data
        
    Example:
        >>> result = responses_create(
        ...     model="gpt-4o-mini",
        ...     input="What is 2+2?"
        ... )
        >>> print(result.output)
    """
    import litellm
    
    call_kwargs = {
        'model': model,
        'input': input,
        'temperature': temperature,
        'timeout': timeout,
    }
    
    if instructions:
        call_kwargs['instructions'] = instructions
    if tools:
        call_kwargs['tools'] = tools
    if max_output_tokens:
        call_kwargs['max_output_tokens'] = max_output_tokens
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    if metadata:
        call_kwargs['metadata'] = metadata
    
    # Try to use responses API if available
    try:
        response = litellm.responses(**call_kwargs)
        
        output = None
        if hasattr(response, 'output'):
            output = []
            for item in response.output:
                output.append({
                    'type': getattr(item, 'type', 'message'),
                    'content': getattr(item, 'content', None),
                })
        
        usage = None
        if hasattr(response, 'usage'):
            usage = {
                'input_tokens': getattr(response.usage, 'input_tokens', 0),
                'output_tokens': getattr(response.usage, 'output_tokens', 0),
                'total_tokens': getattr(response.usage, 'total_tokens', 0),
            }
        
        return ResponseResult(
            id=getattr(response, 'id', ''),
            object=getattr(response, 'object', 'response'),
            output=output,
            status=getattr(response, 'status', 'completed'),
            model=getattr(response, 'model', model),
            usage=usage,
            metadata=metadata or {},
        )
    except AttributeError:
        # Fallback to completion if responses not available
        messages = [{"role": "user", "content": input}]
        if instructions:
            messages.insert(0, {"role": "system", "content": instructions})
        
        response = litellm.completion(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_output_tokens,
            timeout=timeout,
            api_key=api_key,
            api_base=api_base,
            **kwargs
        )
        
        output = [{
            'type': 'message',
            'content': response.choices[0].message.content if response.choices else None,
        }]
        
        usage = None
        if hasattr(response, 'usage'):
            usage = {
                'input_tokens': getattr(response.usage, 'prompt_tokens', 0),
                'output_tokens': getattr(response.usage, 'completion_tokens', 0),
                'total_tokens': getattr(response.usage, 'total_tokens', 0),
            }
        
        return ResponseResult(
            id=getattr(response, 'id', ''),
            object='response',
            output=output,
            status='completed',
            model=model,
            usage=usage,
            metadata=metadata or {},
        )


async def aresponses_create(
    model: str,
    input: str,
    instructions: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    temperature: float = 1.0,
    max_output_tokens: Optional[int] = None,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> ResponseResult:
    """
    Async: Create a response using the Responses API.
    
    See responses_create() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'model': model,
        'input': input,
        'temperature': temperature,
        'timeout': timeout,
    }
    
    if instructions:
        call_kwargs['instructions'] = instructions
    if tools:
        call_kwargs['tools'] = tools
    if max_output_tokens:
        call_kwargs['max_output_tokens'] = max_output_tokens
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    if metadata:
        call_kwargs['metadata'] = metadata
    
    try:
        response = await litellm.aresponses(**call_kwargs)
        
        output = None
        if hasattr(response, 'output'):
            output = []
            for item in response.output:
                output.append({
                    'type': getattr(item, 'type', 'message'),
                    'content': getattr(item, 'content', None),
                })
        
        usage = None
        if hasattr(response, 'usage'):
            usage = {
                'input_tokens': getattr(response.usage, 'input_tokens', 0),
                'output_tokens': getattr(response.usage, 'output_tokens', 0),
                'total_tokens': getattr(response.usage, 'total_tokens', 0),
            }
        
        return ResponseResult(
            id=getattr(response, 'id', ''),
            object=getattr(response, 'object', 'response'),
            output=output,
            status=getattr(response, 'status', 'completed'),
            model=getattr(response, 'model', model),
            usage=usage,
            metadata=metadata or {},
        )
    except AttributeError:
        messages = [{"role": "user", "content": input}]
        if instructions:
            messages.insert(0, {"role": "system", "content": instructions})
        
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_output_tokens,
            timeout=timeout,
            api_key=api_key,
            api_base=api_base,
            **kwargs
        )
        
        output = [{
            'type': 'message',
            'content': response.choices[0].message.content if response.choices else None,
        }]
        
        usage = None
        if hasattr(response, 'usage'):
            usage = {
                'input_tokens': getattr(response.usage, 'prompt_tokens', 0),
                'output_tokens': getattr(response.usage, 'completion_tokens', 0),
                'total_tokens': getattr(response.usage, 'total_tokens', 0),
            }
        
        return ResponseResult(
            id=getattr(response, 'id', ''),
            object='response',
            output=output,
            status='completed',
            model=model,
            usage=usage,
            metadata=metadata or {},
        )
