"""
SessionInfo dataclass for unified retrieve_session schema.

Provides a consistent interface for session information across
all managed agent backends (Anthropic, Local, etc.).
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class UsageInfo:
    """Token usage information for a session."""
    input_tokens: int = 0
    output_tokens: int = 0

    def to_dict(self) -> Dict[str, int]:
        """Convert to dict for backward compatibility."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "UsageInfo":
        """Create from dict, handling missing or None values."""
        if not data:
            return cls()
        return cls(
            input_tokens=data.get("input_tokens", 0),
            output_tokens=data.get("output_tokens", 0),
        )


@dataclass
class SessionInfo:
    """Unified session information schema.
    
    All managed agent backends (Anthropic, Local, etc.) should return
    this consistent schema from their retrieve_session() method.
    
    Fields:
        id: Session identifier (string)
        status: Session status ("idle", "running", "error", "unknown", etc.)
        title: Human-readable session title (empty string if not available)
        usage: Token usage information with input/output counts
    
    Example:
        info = SessionInfo(
            id="sess_123",
            status="idle", 
            title="Research Session",
            usage=UsageInfo(input_tokens=150, output_tokens=75)
        )
        
        # Convert to dict for backward compatibility
        data = info.to_dict()
    """
    id: str = ""
    status: str = "unknown"
    title: str = ""
    usage: UsageInfo = field(default_factory=UsageInfo)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for backward compatibility.
        
        Returns the same dict structure that was previously returned
        by retrieve_session() methods, ensuring no breaking changes.
        """
        return {
            "id": self.id,
            "status": self.status,
            "title": self.title,
            "usage": self.usage.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "SessionInfo":
        """Create SessionInfo from existing dict format.
        
        Handles missing fields gracefully with sensible defaults.
        Used for migrating existing retrieve_session() implementations.
        
        Args:
            data: Dict with session info, possibly incomplete
            
        Returns:
            SessionInfo with all fields populated
        """
        if not data:
            return cls()
            
        return cls(
            id=data.get("id", ""),
            status=data.get("status", "unknown"),
            title=data.get("title", ""),
            usage=UsageInfo.from_dict(data.get("usage")),
        )