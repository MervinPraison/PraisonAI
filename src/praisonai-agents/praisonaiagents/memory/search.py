"""
Search and retrieval functionality for Memory class.

This module contains methods related to memory search, retrieval, and querying.
Split from the main memory.py file for better maintainability.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime


class SearchMixin:
    """Mixin class containing search and retrieval methods for the Memory class."""
    
    def search_short_term(self, query: str, limit: int = 5, metadata_filter: Optional[Dict] = None, 
                         min_quality: Optional[float] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search short-term memory for relevant content.
        
        Args:
            query: Search query string
            limit: Maximum number of results to return
            metadata_filter: Optional metadata filter
            min_quality: Minimum quality score threshold
            user_id: Optional user ID for filtering
            
        Returns:
            List of relevant memory entries
        """
        results = []
        
        # Search in vector store (ChromaDB/MongoDB) if available
        if self.use_rag and hasattr(self, 'stm_collection'):
            try:
                results.extend(self._search_vector_stm(query, limit))
            except Exception as e:
                logging.warning(f"Vector STM search failed: {e}")
        
        if self.use_mongodb and hasattr(self, 'stm_collection'):
            try:
                results.extend(self._search_mongodb_stm(query, limit, metadata_filter, min_quality, user_id))
            except Exception as e:
                logging.warning(f"MongoDB STM search failed: {e}")
        
        # Search in SQLite as fallback
        try:
            sqlite_results = self._search_sqlite_stm(query, limit, metadata_filter, min_quality, user_id)
            results.extend(sqlite_results)
        except Exception as e:
            logging.warning(f"SQLite STM search failed: {e}")
        
        return self._deduplicate_and_rank_results(results, limit)
    
    def search_long_term(self, query: str, limit: int = 10, metadata_filter: Optional[Dict] = None,
                        min_quality: Optional[float] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Search long-term memory for relevant content.
        
        Args:
            query: Search query string
            limit: Maximum number of results to return
            metadata_filter: Optional metadata filter
            min_quality: Minimum quality score threshold
            user_id: Optional user ID for filtering
            
        Returns:
            List of relevant memory entries
        """
        results = []
        
        # Search in vector store (ChromaDB/MongoDB) if available
        if self.use_rag and hasattr(self, 'ltm_collection'):
            try:
                results.extend(self._search_vector_ltm(query, limit))
            except Exception as e:
                logging.warning(f"Vector LTM search failed: {e}")
        
        if self.use_mongodb and hasattr(self, 'ltm_collection'):
            try:
                results.extend(self._search_mongodb_ltm(query, limit, metadata_filter, min_quality, user_id))
            except Exception as e:
                logging.warning(f"MongoDB LTM search failed: {e}")
        
        # Search in SQLite as fallback
        try:
            sqlite_results = self._search_sqlite_ltm(query, limit, metadata_filter, min_quality, user_id)
            results.extend(sqlite_results)
        except Exception as e:
            logging.warning(f"SQLite LTM search failed: {e}")
        
        return self._deduplicate_and_rank_results(results, limit)
    
    def _search_vector_stm(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Search short-term memory using vector similarity."""
        if not hasattr(self, 'stm_collection'):
            return []
            
        # Get query embedding
        query_embedding = self._get_embedding(query)
        if not query_embedding:
            return []
        
        # Search similar vectors
        results = self.stm_collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            include=['metadatas', 'documents', 'distances']
        )
        
        return self._format_vector_results(results)
    
    def _search_vector_ltm(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Search long-term memory using vector similarity."""
        if not hasattr(self, 'ltm_collection'):
            return []
            
        # Get query embedding
        query_embedding = self._get_embedding(query)
        if not query_embedding:
            return []
        
        # Search similar vectors
        results = self.ltm_collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            include=['metadatas', 'documents', 'distances']
        )
        
        return self._format_vector_results(results)
    
    def _search_mongodb_stm(self, query: str, limit: int, metadata_filter: Optional[Dict],
                           min_quality: Optional[float], user_id: Optional[str]) -> List[Dict[str, Any]]:
        """Search short-term memory in MongoDB."""
        if not hasattr(self, 'stm_collection'):
            return []
        
        # Build search filter
        search_filter = {"$text": {"$search": query}}
        
        # Add additional filters
        if metadata_filter:
            for key, value in metadata_filter.items():
                search_filter[f"metadata.{key}"] = value
        
        if min_quality is not None:
            search_filter["quality_score"] = {"$gte": min_quality}
        
        if user_id:
            search_filter["metadata.user_id"] = user_id
        
        # Perform search with text score
        cursor = self.stm_collection.find(
            search_filter,
            {"score": {"$meta": "textScore"}}
        ).sort([("score", {"$meta": "textScore"})]).limit(limit)
        
        return [self._format_mongodb_result(doc) for doc in cursor]
    
    def _search_mongodb_ltm(self, query: str, limit: int, metadata_filter: Optional[Dict],
                           min_quality: Optional[float], user_id: Optional[str]) -> List[Dict[str, Any]]:
        """Search long-term memory in MongoDB."""
        if not hasattr(self, 'ltm_collection'):
            return []
        
        # Build search filter
        search_filter = {"$text": {"$search": query}}
        
        # Add additional filters
        if metadata_filter:
            for key, value in metadata_filter.items():
                search_filter[f"metadata.{key}"] = value
        
        if min_quality is not None:
            search_filter["quality_score"] = {"$gte": min_quality}
        
        if user_id:
            search_filter["metadata.user_id"] = user_id
        
        # Perform search with text score
        cursor = self.ltm_collection.find(
            search_filter,
            {"score": {"$meta": "textScore"}}
        ).sort([("score", {"$meta": "textScore"})]).limit(limit)
        
        return [self._format_mongodb_result(doc) for doc in cursor]
    
    def _search_sqlite_stm(self, query: str, limit: int, metadata_filter: Optional[Dict],
                          min_quality: Optional[float], user_id: Optional[str]) -> List[Dict[str, Any]]:
        """Search short-term memory in SQLite."""
        conn = self._get_stm_conn()
        
        # Build WHERE clause
        where_clauses = ["content LIKE ?"]
        params = [f"%{query}%"]
        
        if min_quality is not None:
            where_clauses.append("quality_score >= ?")
            params.append(min_quality)
        
        # Simple metadata filtering (JSON contains check)
        if metadata_filter:
            for key, value in metadata_filter.items():
                where_clauses.append("metadata LIKE ?")
                params.append(f'%"{key}": "{value}"%')
        
        if user_id:
            where_clauses.append("metadata LIKE ?")
            params.append(f'%"user_id": "{user_id}"%')
        
        where_clause = " AND ".join(where_clauses)
        
        query_sql = f"""
            SELECT id, content, metadata, timestamp, quality_score
            FROM short_term
            WHERE {where_clause}
            ORDER BY quality_score DESC, timestamp DESC
            LIMIT ?
        """
        
        params.append(limit)
        
        cursor = conn.execute(query_sql, params)
        rows = cursor.fetchall()
        
        return [self._format_sqlite_result(dict(row)) for row in rows]
    
    def _search_sqlite_ltm(self, query: str, limit: int, metadata_filter: Optional[Dict],
                          min_quality: Optional[float], user_id: Optional[str]) -> List[Dict[str, Any]]:
        """Search long-term memory in SQLite."""
        conn = self._get_ltm_conn()
        
        # Build WHERE clause
        where_clauses = ["content LIKE ?"]
        params = [f"%{query}%"]
        
        if min_quality is not None:
            where_clauses.append("quality_score >= ?")
            params.append(min_quality)
        
        # Simple metadata filtering (JSON contains check)
        if metadata_filter:
            for key, value in metadata_filter.items():
                where_clauses.append("metadata LIKE ?")
                params.append(f'%"{key}": "{value}"%')
        
        if user_id:
            where_clauses.append("metadata LIKE ?")
            params.append(f'%"user_id": "{user_id}"%')
        
        where_clause = " AND ".join(where_clauses)
        
        query_sql = f"""
            SELECT id, content, metadata, timestamp, quality_score
            FROM long_term
            WHERE {where_clause}
            ORDER BY quality_score DESC, timestamp DESC
            LIMIT ?
        """
        
        params.append(limit)
        
        cursor = conn.execute(query_sql, params)
        rows = cursor.fetchall()
        
        return [self._format_sqlite_result(dict(row)) for row in rows]
    
    def _format_vector_results(self, results: Dict) -> List[Dict[str, Any]]:
        """Format ChromaDB vector search results."""
        formatted = []
        
        if not results.get('documents') or not results['documents'][0]:
            return formatted
        
        documents = results['documents'][0]
        metadatas = results.get('metadatas', [[]])[0]
        distances = results.get('distances', [[]])[0]
        
        for i, doc in enumerate(documents):
            metadata = metadatas[i] if i < len(metadatas) else {}
            distance = distances[i] if i < len(distances) else 1.0
            
            formatted.append({
                'content': doc,
                'metadata': metadata,
                'similarity_score': 1.0 - distance,  # Convert distance to similarity
                'source': 'vector'
            })
        
        return formatted
    
    def _format_mongodb_result(self, doc: Dict) -> Dict[str, Any]:
        """Format MongoDB search result."""
        return {
            'id': str(doc.get('_id', '')),
            'content': doc.get('content', ''),
            'metadata': doc.get('metadata', {}),
            'timestamp': doc.get('timestamp', ''),
            'quality_score': doc.get('quality_score', 0.0),
            'text_score': doc.get('score', 0.0),
            'source': 'mongodb'
        }
    
    def _format_sqlite_result(self, row: Dict) -> Dict[str, Any]:
        """Format SQLite search result."""
        metadata = {}
        if row.get('metadata'):
            try:
                metadata = json.loads(row['metadata'])
            except json.JSONDecodeError:
                pass
        
        return {
            'id': str(row.get('id', '')),
            'content': row.get('content', ''),
            'metadata': metadata,
            'timestamp': row.get('timestamp', ''),
            'quality_score': row.get('quality_score', 0.0),
            'source': 'sqlite'
        }
    
    def _deduplicate_and_rank_results(self, results: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        """Remove duplicates and rank results by relevance."""
        # Simple deduplication by content
        seen_content = set()
        unique_results = []
        
        for result in results:
            content = result.get('content', '').strip().lower()
            if content and content not in seen_content:
                seen_content.add(content)
                unique_results.append(result)
        
        # Sort by quality score or similarity score
        unique_results.sort(
            key=lambda x: (
                x.get('similarity_score', 0.0) + 
                x.get('quality_score', 0.0) + 
                x.get('text_score', 0.0)
            ), 
            reverse=True
        )
        
        return unique_results[:limit]