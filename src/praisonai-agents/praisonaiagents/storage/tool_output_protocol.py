"""
Tool Output Storage Protocol for PraisonAI Agents.

Defines the protocol interface for tool output storage implementations.
This allows for different storage backends (file, cloud, database, etc.)
while maintaining a consistent interface.
"""

from typing import Protocol, Optional, Dict, Any, runtime_checkable


@runtime_checkable
class ToolOutputStoreProtocol(Protocol):
    """
    Protocol for tool output storage implementations.
    
    Implementations must provide methods to store and retrieve
    large tool outputs while maintaining run-scoped isolation.
    
    Example implementations:
    - FileToolOutputStore: Local filesystem storage (default)
    - S3ToolOutputStore: Amazon S3 cloud storage
    - AzureToolOutputStore: Azure Blob Storage
    - MongoToolOutputStore: MongoDB GridFS storage
    """
    
    run_id: str
    retention_hours: int
    
    def store(self, tool_name: str, output: str, call_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Store full tool output and return reference info.
        
        Args:
            tool_name: Name of the tool that produced the output
            output: Full output text to store
            call_id: Optional unique identifier for this call
            
        Returns:
            Dictionary with storage metadata including at least:
                - path: Reference path/URI to stored output
                - size: Total size in bytes
                - tool: Tool name
                - call_id: Unique call identifier
        """
        ...
    
    def retrieve(self, path_or_metadata: Any) -> Optional[str]:
        """
        Retrieve stored tool output.
        
        Args:
            path_or_metadata: Either a reference path/URI string or metadata dict with 'path'
            
        Returns:
            Full output text or None if not found
        """
        ...
    
    def format_reference(self, metadata: Dict[str, Any], truncated_preview: str) -> str:
        """
        Format a reference to stored output within the truncated preview.
        
        Args:
            metadata: Storage metadata from store()
            truncated_preview: The head/tail truncated text
            
        Returns:
            Formatted text with reference to full output
        """
        ...