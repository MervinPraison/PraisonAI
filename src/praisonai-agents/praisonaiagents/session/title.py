"""
Session Title Auto-Generation - Generate descriptive titles for chat sessions.

Automatically creates concise, meaningful titles based on the first user-assistant
exchange in a conversation. Uses a lightweight model for fast generation.
"""

import asyncio
from typing import Optional

__all__ = ["generate_title", "generate_title_async"]

_DEFAULT_SMALL_MODEL = "gpt-4o-mini"


def _resolve_small_model(llm_model: Optional[str], primary_model: Optional[str]) -> str:
    """Resolve the auxiliary model for title generation.

    An explicit ``llm_model`` always wins. Otherwise the configured
    ``defaults.small_model`` is used, falling back to the primary model and
    finally to the historical ``gpt-4o-mini`` default so existing behaviour is
    preserved when nothing is configured.
    """
    if llm_model:
        return llm_model
    try:
        from ..config.loader import get_small_model
        resolved = get_small_model(primary_model=primary_model, fallback=_DEFAULT_SMALL_MODEL)
        if resolved:
            return resolved
    except Exception:
        pass
    return primary_model or _DEFAULT_SMALL_MODEL


def generate_title(
    user_msg: str, 
    assistant_msg: str,
    llm_model: Optional[str] = None,
    timeout: float = 10.0,
    max_length: int = 60,
    primary_model: Optional[str] = None,
) -> str:
    """Generate a session title from the first exchange.
    
    Args:
        user_msg: First user message
        assistant_msg: First assistant response  
        llm_model: Model to use for title generation. When ``None``, resolves
            to ``defaults.small_model`` (config), then ``primary_model``, then
            a cheap built-in default.
        timeout: Timeout in seconds for generation
        max_length: Maximum title length in characters
        primary_model: The running agent's primary model, used as a fallback
            when no auxiliary/small model is configured.
        
    Returns:
        Generated title string, or fallback based on user message
        
    Examples:
        >>> title = generate_title(
        ...     "Help me debug this Python code",
        ...     "I'd be happy to help debug your Python code..."
        ... )
        >>> # Returns something like: "Python Code Debugging Help"
    """
    # Fallback title from user message if generation fails
    fallback_title = _create_fallback_title(user_msg, max_length)
    
    try:
        # Check if we're already in an event loop
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop - safe to use asyncio.run
        try:
            return asyncio.run(generate_title_async(
                user_msg, assistant_msg, llm_model, timeout, max_length,
                primary_model=primary_model,
            ))
        except Exception:
            import logging
            logger = logging.getLogger(__name__)
            logger.debug("Title generation failed in sync context", exc_info=True)
            return fallback_title
    else:
        # Already in event loop - cannot use asyncio.run
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            "generate_title() called from running event loop; "
            "use generate_title_async() instead. Returning fallback title."
        )
        return fallback_title


async def generate_title_async(
    user_msg: str,
    assistant_msg: str, 
    llm_model: Optional[str] = None,
    timeout: float = 10.0,
    max_length: int = 60,
    primary_model: Optional[str] = None,
) -> str:
    """Async version of generate_title.
    
    Args:
        user_msg: First user message
        assistant_msg: First assistant response
        llm_model: Model to use for title generation. When ``None``, resolves
            to ``defaults.small_model`` (config), then ``primary_model``, then
            a cheap built-in default.
        timeout: Timeout in seconds for generation
        max_length: Maximum title length in characters
        primary_model: The running agent's primary model, used as a fallback
            when no auxiliary/small model is configured.
        
    Returns:
        Generated title string, or fallback based on user message
    """
    fallback_title = _create_fallback_title(user_msg, max_length)
    
    try:
        # Lazy import to avoid circular dependencies
        from ..llm import LLM
        
        # Create prompt for title generation
        prompt = f"""Generate a concise, descriptive title (3-8 words) for this conversation.

USER: {user_msg[:400]}
ASSISTANT: {assistant_msg[:400]}

Return ONLY the title text, no quotes, no explanation."""
        
        # Resolve the auxiliary/small model (config small_model -> primary -> default)
        resolved_model = _resolve_small_model(llm_model, primary_model)

        # Use lightweight model for fast, cheap generation
        llm = LLM(model=resolved_model)
        
        # Generate with timeout
        try:
            response = await asyncio.wait_for(
                llm.aget_response(prompt=prompt),
                timeout=timeout
            )
            
            if response and isinstance(response, str):
                # Clean up the response
                title = response.strip().strip('"').strip("'")
                title = title.replace('\n', ' ').replace('\r', '')
                
                # Truncate if too long
                if len(title) > max_length:
                    title = title[:max_length-3] + "..."
                
                # Return if non-empty
                if title and len(title.strip()) > 0:
                    return title
                    
        except asyncio.TimeoutError:
            # Title generation timed out
            pass
        except Exception:
            # Any other LLM error
            pass
            
    except ImportError:
        # LLM module not available
        pass
    except Exception:
        # Unexpected error
        pass
    
    return fallback_title


def _create_fallback_title(user_msg: str, max_length: int) -> str:
    """Create a fallback title from the user message.
    
    Args:
        user_msg: User message to base title on
        max_length: Maximum length for the title
        
    Returns:
        Simple title based on user message
    """
    if not user_msg or not user_msg.strip():
        return "Chat Session"
    
    # Clean up the message
    clean_msg = user_msg.strip()
    
    # Remove common question words and make it more title-like
    clean_msg = clean_msg.replace('?', '')
    clean_msg = clean_msg.replace('!', '')
    
    # Take first sentence or reasonable chunk
    if '.' in clean_msg:
        clean_msg = clean_msg.split('.')[0]
    
    # Truncate if too long
    if len(clean_msg) > max_length:
        clean_msg = clean_msg[:max_length-3] + "..."
    
    return clean_msg if clean_msg else "Chat Session"