"""
Session Info dataclass for unified managed agent session schema.

Provides consistent return structure for retrieve_session() across all
managed agent backends (Anthropic, Local, etc.).
"""

from typing import Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class SessionInfo:
    """Unified session info schema for managed agents.
    
    All fields are always present with sensible defaults to ensure
    consistent API across different backend implementations.
    """
    
    id: str = ""
    """Session ID (empty string if no session)"""
    
    status: str = "unknown"
    """Session status (idle, running, error, unknown, etc.)"""
    
    title: str = ""
    """Session title/name (empty if not set)"""
    
    usage: Dict[str, int] = None
    """Token usage tracking with input_tokens and output_tokens"""
    
    def __post_init__(self):
        """Ensure usage field has proper defaults."""
        if self.id is None:
            self.id = ""
        if self.status is None:
            self.status = "unknown"
        if self.title is None:
            self.title = ""

        if self.usage is None:
            self.usage = {"input_tokens": 0, "output_tokens": 0}
        else:
            if "input_tokens" not in self.usage:
                self.usage["input_tokens"] = 0
            if "output_tokens" not in self.usage:
                self.usage["output_tokens"] = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for backward compatibility.
        
        Returns the same structure that retrieve_session() used to return,
        ensuring existing code continues to work.
        """
        return asdict(self)
