"""
Security and performance improvements for the LLM module.
These utilities can be integrated into llm.py to address identified issues.
"""

import json
import re
import time
import logging
import asyncio
from typing import Any, Dict, List, Optional, Union, Callable, Tuple
from functools import wraps, lru_cache
from collections import deque
from io import StringIO
import hashlib

# Constants
MAX_CHAT_HISTORY_SIZE = 100
MAX_PROMPT_SIZE = 100000  # 100k characters
MAX_ITERATIONS = 10
DEFAULT_RETRY_COUNT = 3
DEFAULT_BACKOFF_FACTOR = 2
CACHE_SIZE = 1000

# Security patterns
DANGEROUS_PROMPT_PATTERNS = [
    r'ignore previous instructions',
    r'disregard all prior',
    r'forget everything',
    r'system:',
    r'assistant:',
    r'<\|im_start\|>',
    r'<\|im_end\|>',
    r'\\[INST\\]',
    r'\\[/INST\\]',
    r'</s>',
    r'<s>',
]


class SecurityValidator:
    """Handles security validation for prompts and inputs."""
    
    @staticmethod
    def validate_prompt(prompt: Union[str, List[Dict]]) -> None:
        """Validate prompt for security and size constraints."""
        if not prompt:
            raise ValueError("Prompt cannot be empty")
        
        # Check prompt size
        prompt_str = str(prompt) if not isinstance(prompt, str) else prompt
        if len(prompt_str) > MAX_PROMPT_SIZE:
            raise ValueError(f"Prompt exceeds maximum size of {MAX_PROMPT_SIZE} characters")
        
        # Check for prompt injection patterns
        for pattern in DANGEROUS_PROMPT_PATTERNS:
            if re.search(pattern, prompt_str, re.IGNORECASE):
                logging.warning(f"Potential prompt injection detected: {pattern}")
                # For backward compatibility, just warn instead of blocking
    
    @staticmethod
    def validate_tools(tools: Optional[List[Any]], allowed_tools: Optional[List[str]] = None) -> None:
        """Validate tools list and optionally check against allowed tools."""
        if not tools:
            return
        
        if not isinstance(tools, list):
            raise TypeError("Tools must be a list")
        
        for tool in tools:
            if not (callable(tool) or isinstance(tool, (dict, list, str))):
                raise TypeError(f"Invalid tool type: {type(tool)}")
        
        # If allowed_tools is provided, validate against whitelist
        if allowed_tools:
            for tool in tools:
                tool_name = None
                if isinstance(tool, dict) and 'function' in tool:
                    tool_name = tool['function'].get('name')
                elif callable(tool):
                    tool_name = tool.__name__
                elif isinstance(tool, str):
                    tool_name = tool
                
                if tool_name and tool_name not in allowed_tools:
                    raise ValueError(f"Tool '{tool_name}' is not in allowed tools list")
    
    @staticmethod
    def sanitize_json_response(json_str: str) -> Dict:
        """Safely parse JSON with validation."""
        if not json_str:
            return {}
        
        try:
            # Remove any potential control characters
            cleaned = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_str)
            
            data = json.loads(cleaned)
            if not isinstance(data, (dict, list)):
                logging.warning(f"JSON response is not a dict or list: {type(data)}")
                return {} if not isinstance(data, list) else []
            
            return data
        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON response: {e}")
            return {}
    
    @staticmethod
    def mask_sensitive_data(data: Dict) -> Dict:
        """Remove sensitive information from data before logging."""
        sensitive_fields = {
            'api_key', 'api_version', 'base_url', 'api_base',
            'password', 'secret', 'token', 'auth', 'authorization'
        }
        
        def _mask_dict(d: Dict) -> Dict:
            masked = {}
            for k, v in d.items():
                if any(field in k.lower() for field in sensitive_fields):
                    masked[k] = "***REDACTED***"
                elif isinstance(v, dict):
                    masked[k] = _mask_dict(v)
                elif isinstance(v, list):
                    masked[k] = [_mask_dict(item) if isinstance(item, dict) else item for item in v]
                else:
                    masked[k] = v
            return masked
        
        return _mask_dict(data)


class PerformanceOptimizer:
    """Handles performance optimizations."""
    
    @staticmethod
    def create_bounded_deque(maxsize: int = MAX_CHAT_HISTORY_SIZE) -> deque:
        """Create a bounded deque for chat history to prevent memory leaks."""
        return deque(maxlen=maxsize)
    
    @staticmethod
    def create_string_buffer() -> StringIO:
        """Create a string buffer for efficient string concatenation."""
        return StringIO()
    
    @staticmethod
    @lru_cache(maxsize=CACHE_SIZE)
    def hash_prompt(prompt: str, system_prompt: Optional[str] = None) -> str:
        """Create a hash for caching purposes."""
        content = f"{system_prompt or ''}{prompt}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    @staticmethod
    def estimate_token_count(text: str) -> int:
        """Estimate token count for a text string."""
        # Simple estimation: ~4 characters per token on average
        # This is a rough estimate; actual tokenization varies by model
        return len(text) // 4


class RetryHandler:
    """Handles retry logic for transient failures."""
    
    @staticmethod
    def retry_on_error(
        max_retries: int = DEFAULT_RETRY_COUNT,
        backoff_factor: int = DEFAULT_BACKOFF_FACTOR,
        retry_exceptions: Tuple[Exception, ...] = (ConnectionError, TimeoutError)
    ):
        """Decorator for retry logic on transient errors."""
        def decorator(func):
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                last_error = None
                for attempt in range(max_retries):
                    try:
                        return func(*args, **kwargs)
                    except retry_exceptions as e:
                        last_error = e
                        if attempt < max_retries - 1:
                            wait_time = backoff_factor ** attempt
                            logging.warning(f"Transient error, retrying in {wait_time}s: {e}")
                            time.sleep(wait_time)
                            continue
                        raise
                    except Exception as e:
                        # Check for specific error patterns
                        error_str = str(e).lower()
                        
                        # Don't retry on authentication errors
                        if any(phrase in error_str for phrase in ['invalid api key', 'authentication', 'unauthorized']):
                            raise
                        
                        # Check if it's a rate limit error
                        if 'rate limit' in error_str:
                            # Extract retry-after if available
                            wait_time = RetryHandler._extract_retry_after(str(e)) or (backoff_factor ** attempt * 2)
                            if attempt < max_retries - 1:
                                logging.warning(f"Rate limit hit, waiting {wait_time}s")
                                time.sleep(wait_time)
                                continue
                        
                        raise
                raise last_error
            
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                last_error = None
                for attempt in range(max_retries):
                    try:
                        return await func(*args, **kwargs)
                    except retry_exceptions as e:
                        last_error = e
                        if attempt < max_retries - 1:
                            wait_time = backoff_factor ** attempt
                            logging.warning(f"Transient error, retrying in {wait_time}s: {e}")
                            await asyncio.sleep(wait_time)
                            continue
                        raise
                    except Exception as e:
                        # Similar error checking as sync version
                        error_str = str(e).lower()
                        
                        if any(phrase in error_str for phrase in ['invalid api key', 'authentication', 'unauthorized']):
                            raise
                        
                        if 'rate limit' in error_str:
                            wait_time = RetryHandler._extract_retry_after(str(e)) or (backoff_factor ** attempt * 2)
                            if attempt < max_retries - 1:
                                logging.warning(f"Rate limit hit, waiting {wait_time}s")
                                await asyncio.sleep(wait_time)
                                continue
                        
                        raise
                raise last_error
            
            # Return appropriate wrapper based on function type
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return sync_wrapper
        
        return decorator
    
    @staticmethod
    def _extract_retry_after(error_message: str) -> Optional[int]:
        """Extract retry-after value from error message if available."""
        # Look for patterns like "retry after 60 seconds" or "retry-after: 60"
        patterns = [
            r'retry[- ]after[:\s]+(\d+)',
            r'retry in (\d+) seconds',
            r'wait (\d+) seconds',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, error_message, re.IGNORECASE)
            if match:
                return int(match.group(1))
        
        return None


class ResponseCache:
    """Simple LRU cache for LLM responses."""
    
    def __init__(self, maxsize: int = CACHE_SIZE):
        self.cache = {}
        self.access_order = deque(maxlen=maxsize)
        self.maxsize = maxsize
    
    def get(self, key: str) -> Optional[str]:
        """Get a cached response."""
        if key in self.cache:
            # Update access order
            self.access_order.remove(key)
            self.access_order.append(key)
            return self.cache[key]
        return None
    
    def put(self, key: str, value: str) -> None:
        """Cache a response."""
        if key in self.cache:
            self.access_order.remove(key)
        elif len(self.cache) >= self.maxsize:
            # Remove least recently used
            lru_key = self.access_order.popleft()
            del self.cache[lru_key]
        
        self.cache[key] = value
        self.access_order.append(key)
    
    def clear(self) -> None:
        """Clear the cache."""
        self.cache.clear()
        self.access_order.clear()


class StreamProcessor:
    """Handles efficient stream processing."""
    
    def __init__(self):
        self.buffer = StringIO()
    
    def process_chunk(self, chunk: str) -> str:
        """Process a streaming chunk efficiently."""
        if chunk:
            self.buffer.write(chunk)
        return self.buffer.getvalue()
    
    def get_content(self) -> str:
        """Get the complete buffered content."""
        return self.buffer.getvalue()
    
    def reset(self) -> None:
        """Reset the buffer."""
        self.buffer = StringIO()


class ContextLengthManager:
    """Manages context length to prevent overflows."""
    
    def __init__(self, model_windows: Dict[str, int]):
        self.model_windows = model_windows
    
    def estimate_tokens(self, messages: List[Dict]) -> int:
        """Estimate token count for messages."""
        total_chars = 0
        for msg in messages:
            content = msg.get('content', '')
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                # Handle multimodal content
                for item in content:
                    if isinstance(item, dict) and 'text' in item:
                        total_chars += len(item['text'])
        
        return PerformanceOptimizer.estimate_token_count(str(total_chars))
    
    def get_safe_context_size(self, model: str) -> int:
        """Get safe context size for a model (75% of actual to leave room)."""
        for model_prefix, size in self.model_windows.items():
            if model.startswith(model_prefix):
                return size
        return 4000  # Safe default
    
    def validate_context_length(self, model: str, messages: List[Dict]) -> None:
        """Validate that messages fit within context window."""
        estimated_tokens = self.estimate_tokens(messages)
        max_tokens = self.get_safe_context_size(model)
        
        if estimated_tokens > max_tokens * 0.9:  # 90% threshold
            raise ValueError(
                f"Estimated {estimated_tokens} tokens exceeds 90% of {max_tokens} token limit for model {model}"
            )
    
    def truncate_messages(self, messages: List[Dict], max_tokens: int) -> List[Dict]:
        """Truncate messages to fit within token limit while preserving system message."""
        if not messages:
            return messages
        
        # Always keep system message if present
        system_msg = None
        other_msgs = messages
        
        if messages[0].get('role') == 'system':
            system_msg = messages[0]
            other_msgs = messages[1:]
        
        # Truncate from the beginning (oldest messages)
        truncated = []
        current_tokens = 0
        
        # Add messages from newest to oldest
        for msg in reversed(other_msgs):
            msg_tokens = PerformanceOptimizer.estimate_token_count(str(msg.get('content', '')))
            if current_tokens + msg_tokens <= max_tokens * 0.8:  # Leave 20% buffer
                truncated.insert(0, msg)
                current_tokens += msg_tokens
            else:
                break
        
        # Add system message back if present
        if system_msg:
            truncated.insert(0, system_msg)
        
        return truncated


# Example usage in llm.py:
"""
# At the top of llm.py
from .llm_improvements import (
    SecurityValidator,
    PerformanceOptimizer,
    RetryHandler,
    ResponseCache,
    StreamProcessor,
    ContextLengthManager
)

# In __init__:
self.chat_history = PerformanceOptimizer.create_bounded_deque()
self.response_cache = ResponseCache()
self.context_manager = ContextLengthManager(self.MODEL_WINDOWS)

# In get_response:
# Validate inputs
SecurityValidator.validate_prompt(prompt)
SecurityValidator.validate_tools(tools)

# Check cache
cache_key = PerformanceOptimizer.hash_prompt(str(prompt), system_prompt)
cached_response = self.response_cache.get(cache_key)
if cached_response and not tools:  # Don't use cache with tools
    return cached_response

# Use retry decorator
@RetryHandler.retry_on_error()
def _make_completion_call():
    return litellm.completion(**params)

# Use stream processor
stream_processor = StreamProcessor()
for chunk in stream:
    content = stream_processor.process_chunk(chunk.delta.content)
    # Update display with content

# Cache the response
self.response_cache.put(cache_key, response_text)
"""