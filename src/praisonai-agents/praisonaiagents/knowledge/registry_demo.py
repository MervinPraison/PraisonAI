"""
Knowledge Registry Demonstration

This module demonstrates how to replace the hardcoded import logic
in knowledge/knowledge.py with protocol-driven adapter registry resolution.

BEFORE (current knowledge.py lines 77-78, 98-100):
```python
# Lines 77-78: Direct hardcoded imports in core  
from markitdown import MarkItDown
import chromadb

# Lines 98-100: Hardcoded provider configuration
base_config = {
    "vector_store": {
        "provider": "chroma",
        "config": {...}
    }
}
```

AFTER (protocol-driven approach):
```python
# Use adapter registry to resolve backend dynamically
adapter = get_knowledge_adapter(provider, config=config)
if adapter is None:
    adapter = get_first_available_knowledge_adapter(["sqlite"])
self.knowledge_adapter = adapter
```

This eliminates:
- Hardcoded `import chromadb` (line 78)
- Hardcoded `from markitdown import MarkItDown` (line 77)  
- Hardcoded provider configurations (lines 98-100)
- Heavy dependencies imported at module level

The adapter registry handles:
- Lazy loading of chromadb/markitdown/mem0/pymongo
- Availability checking
- Dynamic instantiation
- Fallback resolution
"""

import os
from typing import Any, Dict, Optional, List
import logging
from .adapters import (
    get_knowledge_adapter, 
    get_first_available_knowledge_adapter,
    has_knowledge_adapter,
    list_knowledge_adapters
)


class ProtocolDrivenKnowledge:
    """
    Demonstration of protocol-driven Knowledge implementation.
    
    This class shows how to replace the hardcoded backend logic
    in the current Knowledge class with dynamic adapter resolution.
    """
    
    def __init__(self, config: Dict[str, Any] = None, verbose: int = 0):
        self.cfg = config or {}
        self.verbose = verbose
        
        # Protocol-driven adapter resolution replaces hardcoded logic
        self._init_knowledge_adapter()
        
        print(f"✅ Initialized knowledge with adapter: {self.adapter_name}")
        print(f"   Available adapters: {list_knowledge_adapters()}")
    
    def _init_knowledge_adapter(self):
        """
        Initialize knowledge adapter using registry (replaces hardcoded import logic).
        
        This single method replaces:
        - Hardcoded `import chromadb` (line 78)
        - Hardcoded `from markitdown import MarkItDown` (line 77) 
        - Hardcoded provider configurations (lines 98-100)
        - Direct dependency checks and imports
        """
        # Determine provider preference
        vector_config = self.cfg.get("vector_store", {})
        provider = vector_config.get("provider", "sqlite").lower()
        
        # Map legacy provider names for backward compatibility
        provider_mapping = {
            "chroma": "chroma",      # ChromaDB vector store
            "mem0": "mem0",          # Mem0 integration
            "mongodb": "mongodb",    # MongoDB document store
            "sqlite": "sqlite",      # SQLite storage (core)
        }
        
        adapter_name = provider_mapping.get(provider, provider)
        
        # Try preferred adapter first
        if has_knowledge_adapter(adapter_name):
            try:
                adapter = get_knowledge_adapter(adapter_name, **self._get_adapter_config())
                if adapter is not None:
                    self.knowledge_adapter = adapter
                    self.adapter_name = adapter_name
                    return
            except Exception as e:
                print(f"⚠️ Failed to create {adapter_name} adapter: {e}")
        
        # Fallback to first available adapter
        print(f"Provider '{adapter_name}' not available, trying fallbacks...")
        fallback_result = get_first_available_knowledge_adapter(
            preferences=["sqlite"],
            **self._get_adapter_config()
        )
        
        if fallback_result:
            self.adapter_name, self.knowledge_adapter = fallback_result
            print(f"Using fallback adapter: {self.adapter_name}")
        else:
            raise RuntimeError("No knowledge adapters available")
    
    def _get_adapter_config(self) -> Dict[str, Any]:
        """Get configuration for adapter initialization."""
        return {
            "config": self.cfg,
            "verbose": self.verbose,
            "db_path": "knowledge.db"
        }
    
    def add_content(self, content: str, metadata: Dict[str, Any] = None):
        """Add content using configured adapter."""
        return self.knowledge_adapter.add(
            content,
            metadata=metadata or {}
        )
    
    def search_content(self, query: str, limit: int = 5):
        """Search content using configured adapter."""
        result = self.knowledge_adapter.search(query, limit=limit)
        return result.results


def demonstrate_protocol_driven_knowledge():
    """
    Demonstrate how protocol-driven approach fixes the knowledge architecture violations.
    """
    print("🧠 Protocol-Driven Knowledge Demonstration")
    print("=" * 50)
    
    # Test different providers
    test_configs = [
        {"vector_store": {"provider": "sqlite"}},
        {"vector_store": {"provider": "chroma"}},    # Should fallback (requires chromadb dependency)
        {"vector_store": {"provider": "mem0"}},      # Should fallback (requires mem0 dependency)
        {"vector_store": {"provider": "mongodb"}},   # Should fallback (requires pymongo dependency)
    ]
    
    for config in test_configs:
        provider = config["vector_store"]["provider"]
        print(f"\n📋 Testing provider: {provider}")
        try:
            knowledge = ProtocolDrivenKnowledge(config)
            
            # Test basic functionality
            add_result = knowledge.add_content("Hello knowledge world")
            print(f"   ✅ Add result: {add_result.success}")
            
            search_results = knowledge.search_content("Hello")
            print(f"   ✅ Search results: {len(search_results)} items")
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print(f"\n📊 Summary:")
    print(f"   Available adapters: {list_knowledge_adapters()}")
    print(f"   Core adapters work without heavy dependencies")
    print(f"   Heavy adapters gracefully fallback when dependencies missing")
    print(f"   All hardcoded imports eliminated!")


if __name__ == "__main__":
    demonstrate_protocol_driven_knowledge()