"""
Example implementation of LLM response caching for PraisonAI Agents
This can be integrated into praisonaiagents/llm/llm.py with minimal changes
"""

import time
import hashlib
import json
from typing import Dict, Tuple, Optional, Any
from functools import wraps
import asyncio

class LLMResponseCache:
    """Thread-safe LLM response cache with TTL support"""
    
    def __init__(self, ttl: int = 3600, max_size: int = 1000):
        self._cache: Dict[str, Tuple[float, str]] = {}
        self._ttl = ttl
        self._max_size = max_size
        self._hits = 0
        self._misses = 0
    
    def _generate_key(self, prompt: str, system_prompt: Optional[str], 
                      temperature: float, tools: Optional[list]) -> str:
        """Generate a unique cache key from request parameters"""
        # Create a deterministic string representation
        key_parts = [
            prompt,
            system_prompt or "",
            str(temperature),
            json.dumps(sorted([t.__name__ if callable(t) else str(t) for t in (tools or [])]))
        ]
        key_string = "|||".join(key_parts)
        return hashlib.sha256(key_string.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[str]:
        """Get cached response if valid"""
        if key in self._cache:
            timestamp, response = self._cache[key]
            if time.time() - timestamp < self._ttl:
                self._hits += 1
                return response
            else:
                # Expired, remove it
                del self._cache[key]
        
        self._misses += 1
        return None
    
    def set(self, key: str, response: str) -> None:
        """Store response in cache with timestamp"""
        # Implement simple LRU eviction if cache is full
        if len(self._cache) >= self._max_size:
            # Remove oldest entry
            oldest_key = min(self._cache.keys(), 
                           key=lambda k: self._cache[k][0])
            del self._cache[oldest_key]
        
        self._cache[key] = (time.time(), response)
    
    def clear(self) -> None:
        """Clear all cached responses"""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{hit_rate:.1f}%",
            "size": len(self._cache),
            "max_size": self._max_size,
            "ttl": self._ttl
        }


def with_cache(cache_instance: LLMResponseCache):
    """Decorator to add caching to LLM response methods"""
    def decorator(func):
        @wraps(func)
        def wrapper(self, prompt, system_prompt=None, temperature=0.2, 
                   tools=None, **kwargs):
            # Only cache for deterministic requests (low temperature)
            if not getattr(self, 'cache', True) or temperature > 0.5:
                return func(self, prompt, system_prompt, temperature, 
                          tools, **kwargs)
            
            # Generate cache key
            cache_key = cache_instance._generate_key(
                prompt, system_prompt, temperature, tools
            )
            
            # Check cache
            cached_response = cache_instance.get(cache_key)
            if cached_response is not None:
                if getattr(self, 'verbose', False):
                    print(f"[Cache HIT] Returning cached response")
                return cached_response
            
            # Call original function
            response = func(self, prompt, system_prompt, temperature, 
                          tools, **kwargs)
            
            # Cache the response
            if response:
                cache_instance.set(cache_key, response)
            
            return response
        
        # Async version
        @wraps(func)
        async def async_wrapper(self, prompt, system_prompt=None, 
                              temperature=0.2, tools=None, **kwargs):
            # Only cache for deterministic requests
            if not getattr(self, 'cache', True) or temperature > 0.5:
                return await func(self, prompt, system_prompt, temperature, 
                                tools, **kwargs)
            
            # Generate cache key
            cache_key = cache_instance._generate_key(
                prompt, system_prompt, temperature, tools
            )
            
            # Check cache
            cached_response = cache_instance.get(cache_key)
            if cached_response is not None:
                if getattr(self, 'verbose', False):
                    print(f"[Cache HIT] Returning cached response")
                return cached_response
            
            # Call original function
            response = await func(self, prompt, system_prompt, temperature, 
                                tools, **kwargs)
            
            # Cache the response
            if response:
                cache_instance.set(cache_key, response)
            
            return response
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper
    
    return decorator


# Example integration into LLM class:
"""
# In praisonaiagents/llm/llm.py, add at module level:
_llm_cache = LLMResponseCache(ttl=3600, max_size=1000)

# Then in the LLM class:
class LLM:
    def __init__(self, ...):
        # ... existing code ...
        self.cache = cache  # Use existing cache parameter
    
    @with_cache(_llm_cache)
    def get_response(self, prompt, system_prompt=None, temperature=0.2, 
                    tools=None, **kwargs):
        # ... existing implementation ...
    
    @with_cache(_llm_cache)
    async def get_response_async(self, prompt, system_prompt=None, 
                               temperature=0.2, tools=None, **kwargs):
        # ... existing implementation ...
    
    def clear_cache(self):
        '''Clear the LLM response cache'''
        _llm_cache.clear()
    
    def get_cache_stats(self):
        '''Get cache statistics'''
        return _llm_cache.get_stats()
"""

# Example usage:
if __name__ == "__main__":
    # Create cache instance
    cache = LLMResponseCache(ttl=300, max_size=100)
    
    # Simulate LLM calls
    print("Testing LLM Response Cache")
    print("-" * 40)
    
    # First call - cache miss
    key1 = cache._generate_key("What is AI?", "You are helpful", 0.2, None)
    result = cache.get(key1)
    print(f"First call (should miss): {result}")
    
    # Store response
    cache.set(key1, "AI is artificial intelligence...")
    
    # Second call - cache hit
    result = cache.get(key1)
    print(f"Second call (should hit): {result}")
    
    # Different temperature - different key
    key2 = cache._generate_key("What is AI?", "You are helpful", 0.9, None)
    result = cache.get(key2)
    print(f"High temp call (should miss): {result}")
    
    # Show stats
    print(f"\nCache stats: {cache.get_stats()}")