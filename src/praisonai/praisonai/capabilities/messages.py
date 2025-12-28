"""
Messages Capabilities Module

Provides Anthropic-style messages API functionality via LiteLLM.
"""

from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List


@dataclass
class MessageResult:
    """Result from message operations."""
    id: str
    content: Optional[List[Dict[str, Any]]] = None
    role: str = "assistant"
    model: Optional[str] = None
    stop_reason: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenCountResult:
    """Result from token counting."""
    input_tokens: int
    model: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def messages_create(
    messages: List[Dict[str, Any]],
    model: str = "claude-3-5-sonnet-20241022",
    max_tokens: int = 1024,
    system: Optional[str] = None,
    temperature: float = 1.0,
    tools: Optional[List[Dict[str, Any]]] = None,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> MessageResult:
    """
    Create a message using Anthropic-style API.
    
    Args:
        messages: List of messages
        model: Model to use (e.g., "claude-3-5-sonnet-20241022")
        max_tokens: Maximum tokens to generate
        system: System prompt
        temperature: Sampling temperature
        tools: List of tools
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        metadata: Optional metadata for tracing
        
    Returns:
        MessageResult with response
        
    Example:
        >>> result = messages_create([{"role": "user", "content": "Hello"}])
        >>> print(result.content)
    """
    import litellm
    
    # Convert to LiteLLM format
    litellm_messages = []
    if system:
        litellm_messages.append({"role": "system", "content": system})
    litellm_messages.extend(messages)
    
    call_kwargs = {
        'model': model,
        'messages': litellm_messages,
        'max_tokens': max_tokens,
        'temperature': temperature,
        'timeout': timeout,
    }
    
    if tools:
        call_kwargs['tools'] = tools
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
    
    # Convert to Anthropic-style content blocks
    content = None
    if message and message.content:
        content = [{"type": "text", "text": message.content}]
    
    usage = None
    if hasattr(response, 'usage') and response.usage:
        usage = {
            'input_tokens': getattr(response.usage, 'prompt_tokens', 0),
            'output_tokens': getattr(response.usage, 'completion_tokens', 0),
        }
    
    return MessageResult(
        id=getattr(response, 'id', ''),
        content=content,
        role=getattr(message, 'role', 'assistant') if message else 'assistant',
        model=getattr(response, 'model', model),
        stop_reason=getattr(choice, 'finish_reason', None) if choice else None,
        usage=usage,
        metadata=metadata or {},
    )


async def amessages_create(
    messages: List[Dict[str, Any]],
    model: str = "claude-3-5-sonnet-20241022",
    max_tokens: int = 1024,
    system: Optional[str] = None,
    temperature: float = 1.0,
    tools: Optional[List[Dict[str, Any]]] = None,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> MessageResult:
    """
    Async: Create a message using Anthropic-style API.
    
    See messages_create() for full documentation.
    """
    import litellm
    
    litellm_messages = []
    if system:
        litellm_messages.append({"role": "system", "content": system})
    litellm_messages.extend(messages)
    
    call_kwargs = {
        'model': model,
        'messages': litellm_messages,
        'max_tokens': max_tokens,
        'temperature': temperature,
        'timeout': timeout,
    }
    
    if tools:
        call_kwargs['tools'] = tools
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
    
    content = None
    if message and message.content:
        content = [{"type": "text", "text": message.content}]
    
    usage = None
    if hasattr(response, 'usage') and response.usage:
        usage = {
            'input_tokens': getattr(response.usage, 'prompt_tokens', 0),
            'output_tokens': getattr(response.usage, 'completion_tokens', 0),
        }
    
    return MessageResult(
        id=getattr(response, 'id', ''),
        content=content,
        role=getattr(message, 'role', 'assistant') if message else 'assistant',
        model=getattr(response, 'model', model),
        stop_reason=getattr(choice, 'finish_reason', None) if choice else None,
        usage=usage,
        metadata=metadata or {},
    )


def count_tokens(
    messages: List[Dict[str, Any]],
    model: str = "gpt-4o-mini",
    system: Optional[str] = None,
    api_key: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> TokenCountResult:
    """
    Count tokens in messages.
    
    Args:
        messages: List of messages
        model: Model to use for tokenization
        system: System prompt
        api_key: Optional API key override
        metadata: Optional metadata for tracing
        
    Returns:
        TokenCountResult with token count
        
    Example:
        >>> result = count_tokens([{"role": "user", "content": "Hello"}])
        >>> print(result.input_tokens)
    """
    import litellm
    
    all_messages = []
    if system:
        all_messages.append({"role": "system", "content": system})
    all_messages.extend(messages)
    
    try:
        token_count = litellm.token_counter(model=model, messages=all_messages)
    except Exception:
        # Fallback: estimate tokens
        text = ""
        for msg in all_messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                text += content
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text += item.get("text", "")
        # Rough estimate: 4 chars per token
        token_count = len(text) // 4
    
    return TokenCountResult(
        input_tokens=token_count,
        model=model,
        metadata=metadata or {},
    )


async def acount_tokens(
    messages: List[Dict[str, Any]],
    model: str = "gpt-4o-mini",
    system: Optional[str] = None,
    api_key: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> TokenCountResult:
    """
    Async: Count tokens in messages.
    
    See count_tokens() for full documentation.
    """
    # Token counting is synchronous, just wrap it
    return count_tokens(
        messages=messages,
        model=model,
        system=system,
        api_key=api_key,
        metadata=metadata,
        **kwargs
    )
