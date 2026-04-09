"""
Core memory functionality for Memory class.

This module contains the core Memory class definition, initialization,
and quality scoring logic. Split from the main memory.py file for better maintainability.
"""

import json
import logging
import threading
import asyncio
from typing import Any, Dict, List, Optional
from datetime import datetime
from .results import MemoryResult, MemoryResultStatus, SearchResult


class MemoryCoreMixin:
    """Mixin class containing core memory functionality for the Memory class."""
    
    def store_short_term(self, content: str, metadata: Optional[Dict] = None, quality_score: Optional[float] = None, 
                        user_id: Optional[str] = None, auto_promote: bool = True, **kwargs) -> str:
        """
        Store content in short-term memory using protocol-driven approach.
        
        Args:
            content: The content to store
            metadata: Optional metadata dictionary
            quality_score: Optional pre-calculated quality score
            user_id: Optional user identifier
            auto_promote: Whether to automatically promote to LTM if quality is high
            **kwargs: Additional provider-specific arguments
            
        Returns:
            The memory ID of the stored content
        """
        if not content.strip():
            return ""
        
        # Calculate quality score if not provided
        if quality_score is None:
            quality_score = self.compute_quality_score(content, metadata)
        
        # Prepare metadata
        if metadata is None:
            metadata = {}
        
        if user_id:
            metadata['user_id'] = user_id
        
        metadata['timestamp'] = datetime.now().isoformat()
        metadata['quality'] = quality_score
        
        # Sanitize metadata for storage
        clean_metadata = self._sanitize_metadata(metadata)
        
        # Protocol-driven storage: Delegate to adapter first
        memory_id = None
        try:
            if hasattr(self, 'memory_adapter') and self.memory_adapter:
                memory_id = self.memory_adapter.store_short_term(content, metadata=clean_metadata, **kwargs)
                self._log_verbose(f"Stored in {self.provider} STM via adapter: {content[:100]}...")
        except Exception as e:
            self._log_verbose(f"Failed to store in {self.provider} STM: {e}", logging.WARNING)
        
        # Backward compatibility: Also store in SQLite if not using SQLite adapter
        if hasattr(self, '_sqlite_adapter') and self._sqlite_adapter != getattr(self, 'memory_adapter', None):
            try:
                fallback_id = self._sqlite_adapter.store_short_term(content, metadata=clean_metadata, **kwargs)
                if not memory_id:
                    memory_id = fallback_id
            except Exception as e:
                logging.error(f"Failed to store in SQLite STM fallback: {e}")
                if not memory_id:
                    return ""
        
        # Auto-promote to long-term memory if quality is high
        if auto_promote and quality_score >= 7.5:  # High quality threshold
            try:
                self.store_long_term(content, clean_metadata, quality_score, user_id, **kwargs)
                self._log_verbose(f"Auto-promoted STM content to LTM (score: {quality_score:.2f})")
            except Exception as e:
                logging.warning(f"Failed to auto-promote to LTM: {e}")
        
        # Emit memory event
        self._emit_memory_event("store", "short_term", content, clean_metadata)
        
        return memory_id or ""
    
    def store_short_term_structured(self, content: str, metadata: Optional[Dict] = None, 
                                   quality_score: Optional[float] = None, 
                                   user_id: Optional[str] = None, 
                                   auto_promote: bool = True, **kwargs) -> MemoryResult:
        """
        Store content in short-term memory with structured error handling.
        
        Returns a MemoryResult that distinguishes between success, fallback,
        and failure scenarios instead of silently returning empty strings.
        
        Args:
            content: The content to store
            metadata: Optional metadata dictionary
            quality_score: Optional pre-calculated quality score
            user_id: Optional user identifier
            auto_promote: Whether to auto-promote high-quality content to long-term memory
            **kwargs: Additional provider-specific arguments
            
        Returns:
            MemoryResult with status, memory_id, and error context
        """
        if not content.strip():
            return MemoryResult.failed_result("Empty content cannot be stored")
        
        # Calculate quality score if not provided
        if quality_score is None:
            quality_score = self._calculate_quality_score(content)
        
        # Prepare metadata with quality score
        metadata = metadata or {}
        metadata['quality'] = quality_score
        
        # Sanitize metadata for storage
        clean_metadata = self._sanitize_metadata(metadata)
        
        # Protocol-driven storage: Try primary adapter first
        primary_error = None
        memory_id = None
        
        try:
            if hasattr(self, 'memory_adapter') and self.memory_adapter:
                memory_id = self.memory_adapter.store_short_term(content, metadata=clean_metadata, **kwargs)
                self._log_verbose(f"Stored in {self.provider} STM via adapter: {content[:100]}...")
                
                # Auto-promote to long-term memory if quality is high
                if auto_promote and quality_score >= 7.5:
                    try:
                        self.store_long_term(content, clean_metadata, quality_score, user_id, **kwargs)
                        self._log_verbose(f"Auto-promoted STM content to LTM (score: {quality_score:.2f})")
                    except Exception as e:
                        # Auto-promotion failure doesn't affect the primary storage result
                        logging.warning(f"Failed to auto-promote to LTM: {e}")
                
                # Emit memory event for successful storage
                self._emit_memory_event("store", "short_term", content, clean_metadata)
                
                return MemoryResult.success_result(
                    memory_id=memory_id, 
                    adapter_used=self.provider,
                    context={
                        "quality_score": quality_score,
                        "auto_promoted": auto_promote and quality_score >= 7.5
                    }
                )
        except Exception as e:
            primary_error = str(e)
            self._log_verbose(f"Failed to store in {self.provider} STM: {e}", logging.WARNING)
        
        # Fallback to SQLite if available and different from primary adapter
        fallback_error = None
        if hasattr(self, '_sqlite_adapter') and self._sqlite_adapter != getattr(self, 'memory_adapter', None):
            try:
                fallback_id = self._sqlite_adapter.store_short_term(content, metadata=clean_metadata, **kwargs)
                
                # Emit memory event for fallback storage
                self._emit_memory_event("store", "short_term", content, clean_metadata)
                
                return MemoryResult.fallback_result(
                    memory_id=fallback_id,
                    fallback_reason=f"Primary adapter failed: {primary_error}",
                    adapter_used="sqlite",
                    context={
                        "quality_score": quality_score,
                        "primary_error": primary_error
                    }
                )
            except Exception as e:
                fallback_error = str(e)
                logging.error(f"Failed to store in SQLite STM fallback: {e}")
        
        # Complete failure - both primary and fallback failed
        return MemoryResult.failed_result(
            error_message=f"All storage adapters failed. Primary: {primary_error}, Fallback: {fallback_error}",
            context={
                "primary_error": primary_error,
                "fallback_error": fallback_error,
                "quality_score": quality_score
            }
        )
    
    def store_long_term(self, content: str, metadata: Optional[Dict] = None, quality_score: Optional[float] = None,
                       user_id: Optional[str] = None, **kwargs) -> str:
        """
        Store content in long-term memory using protocol-driven approach.
        
        Args:
            content: The content to store
            metadata: Optional metadata dictionary
            quality_score: Optional pre-calculated quality score
            user_id: Optional user identifier
            **kwargs: Additional provider-specific arguments
            
        Returns:
            The memory ID of the stored content
        """
        if not content.strip():
            return ""
        
        # Calculate quality score if not provided
        if quality_score is None:
            quality_score = self.compute_quality_score(content, metadata)
        
        # Only store high-quality content in LTM
        if quality_score < 5.0:  # Minimum quality threshold for LTM
            self._log_verbose(f"Content quality too low for LTM: {quality_score:.2f}")
            return ""
        
        # Prepare metadata
        if metadata is None:
            metadata = {}
        
        if user_id:
            metadata['user_id'] = user_id
        
        metadata['timestamp'] = datetime.now().isoformat()
        metadata['promoted_at'] = datetime.now().isoformat()
        metadata['quality'] = quality_score
        
        # Sanitize metadata for storage
        clean_metadata = self._sanitize_metadata(metadata)
        
        # Protocol-driven storage: Delegate to adapter first
        memory_id = None
        try:
            if hasattr(self, 'memory_adapter') and self.memory_adapter:
                memory_id = self.memory_adapter.store_long_term(content, metadata=clean_metadata, **kwargs)
                self._log_verbose(f"Stored in {self.provider} LTM via adapter: {content[:100]}...")
        except Exception as e:
            self._log_verbose(f"Failed to store in {self.provider} LTM: {e}", logging.WARNING)
        
        # Backward compatibility: Also store in SQLite if not using SQLite adapter  
        if hasattr(self, '_sqlite_adapter') and self._sqlite_adapter != getattr(self, 'memory_adapter', None):
            try:
                fallback_id = self._sqlite_adapter.store_long_term(content, metadata=clean_metadata, **kwargs)
                if not memory_id:
                    memory_id = fallback_id
            except Exception as e:
                logging.error(f"Failed to store in SQLite LTM fallback: {e}")
                if not memory_id:
                    return ""
        
        # Emit memory event
        self._emit_memory_event("store", "long_term", content, clean_metadata)
        
        return memory_id or ""
    
    def compute_quality_score(self, content: str, metadata: Optional[Dict] = None,
                            user_engagement: Optional[Dict] = None, context: Optional[str] = None) -> float:
        """
        Compute a quality score for memory content (0-10 scale).
        
        Args:
            content: The content to score
            metadata: Optional metadata for context
            user_engagement: Optional user interaction data
            context: Optional conversation context
            
        Returns:
            Quality score between 0.0 and 10.0
        """
        if not content or not content.strip():
            return 0.0
        
        score = 5.0  # Base score
        
        # Content length factors
        content_length = len(content.strip())
        if content_length < 10:
            score -= 2.0  # Too short
        elif content_length > 500:
            score += 1.0  # Comprehensive
        elif content_length > 100:
            score += 0.5  # Good length
        
        # Content complexity and richness
        word_count = len(content.split())
        unique_words = len(set(content.lower().split()))
        
        if word_count > 0:
            vocabulary_richness = unique_words / word_count
            score += min(vocabulary_richness * 2, 1.5)
        
        # Look for structured information
        if any(marker in content.lower() for marker in [':', '-', '•', '\n', '\t']):
            score += 0.5  # Structured content bonus
        
        # Look for specific types of valuable content
        valuable_keywords = [
            'definition', 'explain', 'process', 'step', 'method', 'approach',
            'important', 'key', 'critical', 'remember', 'note', 'warning',
            'example', 'instance', 'case', 'scenario', 'situation'
        ]
        
        keyword_matches = sum(1 for keyword in valuable_keywords if keyword in content.lower())
        score += min(keyword_matches * 0.3, 1.0)
        
        # User engagement factors
        if user_engagement:
            follow_ups = user_engagement.get('follow_up_questions', 0)
            score += min(follow_ups * 0.5, 1.0)
            
            if user_engagement.get('bookmarked', False):
                score += 1.0
            
            if user_engagement.get('shared', False):
                score += 0.5
        
        # Context relevance
        if context:
            context_words = set(context.lower().split())
            content_words = set(content.lower().split())
            overlap = len(context_words.intersection(content_words))
            
            if overlap > 0:
                relevance_score = min(overlap / len(content_words), 0.3)
                score += relevance_score * 2
        
        # Metadata factors
        if metadata:
            if metadata.get('importance') == 'high':
                score += 1.5
            elif metadata.get('importance') == 'medium':
                score += 0.5
            
            if metadata.get('verified', False):
                score += 1.0
            
            if metadata.get('source') in ['expert', 'documentation', 'official']:
                score += 1.0
        
        # Ensure score is within bounds
        score = max(0.0, min(10.0, score))
        
        return round(score, 2)
    
    def _sanitize_metadata(self, metadata: Dict) -> Dict:
        """Sanitize metadata to ensure it's JSON serializable."""
        if not isinstance(metadata, dict):
            return {}
        
        sanitized = {}
        for key, value in metadata.items():
            try:
                # Ensure key is string
                str_key = str(key)
                
                # Handle various value types
                if value is None:
                    sanitized[str_key] = None
                elif isinstance(value, (str, int, float, bool)):
                    sanitized[str_key] = value
                elif isinstance(value, (list, dict)):
                    # Try to serialize to ensure it's JSON-safe
                    json.dumps(value)
                    sanitized[str_key] = value
                else:
                    # Convert other types to string
                    sanitized[str_key] = str(value)
                    
            except (ValueError, TypeError) as e:
                logging.warning(f"Skipping non-serializable metadata key '{key}': {e}")
                continue
        
        return sanitized
    
    def _log_verbose(self, msg: str, level: int = logging.INFO):
        """Log message if verbose mode is enabled."""
        if self.verbose >= 1:
            logger.log(level, msg)
    
    def _emit_memory_event(self, event_type: str, memory_type: str, content: str, metadata: Dict):
        """Emit a memory-related event for monitoring/hooks."""
        try:
            # Integrate with the existing event system
            event_data = {
                'type': event_type,
                'memory_type': memory_type,
                'content_preview': content[:100] + ('...' if len(content) > 100 else ''),
                'metadata': metadata,
                'timestamp': datetime.now().isoformat(),
                'provider': getattr(self, 'provider', 'unknown')
            }
            
            # Try to emit to the EventBus if available
            try:
                from ..bus import get_default_bus
                bus = get_default_bus()
                bus.emit(f"memory.{event_type}.{memory_type}", event_data)
            except ImportError:
                # EventBus not available, fall back to logging
                logging.debug(f"Memory event: {event_type}.{memory_type} - {event_data}")
            except Exception as bus_error:
                # EventBus failed, log the event instead
                logging.debug(f"Memory event (bus failed): {event_type}.{memory_type} - {event_data}")
                logging.debug(f"EventBus error: {bus_error}")
        except Exception as e:
            logging.debug(f"Failed to emit memory event: {e}")
    
    @property
    def learn(self):
        """Get the learn manager instance (lazy-loaded)."""
        if self._learn_manager is None and self._learn_config:
            try:
                from .learn.manager import LearnManager
                self._learn_manager = LearnManager(config=self._learn_config)
            except ImportError:
                logging.warning("Learn manager not available - install learn dependencies")
        return self._learn_manager

    # Async variants to prevent event loop blocking
    async def store_short_term_async(self, content: str, metadata: Optional[Dict] = None, quality_score: Optional[float] = None, 
                                   user_id: Optional[str] = None, auto_promote: bool = True) -> str:
        """
        Async version of store_short_term to prevent event loop blocking.
        
        Args:
            content: The content to store
            metadata: Optional metadata dictionary
            quality_score: Optional pre-calculated quality score
            user_id: Optional user identifier
            auto_promote: Whether to automatically promote to LTM if quality is high
            
        Returns:
            The memory ID of the stored content
        """
        if not content.strip():
            return ""
        
        # Calculate quality score if not provided
        if quality_score is None:
            quality_score = self.compute_quality_score(content, metadata)
        
        # Prepare metadata (mirror sync version's metadata construction including sanitization
        # to ensure only JSON-serializable values are stored, preventing crashes across backends)
        raw_metadata = metadata.copy() if metadata else {}
        raw_metadata.update({
            "timestamp": datetime.now().isoformat(),
            "quality_score": quality_score,
            "memory_type": "short_term"
        })
        if user_id:
            raw_metadata["user_id"] = user_id
        clean_metadata = self._sanitize_metadata(raw_metadata)

        # Store in SQLite STM
        memory_id = ""
        try:
            memory_id = await asyncio.to_thread(self._store_sqlite_stm, content, clean_metadata, quality_score)
        except Exception as e:
            logging.error(f"Failed to store in SQLite STM: {e}")
            return ""
        
        # Auto-promote to long-term memory if quality is high (async)
        if auto_promote and quality_score >= 7.5:  # High quality threshold
            try:
                await self.store_long_term_async(content, clean_metadata, quality_score, user_id)
                self._log_verbose(f"Auto-promoted STM content to LTM (score: {quality_score:.2f})")
            except Exception as e:
                logging.warning(f"Failed to auto-promote to LTM: {e}")
        
        # Emit memory event
        self._emit_memory_event("store", "short_term", content, clean_metadata)
        
        self._log_verbose(f"Stored in STM: {content[:100]}... (quality: {quality_score:.2f})")
        
        return memory_id or ""

    async def store_long_term_async(self, content: str, metadata: Optional[Dict] = None, quality_score: Optional[float] = None,
                                  user_id: Optional[str] = None) -> str:
        """
        Async version of store_long_term to prevent event loop blocking.
        
        Args:
            content: The content to store
            metadata: Optional metadata dictionary
            quality_score: Optional pre-calculated quality score
            user_id: Optional user identifier
            
        Returns:
            The memory ID of the stored content
        """
        if not content.strip():
            return ""
        
        # Calculate quality score if not provided
        if quality_score is None:
            quality_score = self.compute_quality_score(content, metadata)
        
        # Use sync version in thread to avoid blocking event loop
        return await asyncio.to_thread(self.store_long_term, content, metadata, quality_score, user_id)