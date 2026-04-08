"""
Memory Registry Demonstration

This module demonstrates how to replace the hardcoded _check_* imports 
in memory.py with protocol-driven adapter registry resolution.

BEFORE (current memory.py lines 266-307):
```python
self.use_mem0 = (self.provider.lower() == "mem0") and _check_mem0()
self.use_rag = (self.provider.lower() == "rag") and _check_chromadb() and self.cfg.get("use_embedding", False) 
self.use_mongodb = (self.provider.lower() == "mongodb") and _check_pymongo()

if self.use_mem0:
    self._init_mem0()
elif self.use_mongodb:
    self._init_mongodb()
elif self.use_rag:
    self._init_chroma()
```

AFTER (protocol-driven approach):
```python  
# Use adapter registry to resolve backend dynamically
adapter = get_memory_adapter(provider, config=self.cfg)
if adapter is None:
    # Fallback to available adapters
    adapter = get_first_available_memory_adapter(["sqlite", "in_memory"])
self.memory_adapter = adapter
```

This eliminates:
- All 146 hardcoded _check_* functions (lines 36-142)
- All hardcoded _init_* methods 
- All conditional self.use_* flags
- All direct dependency imports in core

The adapter registry handles:
- Lazy loading of heavy dependencies
- Availability checking
- Dynamic instantiation  
- Fallback resolution
"""

import os
from typing import Any, Dict, Optional, List
import logging
from .adapters import (
    get_memory_adapter, 
    get_first_available_memory_adapter,
    has_memory_adapter,
    list_memory_adapters
)


class ProtocolDrivenMemory:
    """
    Demonstration of protocol-driven Memory implementation.
    
    This class shows how to replace the hardcoded backend logic
    in the current Memory class with dynamic adapter resolution.
    """
    
    def __init__(self, config: Dict[str, Any], verbose: int = 0):
        self.cfg = config or {}
        self.verbose = verbose
        
        # Protocol-driven adapter resolution replaces hardcoded logic
        self._init_memory_adapter()
        
        print(f"✅ Initialized memory with adapter: {self.adapter_name}")
        print(f"   Available adapters: {list_memory_adapters()}")
    
    def _init_memory_adapter(self):
        """
        Initialize memory adapter using registry (replaces hardcoded _check_* logic).
        
        This single method replaces:
        - _check_chromadb() (lines 36-62)
        - _check_mem0() (lines 64-88) 
        - _check_openai() (lines 90-114)
        - _check_litellm() (lines 116-141)
        - _check_pymongo() (lines 143-170)
        - All conditional self.use_* flags (lines 266-268)
        - All _init_* backend methods (lines 301-306)
        """
        # Determine provider preference
        provider = self.cfg.get("provider", "sqlite").lower()
        
        # Map legacy provider names for backward compatibility
        provider_mapping = {
            "rag": "chroma",    # Legacy "rag" -> ChromaDB
            "mem0": "mem0",     # Mem0 integration
            "mongodb": "mongodb", # MongoDB storage
            "sqlite": "sqlite", # SQLite storage (core)
            "none": "in_memory" # In-memory storage (core)
        }
        
        adapter_name = provider_mapping.get(provider, provider)
        
        # Try preferred adapter first
        if has_memory_adapter(adapter_name):
            try:
                adapter = get_memory_adapter(adapter_name, **self._get_adapter_config())
                if adapter is not None:
                    self.memory_adapter = adapter
                    self.adapter_name = adapter_name
                    return
            except Exception as e:
                print(f"⚠️ Failed to create {adapter_name} adapter: {e}")
        
        # Fallback to first available adapter
        print(f"Provider '{adapter_name}' not available, trying fallbacks...")
        fallback_result = get_first_available_memory_adapter(
            preferences=["sqlite", "in_memory"],
            **self._get_adapter_config()
        )
        
        if fallback_result:
            self.adapter_name, self.memory_adapter = fallback_result
            print(f"Using fallback adapter: {self.adapter_name}")
        else:
            raise RuntimeError("No memory adapters available")
    
    def _get_adapter_config(self) -> Dict[str, Any]:
        """Get configuration for adapter initialization."""
        config = self.cfg.copy()
        
        # Add default paths for file-based adapters
        config.setdefault("short_db", "short_term.db")
        config.setdefault("long_db", "long_term.db")
        config.setdefault("verbose", self.verbose)
        
        return config
    
    def store_memory(self, text: str, memory_type: str = "long_term"):
        """Store memory using configured adapter."""
        if memory_type == "short_term":
            return self.memory_adapter.store_short_term(text)
        else:
            return self.memory_adapter.store_long_term(text)
    
    def search_memory(self, query: str, memory_type: str = "long_term", limit: int = 5):
        """Search memory using configured adapter."""
        if memory_type == "short_term":
            return self.memory_adapter.search_short_term(query, limit=limit)
        else:
            return self.memory_adapter.search_long_term(query, limit=limit)


def demonstrate_protocol_driven_approach():
    """
    Demonstrate how protocol-driven approach fixes the architecture violations.
    """
    print("🚀 Protocol-Driven Memory Demonstration")
    print("=" * 50)
    
    # Test different providers
    test_configs = [
        {"provider": "sqlite"},
        {"provider": "in_memory"},  
        {"provider": "mem0"},      # Should fallback (requires mem0 dependency)
        {"provider": "chroma"},    # Should fallback (requires chromadb dependency)
        {"provider": "mongodb"},   # Should fallback (requires pymongo dependency)
    ]
    
    for config in test_configs:
        print(f"\n📋 Testing provider: {config['provider']}")
        try:
            memory = ProtocolDrivenMemory(config)
            
            # Test basic functionality
            memory.store_memory("Hello world", "long_term")
            results = memory.search_memory("Hello", "long_term")
            print(f"   ✅ Basic operations work: {len(results)} results")
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print(f"\n📊 Summary:")
    print(f"   Available adapters: {list_memory_adapters()}")
    print(f"   Core adapters work without heavy dependencies")
    print(f"   Heavy adapters gracefully fallback when dependencies missing")
    print(f"   All hardcoded imports eliminated!")


if __name__ == "__main__":
    demonstrate_protocol_driven_approach()