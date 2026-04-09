"""
Structured result types for memory operations.

Provides type-safe return values that distinguish between success, failure, 
and fallback scenarios for memory storage and retrieval operations.
Enables proper error handling and observability in multi-agent workflows.
"""

from typing import Optional, Any, Dict, Literal, Union
from dataclasses import dataclass
from enum import Enum


class MemoryResultStatus(Enum):
    """Status of a memory operation."""
    SUCCESS = "success"
    FALLBACK = "fallback" 
    FAILED = "failed"


@dataclass
class MemoryResult:
    """
    Structured result for memory operations.
    
    Replaces silent failures and empty string returns with explicit
    status information and error context for better debugging and
    observability in production deployments.
    
    Example:
        ```python
        # Instead of silent failure returning ""
        result = memory.store_short_term("content")
        if result.status == MemoryResultStatus.FAILED:
            handle_failure(result.error_message)
        elif result.status == MemoryResultStatus.FALLBACK:
            log_fallback_warning(result.fallback_reason)
        ```
    """
    
    status: MemoryResultStatus
    memory_id: Optional[str] = None
    error_message: Optional[str] = None
    fallback_reason: Optional[str] = None
    adapter_used: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    
    @property
    def success(self) -> bool:
        """Returns True if the operation succeeded (including fallback)."""
        return self.status in (MemoryResultStatus.SUCCESS, MemoryResultStatus.FALLBACK)
    
    @property
    def failed(self) -> bool:
        """Returns True if the operation completely failed."""
        return self.status == MemoryResultStatus.FAILED
    
    @property
    def used_fallback(self) -> bool:
        """Returns True if a fallback adapter was used."""
        return self.status == MemoryResultStatus.FALLBACK
    
    @classmethod
    def success_result(cls, memory_id: str, adapter_used: str = "primary", 
                      context: Optional[Dict[str, Any]] = None) -> "MemoryResult":
        """Create a successful memory result."""
        return cls(
            status=MemoryResultStatus.SUCCESS,
            memory_id=memory_id,
            adapter_used=adapter_used,
            context=context or {}
        )
    
    @classmethod
    def fallback_result(cls, memory_id: str, fallback_reason: str,
                       adapter_used: str = "fallback", 
                       context: Optional[Dict[str, Any]] = None) -> "MemoryResult":
        """Create a fallback memory result."""
        return cls(
            status=MemoryResultStatus.FALLBACK,
            memory_id=memory_id,
            fallback_reason=fallback_reason,
            adapter_used=adapter_used,
            context=context or {}
        )
    
    @classmethod
    def failed_result(cls, error_message: str, 
                     context: Optional[Dict[str, Any]] = None) -> "MemoryResult":
        """Create a failed memory result."""
        return cls(
            status=MemoryResultStatus.FAILED,
            error_message=error_message,
            context=context or {}
        )
    
    def to_legacy_string(self) -> str:
        """
        Convert to legacy empty string return format for backward compatibility.
        
        Returns the memory_id or empty string to maintain compatibility
        with existing code that expects string returns.
        """
        return self.memory_id or ""


@dataclass 
class SearchResult:
    """
    Structured result for memory search operations.
    """
    
    status: MemoryResultStatus
    results: list = None
    total_count: int = 0
    query: Optional[str] = None
    error_message: Optional[str] = None
    adapter_used: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.results is None:
            self.results = []
    
    @property
    def success(self) -> bool:
        """Returns True if the search succeeded."""
        return self.status == MemoryResultStatus.SUCCESS
    
    @property
    def failed(self) -> bool:
        """Returns True if the search failed."""
        return self.status == MemoryResultStatus.FAILED
    
    @property
    def has_results(self) -> bool:
        """Returns True if the search returned any results."""
        return len(self.results) > 0
    
    @classmethod
    def success_result(cls, results: list, query: str = "", 
                      adapter_used: str = "primary",
                      context: Optional[Dict[str, Any]] = None) -> "SearchResult":
        """Create a successful search result."""
        return cls(
            status=MemoryResultStatus.SUCCESS,
            results=results,
            total_count=len(results),
            query=query,
            adapter_used=adapter_used,
            context=context or {}
        )
    
    @classmethod
    def failed_result(cls, error_message: str, query: str = "",
                     context: Optional[Dict[str, Any]] = None) -> "SearchResult":
        """Create a failed search result."""
        return cls(
            status=MemoryResultStatus.FAILED,
            results=[],
            total_count=0,
            query=query,
            error_message=error_message,
            context=context or {}
        )
    
    def to_legacy_list(self) -> list:
        """
        Convert to legacy list return format for backward compatibility.
        
        Returns the results list or empty list to maintain compatibility
        with existing code that expects list returns.
        """
        return self.results


# Export main types
__all__ = [
    "MemoryResultStatus",
    "MemoryResult", 
    "SearchResult"
]