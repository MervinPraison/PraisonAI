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


class MemoryCoreMixin:
    """Mixin class containing core memory functionality for the Memory class."""
    
    def store_short_term(self, content: str, metadata: Optional[Dict] = None, quality_score: Optional[float] = None, 
                        user_id: Optional[str] = None, auto_promote: bool = True) -> str:
        """
        Store content in short-term memory.
        
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
        
        # Prepare metadata
        if metadata is None:
            metadata = {}
        
        if user_id:
            metadata['user_id'] = user_id
        
        metadata['timestamp'] = datetime.now().isoformat()
        
        # Sanitize metadata for storage
        clean_metadata = self._sanitize_metadata(metadata)
        
        memory_id = None
        
        # Store in vector store if available
        if self.use_rag and hasattr(self, 'stm_collection'):
            try:
                memory_id = self._store_vector_stm(content, clean_metadata, quality_score)
            except Exception as e:
                logging.warning(f"Failed to store in vector STM: {e}")
        
        if self.use_mongodb and hasattr(self, 'stm_collection'):
            try:
                memory_id = self._store_mongodb_stm(content, clean_metadata, quality_score)
            except Exception as e:
                logging.warning(f"Failed to store in MongoDB STM: {e}")
        
        # Always store in SQLite as fallback
        try:
            if not memory_id:
                memory_id = self._store_sqlite_stm(content, clean_metadata, quality_score)
        except Exception as e:
            logging.error(f"Failed to store in SQLite STM: {e}")
            return ""
        
        # Auto-promote to long-term memory if quality is high
        if auto_promote and quality_score >= 7.5:  # High quality threshold
            try:
                self.store_long_term(content, clean_metadata, quality_score, user_id)
                self._log_verbose(f"Auto-promoted STM content to LTM (score: {quality_score:.2f})")
            except Exception as e:
                logging.warning(f"Failed to auto-promote to LTM: {e}")
        
        # Emit memory event
        self._emit_memory_event("store", "short_term", content, clean_metadata)
        
        self._log_verbose(f"Stored in STM: {content[:100]}... (quality: {quality_score:.2f})")
        
        return memory_id or ""
    
    def store_long_term(self, content: str, metadata: Optional[Dict] = None, quality_score: Optional[float] = None,
                       user_id: Optional[str] = None) -> str:
        """
        Store content in long-term memory.
        
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
        
        # Sanitize metadata for storage
        clean_metadata = self._sanitize_metadata(metadata)
        
        memory_id = None
        
        # Store in vector store if available
        if self.use_rag and hasattr(self, 'ltm_collection'):
            try:
                memory_id = self._store_vector_ltm(content, clean_metadata, quality_score)
            except Exception as e:
                logging.warning(f"Failed to store in vector LTM: {e}")
        
        if self.use_mongodb and hasattr(self, 'ltm_collection'):
            try:
                memory_id = self._store_mongodb_ltm(content, clean_metadata, quality_score)
            except Exception as e:
                logging.warning(f"Failed to store in MongoDB LTM: {e}")
        
        # Always store in SQLite as fallback
        try:
            if not memory_id:
                memory_id = self._store_sqlite_ltm(content, clean_metadata, quality_score)
        except Exception as e:
            logging.error(f"Failed to store in SQLite LTM: {e}")
            return ""
        
        # Emit memory event
        self._emit_memory_event("store", "long_term", content, clean_metadata)
        
        self._log_verbose(f"Stored in LTM: {content[:100]}... (quality: {quality_score:.2f})")
        
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
            # This would integrate with the event system
            event_data = {
                'type': event_type,
                'memory_type': memory_type,
                'content_preview': content[:100] + ('...' if len(content) > 100 else ''),
                'metadata': metadata,
                'timestamp': datetime.now().isoformat()
            }
            # Event emission logic would go here
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