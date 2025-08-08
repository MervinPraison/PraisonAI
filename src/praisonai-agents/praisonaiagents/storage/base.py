"""
Base storage interface for PraisonAI Agents storage backends.

This module defines the abstract base class that all storage backends must implement.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
import logging

logger = logging.getLogger(__name__)


class BaseStorage(ABC):
    """
    Abstract base class for all storage backends.
    
    All storage implementations must inherit from this class and implement
    the required methods to provide a unified interface for memory storage.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the storage backend with configuration.
        
        Args:
            config: Configuration dictionary for the storage backend
        """
        self.config = config
        self.logger = logger
    
    @abstractmethod
    async def read(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Read a single record by key.
        
        Args:
            key: Unique identifier for the record
            
        Returns:
            Dictionary containing the record data, or None if not found
        """
        pass
    
    @abstractmethod
    async def write(self, key: str, data: Dict[str, Any]) -> bool:
        """
        Write a single record.
        
        Args:
            key: Unique identifier for the record
            data: Dictionary containing the record data
            
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        Delete a single record by key.
        
        Args:
            key: Unique identifier for the record
            
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def search(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Search for records matching the query.
        
        Args:
            query: Dictionary containing search parameters
            
        Returns:
            List of matching records
        """
        pass
    
    @abstractmethod
    async def list_keys(self, prefix: Optional[str] = None, limit: Optional[int] = None) -> List[str]:
        """
        List keys in the storage.
        
        Args:
            prefix: Optional prefix to filter keys
            limit: Optional limit on number of keys returned
            
        Returns:
            List of keys
        """
        pass
    
    @abstractmethod
    async def clear(self) -> bool:
        """
        Clear all records from storage.
        
        Returns:
            True if successful, False otherwise
        """
        pass
    
    async def batch_write(self, records: Dict[str, Dict[str, Any]]) -> Dict[str, bool]:
        """
        Write multiple records in a batch operation.
        
        Default implementation calls write() for each record.
        Backends can override for optimized batch operations.
        
        Args:
            records: Dictionary mapping keys to record data
            
        Returns:
            Dictionary mapping keys to success status
        """
        results = {}
        for key, data in records.items():
            try:
                results[key] = await self.write(key, data)
            except Exception as e:
                self.logger.error(f"Failed to write key {key}: {e}")
                results[key] = False
        return results
    
    async def batch_read(self, keys: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Read multiple records in a batch operation.
        
        Default implementation calls read() for each key.
        Backends can override for optimized batch operations.
        
        Args:
            keys: List of keys to read
            
        Returns:
            Dictionary mapping keys to record data (or None if not found)
        """
        results = {}
        for key in keys:
            try:
                results[key] = await self.read(key)
            except Exception as e:
                self.logger.error(f"Failed to read key {key}: {e}")
                results[key] = None
        return results
    
    async def batch_delete(self, keys: List[str]) -> Dict[str, bool]:
        """
        Delete multiple records in a batch operation.
        
        Default implementation calls delete() for each key.
        Backends can override for optimized batch operations.
        
        Args:
            keys: List of keys to delete
            
        Returns:
            Dictionary mapping keys to success status
        """
        results = {}
        for key in keys:
            try:
                results[key] = await self.delete(key)
            except Exception as e:
                self.logger.error(f"Failed to delete key {key}: {e}")
                results[key] = False
        return results
    
    async def exists(self, key: str) -> bool:
        """
        Check if a key exists in storage.
        
        Default implementation calls read() and checks for None.
        Backends can override for optimized existence checks.
        
        Args:
            key: Key to check
            
        Returns:
            True if key exists, False otherwise
        """
        try:
            result = await self.read(key)
            return result is not None
        except Exception as e:
            self.logger.error(f"Failed to check existence of key {key}: {e}")
            return False
    
    async def count(self) -> int:
        """
        Count total number of records in storage.
        
        Default implementation lists all keys and returns count.
        Backends can override for optimized counting.
        
        Returns:
            Number of records in storage
        """
        try:
            keys = await self.list_keys()
            return len(keys)
        except Exception as e:
            self.logger.error(f"Failed to count records: {e}")
            return 0
    
    def _log_verbose(self, msg: str, level: int = logging.INFO):
        """Log message if verbose logging is enabled."""
        self.logger.log(level, msg)