"""
Memory module for PraisonAI Agents

This module provides memory management capabilities including:
- Short-term memory (STM) for ephemeral context
- Long-term memory (LTM) for persistent knowledge  
- Entity memory for structured data
- User memory for preferences/history
- Quality-based storage decisions
- Graph memory support via Mem0
- Enhanced storage backends (MongoDB, PostgreSQL, Redis, DynamoDB, Cloud Storage)
"""

try:
    # Try to import enhanced memory with new storage backends
    from .enhanced_memory import Memory
    ENHANCED_AVAILABLE = True
except ImportError:
    # Fallback to original memory implementation
    from .memory import Memory
    ENHANCED_AVAILABLE = False

__all__ = ["Memory"] 