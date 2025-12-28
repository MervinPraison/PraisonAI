"""
Completions Capabilities Module

Provides chat/completions and text completions functionality via LiteLLM.
"""

from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List, Union


@dataclass
class CompletionResult:
    """Result from completion operations."""
    id: str
    content: Optional[str] = None
    role: str = "assistant"
    model: Optional[str] = None
    finish_reason: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def chat_completion(
    messages: List[Dict[str, Any]],
    model: str = "gpt-4o-mini",
    temperature: float = 1.0,
    max_tokens: Optional[int] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[str] = None,
    stream: bool = False,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> CompletionResult:
    """
    Create a chat completion.
    
    Args:
        messages: List of messages [{"role": "user", "content": "..."}]
        model: Model to use
        temperature: Sampling temperature
        max_tokens: Maximum tokens to generate
        tools: List of tools
        tool_choice: Tool choice mode
        stream: Whether to stream
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        metadata: Optional metadata for tracing
        
    Returns:
        CompletionResult with response
        
    Example:
        >>> result = chat_completion([{"role": "user", "content": "Hello"}])
        >>> print(result.content)
    """
    import litellm
    
    call_kwargs = {
        'model': model,
        'messages': messages,
        'temperature': temperature,
        'stream': stream,
        'timeout': timeout,
    }
    
    if max_tokens:
        call_kwargs['max_tokens'] = max_tokens
    if tools:
        call_kwargs['tools'] = tools
    if tool_choice:
        call_kwargs['tool_choice'] = tool_choice
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    if metadata:
        call_kwargs['metadata'] = metadata
    
    response = litellm.completion(**call_kwargs)
    
    choice = response.choices[0] if response.choices else None
    message = choice.message if choice else None
    
    usage = None
    if hasattr(response, 'usage') and response.usage:
        usage = {
            'prompt_tokens': getattr(response.usage, 'prompt_tokens', 0),
            'completion_tokens': getattr(response.usage, 'completion_tokens', 0),
            'total_tokens': getattr(response.usage, 'total_tokens', 0),
        }
    
    tool_calls = None
    if message and hasattr(message, 'tool_calls') and message.tool_calls:
        tool_calls = []
        for tc in message.tool_calls:
            tool_calls.append({
                'id': getattr(tc, 'id', ''),
                'type': getattr(tc, 'type', 'function'),
                'function': {
                    'name': getattr(tc.function, 'name', ''),
                    'arguments': getattr(tc.function, 'arguments', '{}'),
                }
            })
    
    return CompletionResult(
        id=getattr(response, 'id', ''),
        content=getattr(message, 'content', None) if message else None,
        role=getattr(message, 'role', 'assistant') if message else 'assistant',
        model=getattr(response, 'model', model),
        finish_reason=getattr(choice, 'finish_reason', None) if choice else None,
        usage=usage,
        tool_calls=tool_calls,
        metadata=metadata or {},
    )


async def achat_completion(
    messages: List[Dict[str, Any]],
    model: str = "gpt-4o-mini",
    temperature: float = 1.0,
    max_tokens: Optional[int] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[str] = None,
    stream: bool = False,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> CompletionResult:
    """
    Async: Create a chat completion.
    
    See chat_completion() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'model': model,
        'messages': messages,
        'temperature': temperature,
        'stream': stream,
        'timeout': timeout,
    }
    
    if max_tokens:
        call_kwargs['max_tokens'] = max_tokens
    if tools:
        call_kwargs['tools'] = tools
    if tool_choice:
        call_kwargs['tool_choice'] = tool_choice
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    if metadata:
        call_kwargs['metadata'] = metadata
    
    response = await litellm.acompletion(**call_kwargs)
    
    choice = response.choices[0] if response.choices else None
    message = choice.message if choice else None
    
    usage = None
    if hasattr(response, 'usage') and response.usage:
        usage = {
            'prompt_tokens': getattr(response.usage, 'prompt_tokens', 0),
            'completion_tokens': getattr(response.usage, 'completion_tokens', 0),
            'total_tokens': getattr(response.usage, 'total_tokens', 0),
        }
    
    tool_calls = None
    if message and hasattr(message, 'tool_calls') and message.tool_calls:
        tool_calls = []
        for tc in message.tool_calls:
            tool_calls.append({
                'id': getattr(tc, 'id', ''),
                'type': getattr(tc, 'type', 'function'),
                'function': {
                    'name': getattr(tc.function, 'name', ''),
                    'arguments': getattr(tc.function, 'arguments', '{}'),
                }
            })
    
    return CompletionResult(
        id=getattr(response, 'id', ''),
        content=getattr(message, 'content', None) if message else None,
        role=getattr(message, 'role', 'assistant') if message else 'assistant',
        model=getattr(response, 'model', model),
        finish_reason=getattr(choice, 'finish_reason', None) if choice else None,
        usage=usage,
        tool_calls=tool_calls,
        metadata=metadata or {},
    )


def text_completion(
    prompt: str,
    model: str = "gpt-3.5-turbo-instruct",
    temperature: float = 1.0,
    max_tokens: Optional[int] = None,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> CompletionResult:
    """
    Create a text completion (legacy completions API).
    
    Args:
        prompt: Text prompt
        model: Model to use
        temperature: Sampling temperature
        max_tokens: Maximum tokens to generate
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        metadata: Optional metadata for tracing
        
    Returns:
        CompletionResult with response
    """
    import litellm
    
    call_kwargs = {
        'model': model,
        'prompt': prompt,
        'temperature': temperature,
        'timeout': timeout,
    }
    
    if max_tokens:
        call_kwargs['max_tokens'] = max_tokens
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    if metadata:
        call_kwargs['metadata'] = metadata
    
    response = litellm.text_completion(**call_kwargs)
    
    choice = response.choices[0] if response.choices else None
    
    usage = None
    if hasattr(response, 'usage') and response.usage:
        usage = {
            'prompt_tokens': getattr(response.usage, 'prompt_tokens', 0),
            'completion_tokens': getattr(response.usage, 'completion_tokens', 0),
            'total_tokens': getattr(response.usage, 'total_tokens', 0),
        }
    
    return CompletionResult(
        id=getattr(response, 'id', ''),
        content=getattr(choice, 'text', None) if choice else None,
        role='assistant',
        model=getattr(response, 'model', model),
        finish_reason=getattr(choice, 'finish_reason', None) if choice else None,
        usage=usage,
        metadata=metadata or {},
    )


async def atext_completion(
    prompt: str,
    model: str = "gpt-3.5-turbo-instruct",
    temperature: float = 1.0,
    max_tokens: Optional[int] = None,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> CompletionResult:
    """
    Async: Create a text completion.
    
    See text_completion() for full documentation.
    """
    import litellm
    
    call_kwargs = {
        'model': model,
        'prompt': prompt,
        'temperature': temperature,
        'timeout': timeout,
    }
    
    if max_tokens:
        call_kwargs['max_tokens'] = max_tokens
    if api_key:
        call_kwargs['api_key'] = api_key
    if api_base:
        call_kwargs['api_base'] = api_base
    
    call_kwargs.update(kwargs)
    
    if metadata:
        call_kwargs['metadata'] = metadata
    
    response = await litellm.atext_completion(**call_kwargs)
    
    choice = response.choices[0] if response.choices else None
    
    usage = None
    if hasattr(response, 'usage') and response.usage:
        usage = {
            'prompt_tokens': getattr(response.usage, 'prompt_tokens', 0),
            'completion_tokens': getattr(response.usage, 'completion_tokens', 0),
            'total_tokens': getattr(response.usage, 'total_tokens', 0),
        }
    
    return CompletionResult(
        id=getattr(response, 'id', ''),
        content=getattr(choice, 'text', None) if choice else None,
        role='assistant',
        model=getattr(response, 'model', model),
        finish_reason=getattr(choice, 'finish_reason', None) if choice else None,
        usage=usage,
        metadata=metadata or {},
    )
