"""
Memory tools for PraisonAI Agents

This module provides tools that agents can use to manage their memory,
including storing, retrieving, updating, and deleting memories.
"""

from typing import Any, Dict, List, Optional


class MemoryTools:
    """Tools for agents to manage their memory"""
    
    def __init__(self, memory: Optional[Any] = None):
        """Initialize memory tools with a memory instance"""
        self.memory = memory
    
    def remember(self, fact: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Store important information in memory
        
        Args:
            fact: The information to remember
            metadata: Optional metadata to associate with the fact
            
        Returns:
            bool: True if successfully stored, False otherwise
        """
        if not self.memory:
            return False
        return self.memory.remember(fact, metadata)
    
    def update_memory(self, memory_id: str, new_fact: str) -> bool:
        """
        Update existing memory by ID
        
        Args:
            memory_id: The ID of the memory to update
            new_fact: The new information to replace the old fact
            
        Returns:
            bool: True if successfully updated, False otherwise
        """
        if not self.memory:
            return False
        return self.memory.update_memory(memory_id, new_fact)
    
    def forget(self, memory_id: str) -> bool:
        """
        Remove a memory by ID
        
        Args:
            memory_id: The ID of the memory to remove
            
        Returns:
            bool: True if successfully removed, False otherwise
        """
        if not self.memory:
            return False
        return self.memory.forget(memory_id)
    
    def search_memories(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search for memories related to a query
        
        Args:
            query: The search query
            limit: Maximum number of results to return
            
        Returns:
            List of memory results
        """
        if not self.memory:
            return []
        return self.memory.search_memories(query, limit)
    
    def get_session_summary(self) -> Optional[Dict[str, Any]]:
        """
        Get the current session summary
        
        Returns:
            Dictionary containing session summary with keys: text, topics, key_points
        """
        if not self.memory:
            return None
        return self.memory.get_session_summary()
    
    def search_with_references(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """
        Search for memories with references included
        
        Args:
            query: The search query
            limit: Maximum number of results to return
            
        Returns:
            Dictionary with content and references
        """
        if not self.memory:
            return {"content": "", "references": []}
        return self.memory.search_with_references(query, limit)


def get_memory_tools(memory: Optional[Any] = None) -> List[Any]:
    """
    Get a list of memory tools for use by agents
    
    Args:
        memory: The memory instance to use
        
    Returns:
        List of memory tool functions
    """
    tools_instance = MemoryTools(memory)
    return [
        tools_instance.remember,
        tools_instance.update_memory,
        tools_instance.forget,
        tools_instance.search_memories,
        tools_instance.get_session_summary,
        tools_instance.search_with_references
    ]