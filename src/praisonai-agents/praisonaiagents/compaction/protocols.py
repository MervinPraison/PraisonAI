"""
Compaction Protocols for PraisonAI Agents.

Protocol-driven interfaces for context compaction functionality.
"""

from typing import Protocol, List, Dict, Any, Tuple, Optional


class ToolResultPrunerProtocol(Protocol):
    """Protocol for pruning and deduplicating tool results."""
    
    def prune(
        self,
        messages: List[Dict[str, Any]],
        max_tool_result_size: int = 500
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Prune and deduplicate tool results to reduce token usage.
        
        Args:
            messages: List of messages to process
            max_tool_result_size: Maximum size for tool results before truncation
            
        Returns:
            Tuple of (processed messages, number of tool results pruned)
        """
        ...


class MessageFormatterProtocol(Protocol):
    """Protocol for formatting messages for summarization."""
    
    def format_for_summary(self, messages: List[Dict[str, Any]]) -> str:
        """
        Format messages for LLM summarization.
        
        Args:
            messages: Messages to format
            
        Returns:
            Formatted string suitable for summarization
        """
        ...


class SummaryBuilderProtocol(Protocol):
    """Protocol for building structured summaries."""
    
    def build_structured_summary(self, messages: List[Dict[str, Any]]) -> str:
        """
        Build a structured summary from messages.
        
        Args:
            messages: Messages to summarize
            
        Returns:
            Structured summary string
        """
        ...
    
    def merge_summaries(self, previous: str, current: str) -> str:
        """
        Merge previous summary with current one for iterative updates.
        
        Args:
            previous: Previous summary content
            current: Current summary content
            
        Returns:
            Merged summary
        """
        ...