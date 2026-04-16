"""
Unified session info schema for managed agents.

Provides consistent session information structure across different managed agent backends.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass
class SessionUsage:
    """Token usage information."""
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass 
class SessionInfo:
    """Unified session information across managed agent backends.
    
    Provides consistent schema for session metadata returned by 
    retrieve_session() methods in both AnthropicManagedAgent and LocalManagedAgent.
    
    All fields are always present with sensible defaults for backward compatibility.
    """
    id: str = ""
    status: str = "unknown"
    title: str = ""
    usage: SessionUsage = field(default_factory=SessionUsage)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for backward compatibility."""
        return {
            "id": self.id,
            "status": self.status, 
            "title": self.title,
            "usage": {
                "input_tokens": self.usage.input_tokens,
                "output_tokens": self.usage.output_tokens,
            }
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionInfo":
        """Create from dictionary with defaults for missing fields."""
        usage_data = data.get("usage", {})
        usage = SessionUsage(
            input_tokens=usage_data.get("input_tokens", 0),
            output_tokens=usage_data.get("output_tokens", 0)
        )
        
        return cls(
            id=data.get("id", ""),
            status=data.get("status", "unknown"),
            title=data.get("title", ""),
            usage=usage
        )