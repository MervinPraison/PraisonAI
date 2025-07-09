"""OpenAI client initialization and configuration.

This module handles the initialization of the OpenAI client with proper
API key handling and support for both OpenAI services and local servers
like LM Studio.
"""

import os
from openai import OpenAI

# Constants
LOCAL_SERVER_API_KEY_PLACEHOLDER = "not-needed"

# Initialize OpenAI client with proper API key handling
api_key = os.environ.get("OPENAI_API_KEY")
base_url = os.environ.get("OPENAI_API_BASE") or os.environ.get("OPENAI_BASE_URL")

# For local servers like LM Studio, allow minimal API key
if base_url and not api_key:
    api_key = LOCAL_SERVER_API_KEY_PLACEHOLDER
elif not api_key:
    raise ValueError(
        "OPENAI_API_KEY environment variable is required for the default OpenAI service. "
        "If you are targeting a local server (e.g., LM Studio), ensure OPENAI_API_BASE is set "
        f"(e.g., 'http://localhost:1234/v1') and you can use a placeholder API key by setting OPENAI_API_KEY='{LOCAL_SERVER_API_KEY_PLACEHOLDER}'"
    )

# Global OpenAI client instance
client = OpenAI(api_key=api_key, base_url=base_url)


def get_client() -> OpenAI:
    """Get the configured OpenAI client instance.
    
    Returns:
        OpenAI client instance
    """
    return client


def reinitialize_client(api_key: str = None, base_url: str = None) -> OpenAI:
    """Reinitialize the OpenAI client with new configuration.
    
    Args:
        api_key: New API key (uses environment variable if not provided)
        base_url: New base URL (uses environment variable if not provided)
        
    Returns:
        New OpenAI client instance
    """
    global client
    
    if api_key is None:
        api_key = os.environ.get("OPENAI_API_KEY")
    
    if base_url is None:
        base_url = os.environ.get("OPENAI_API_BASE") or os.environ.get("OPENAI_BASE_URL")
    
    # Apply same logic for local servers
    if base_url and not api_key:
        api_key = LOCAL_SERVER_API_KEY_PLACEHOLDER
    elif not api_key:
        raise ValueError("API key is required")
    
    client = OpenAI(api_key=api_key, base_url=base_url)
    return client


__all__ = [
    'client',
    'get_client',
    'reinitialize_client',
    'LOCAL_SERVER_API_KEY_PLACEHOLDER',
]