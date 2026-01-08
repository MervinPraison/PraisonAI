"""
Mem0 Adapter for PraisonAI Knowledge Store.

Implements KnowledgeStoreProtocol using mem0 as the backend.
Handles all normalization to ensure metadata is ALWAYS a dict (never None).

LAZY IMPORT: mem0 is only imported when this adapter is instantiated.
"""

import logging
import os
from typing import Any, Dict, List, Optional

from ..models import (
    AddResult,
    SearchResult,
    SearchResultItem,
    normalize_search_item,
)
from ..protocols import ScopeRequiredError

logger = logging.getLogger(__name__)


class Mem0Adapter:
    """
    Adapter implementing KnowledgeStoreProtocol for mem0 backend.
    
    Features:
    - Lazy imports mem0 only when instantiated
    - Normalizes all results (metadata None → {})
    - Enforces scope requirements (user_id/agent_id/run_id)
    - Maps mem0 field names to standard schema (memory → text)
    - Disables telemetry by default
    
    Usage:
        adapter = Mem0Adapter(config={...})
        results = adapter.search("query", user_id="user123")
    """
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        disable_telemetry: bool = True,
    ):
        """
        Initialize Mem0 adapter.
        
        Args:
            config: mem0 configuration dict
            disable_telemetry: Whether to disable mem0 telemetry (default True)
        """
        self._config = config or {}
        self._memory = None
        self._disable_telemetry = disable_telemetry
        
        # Disable telemetry before importing mem0
        if disable_telemetry:
            os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
    
    @property
    def memory(self):
        """Lazy load mem0 Memory instance."""
        if self._memory is None:
            self._memory = self._init_mem0()
        return self._memory
    
    def _init_mem0(self):
        """Initialize mem0 Memory with config."""
        try:
            from mem0 import Memory
        except ImportError:
            raise ImportError(
                "mem0 is not installed. Install with: pip install mem0ai"
            )
        
        if self._config:
            return Memory.from_config(self._config)
        return Memory()
    
    def _check_scope(
        self,
        user_id: Optional[str],
        agent_id: Optional[str],
        run_id: Optional[str],
        operation: str = "operation",
    ) -> None:
        """
        Check that at least one scope identifier is provided.
        
        mem0 requires at least one of user_id, agent_id, or run_id.
        
        Raises:
            ScopeRequiredError: If no scope identifier is provided
        """
        if not any([user_id, agent_id, run_id]):
            raise ScopeRequiredError(
                message=(
                    f"mem0 {operation} requires at least one of 'user_id', "
                    f"'agent_id', or 'run_id'. Please provide at least one "
                    f"identifier to scope the {operation}."
                ),
                backend="mem0",
            )
    
    def _normalize_mem0_item(self, raw: Dict[str, Any]) -> SearchResultItem:
        """
        Normalize a mem0 result item to SearchResultItem.
        
        Handles mem0-specific field names and ensures metadata is dict.
        
        Args:
            raw: Raw mem0 result dict
            
        Returns:
            SearchResultItem with guaranteed schema
        """
        if raw is None:
            return SearchResultItem()
        
        # Use the canonical normalization function
        item = normalize_search_item(raw)
        
        # mem0 specific: extract user_id/agent_id/run_id from top level
        # and add to metadata if present
        for key in ["user_id", "agent_id", "run_id"]:
            if key in raw and raw[key] is not None:
                item.metadata[key] = raw[key]
        
        return item
    
    def _normalize_mem0_results(self, raw: Any) -> SearchResult:
        """
        Normalize mem0 search results to SearchResult.
        
        Args:
            raw: Raw mem0 results (dict with 'results' key or list)
            
        Returns:
            SearchResult with normalized items
        """
        if raw is None:
            return SearchResult()
        
        # Handle dict with 'results' key (standard mem0 format)
        if isinstance(raw, dict):
            items = raw.get("results", []) or []
            normalized_items = [
                self._normalize_mem0_item(item)
                for item in items
                if item is not None
            ]
            return SearchResult(
                results=normalized_items,
                metadata=raw.get("relations", {}) if "relations" in raw else {},
            )
        
        # Handle list of results
        if isinstance(raw, list):
            normalized_items = [
                self._normalize_mem0_item(item)
                for item in raw
                if item is not None
            ]
            return SearchResult(results=normalized_items)
        
        return SearchResult()
    
    def search(
        self,
        query: str,
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None,
        rerank: bool = True,
        **kwargs: Any,
    ) -> SearchResult:
        """
        Search for relevant content in mem0.
        
        Args:
            query: Search query string
            user_id: User identifier for scoping
            agent_id: Agent identifier for scoping
            run_id: Run identifier for scoping
            limit: Maximum number of results
            filters: Optional metadata filters
            rerank: Whether to use mem0 reranking (default True)
            **kwargs: Additional mem0 search options
            
        Returns:
            SearchResult with normalized items (metadata always dict)
            
        Raises:
            ScopeRequiredError: If no scope identifier is provided
        """
        self._check_scope(user_id, agent_id, run_id, "search")
        
        try:
            raw_results = self.memory.search(
                query=query,
                user_id=user_id,
                agent_id=agent_id,
                run_id=run_id,
                limit=limit,
                filters=filters,
                rerank=rerank,
                **kwargs,
            )
            return self._normalize_mem0_results(raw_results)
        except Exception as e:
            logger.warning(f"mem0 search failed: {e}")
            return SearchResult(metadata={"error": str(e)})
    
    def add(
        self,
        content: Any,
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> AddResult:
        """
        Add content to mem0.
        
        Args:
            content: Content to add (string or messages list)
            user_id: User identifier for scoping
            agent_id: Agent identifier for scoping
            run_id: Run identifier for scoping
            metadata: Optional metadata to attach
            **kwargs: Additional mem0 add options
            
        Returns:
            AddResult with operation status
            
        Raises:
            ScopeRequiredError: If no scope identifier is provided
        """
        self._check_scope(user_id, agent_id, run_id, "add")
        
        try:
            # Convert content to messages format for mem0
            if isinstance(content, str):
                messages = [{"role": "user", "content": content}]
            elif isinstance(content, list):
                messages = content
            else:
                messages = [{"role": "user", "content": str(content)}]
            
            result = self.memory.add(
                messages=messages,
                user_id=user_id,
                agent_id=agent_id,
                run_id=run_id,
                metadata=metadata,
                **kwargs,
            )
            
            # Extract ID from result
            result_id = ""
            if isinstance(result, dict):
                result_id = result.get("id", "")
            elif isinstance(result, list) and result:
                result_id = result[0].get("id", "") if isinstance(result[0], dict) else ""
            
            return AddResult(
                id=str(result_id),
                success=True,
                message="Content added successfully",
                metadata={"raw_result": result} if result else {},
            )
        except Exception as e:
            logger.error(f"mem0 add failed: {e}")
            return AddResult(
                success=False,
                message=str(e),
                metadata={"error": str(e)},
            )
    
    def get(
        self,
        item_id: str,
        **kwargs: Any,
    ) -> Optional[SearchResultItem]:
        """
        Get a specific item by ID from mem0.
        
        Args:
            item_id: ID of the item to retrieve
            **kwargs: Additional options
            
        Returns:
            SearchResultItem if found, None otherwise
        """
        try:
            raw = self.memory.get(item_id)
            if raw is None:
                return None
            return self._normalize_mem0_item(raw)
        except Exception as e:
            logger.warning(f"mem0 get failed: {e}")
            return None
    
    def get_all(
        self,
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        limit: int = 100,
        **kwargs: Any,
    ) -> SearchResult:
        """
        Get all items from mem0, optionally filtered by scope.
        
        Args:
            user_id: User identifier for scoping
            agent_id: Agent identifier for scoping
            run_id: Run identifier for scoping
            limit: Maximum number of results
            **kwargs: Additional options
            
        Returns:
            SearchResult with all matching items
            
        Raises:
            ScopeRequiredError: If no scope identifier is provided
        """
        self._check_scope(user_id, agent_id, run_id, "get_all")
        
        try:
            raw_results = self.memory.get_all(
                user_id=user_id,
                agent_id=agent_id,
                run_id=run_id,
                **kwargs,
            )
            return self._normalize_mem0_results(raw_results)
        except Exception as e:
            logger.warning(f"mem0 get_all failed: {e}")
            return SearchResult(metadata={"error": str(e)})
    
    def update(
        self,
        item_id: str,
        content: Any,
        **kwargs: Any,
    ) -> AddResult:
        """
        Update an existing item in mem0.
        
        Args:
            item_id: ID of the item to update
            content: New content
            **kwargs: Additional options
            
        Returns:
            AddResult with operation status
        """
        try:
            result = self.memory.update(item_id, str(content))
            return AddResult(
                id=item_id,
                success=True,
                message=result.get("message", "Updated successfully") if isinstance(result, dict) else "Updated",
            )
        except Exception as e:
            logger.error(f"mem0 update failed: {e}")
            return AddResult(
                id=item_id,
                success=False,
                message=str(e),
                metadata={"error": str(e)},
            )
    
    def delete(
        self,
        item_id: str,
        **kwargs: Any,
    ) -> bool:
        """
        Delete an item by ID from mem0.
        
        Args:
            item_id: ID of the item to delete
            **kwargs: Additional options
            
        Returns:
            True if deleted, False otherwise
        """
        try:
            self.memory.delete(item_id)
            return True
        except Exception as e:
            logger.warning(f"mem0 delete failed: {e}")
            return False
    
    def delete_all(
        self,
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        **kwargs: Any,
    ) -> bool:
        """
        Delete all items matching scope from mem0.
        
        Args:
            user_id: User identifier for scoping
            agent_id: Agent identifier for scoping
            run_id: Run identifier for scoping
            **kwargs: Additional options
            
        Returns:
            True if operation succeeded
            
        Raises:
            ScopeRequiredError: If no scope identifier is provided
        """
        self._check_scope(user_id, agent_id, run_id, "delete_all")
        
        try:
            self.memory.delete_all(
                user_id=user_id,
                agent_id=agent_id,
                run_id=run_id,
            )
            return True
        except Exception as e:
            logger.warning(f"mem0 delete_all failed: {e}")
            return False
    
    def history(
        self,
        item_id: str,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """
        Get history of changes for an item.
        
        Args:
            item_id: ID of the item
            **kwargs: Additional options
            
        Returns:
            List of history entries
        """
        try:
            return self.memory.history(item_id)
        except Exception as e:
            logger.warning(f"mem0 history failed: {e}")
            return []
