"""
Artifact Types and Protocols for Dynamic Context Discovery.

This module provides lightweight types and protocols for artifact-based
context management. Implementations live in the wrapper (praisonai).

Zero Performance Impact:
- Pure dataclasses and protocols
- No heavy imports
- No I/O at import time

Usage:
    from praisonaiagents.context.artifacts import ArtifactRef, ArtifactStoreProtocol
    
    # Create a reference to a stored artifact
    ref = ArtifactRef(
        path="/path/to/artifact.json",
        summary="API response with 50,000 records",
        size_bytes=1_200_000,
        mime_type="application/json",
    )
    
    # Implement the protocol in wrapper
    class FileSystemArtifactStore:
        def store(self, content, metadata): ...
        def load(self, ref): ...
"""

import time
import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Union, runtime_checkable


@dataclass
class ArtifactRef:
    """
    Reference to a stored artifact.
    
    Used to replace large tool outputs in context with a lightweight pointer.
    The agent can then use tail/grep/load operations to access content on demand.
    
    Attributes:
        path: Absolute path to the artifact file
        summary: Brief description or first ~200 chars of content
        size_bytes: Original content size in bytes
        mime_type: Content type (e.g., "application/json", "text/plain")
        checksum: SHA256 hash for integrity verification
        created_at: Unix timestamp when artifact was created
        artifact_id: Unique identifier for the artifact
        agent_id: ID of the agent that created this artifact
        run_id: ID of the run/session this artifact belongs to
        tool_name: Name of the tool that produced this output (if applicable)
        turn_id: Conversation turn number when artifact was created
    """
    path: str
    summary: str
    size_bytes: int
    mime_type: str = "application/octet-stream"
    checksum: str = ""
    created_at: float = field(default_factory=time.time)
    artifact_id: str = ""
    agent_id: str = ""
    run_id: str = ""
    tool_name: Optional[str] = None
    turn_id: int = 0
    
    def to_inline(self) -> str:
        """
        Generate inline representation for context.
        
        Returns a compact string that can be included in the conversation
        context, allowing the agent to reference the artifact.
        """
        size_str = self._format_size(self.size_bytes)
        tool_info = f" from {self.tool_name}" if self.tool_name else ""
        return f"[Artifact{tool_info}: {self.path} ({size_str}) - {self.summary}]"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "path": self.path,
            "summary": self.summary,
            "size_bytes": self.size_bytes,
            "mime_type": self.mime_type,
            "checksum": self.checksum,
            "created_at": self.created_at,
            "artifact_id": self.artifact_id,
            "agent_id": self.agent_id,
            "run_id": self.run_id,
            "tool_name": self.tool_name,
            "turn_id": self.turn_id,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArtifactRef":
        """Create from dictionary."""
        return cls(
            path=data.get("path", ""),
            summary=data.get("summary", ""),
            size_bytes=data.get("size_bytes", 0),
            mime_type=data.get("mime_type", "application/octet-stream"),
            checksum=data.get("checksum", ""),
            created_at=data.get("created_at", time.time()),
            artifact_id=data.get("artifact_id", ""),
            agent_id=data.get("agent_id", ""),
            run_id=data.get("run_id", ""),
            tool_name=data.get("tool_name"),
            turn_id=data.get("turn_id", 0),
        )
    
    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format size in human-readable form."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


@dataclass
class ArtifactMetadata:
    """
    Metadata for artifact creation and tracking.
    
    Passed to ArtifactStore.store() to provide context about the artifact.
    """
    agent_id: str = ""
    run_id: str = ""
    tool_name: Optional[str] = None
    turn_id: int = 0
    content_type: str = "auto"  # auto, json, text, binary
    tags: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "run_id": self.run_id,
            "tool_name": self.tool_name,
            "turn_id": self.turn_id,
            "content_type": self.content_type,
            "tags": self.tags,
            "extra": self.extra,
        }


@dataclass
class GrepMatch:
    """A single match from grep operation."""
    line_number: int
    line_content: str
    context_before: List[str] = field(default_factory=list)
    context_after: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "line_number": self.line_number,
            "line_content": self.line_content,
            "context_before": self.context_before,
            "context_after": self.context_after,
        }


@runtime_checkable
class ArtifactStoreProtocol(Protocol):
    """
    Protocol for artifact storage backends.
    
    Implementations should handle:
    - Storing content to persistent storage
    - Loading content back
    - Efficient tail/grep operations for large files
    - Checksum verification
    - Secret redaction (if enabled)
    
    Example implementation in wrapper:
        class FileSystemArtifactStore:
            def store(self, content, metadata):
                # Write to ~/.praison/runs/{run_id}/artifacts/
                ...
    """
    
    def store(
        self,
        content: Any,
        metadata: ArtifactMetadata,
    ) -> ArtifactRef:
        """
        Store content as an artifact.
        
        Args:
            content: The content to store (will be serialized)
            metadata: Metadata about the artifact
            
        Returns:
            ArtifactRef pointing to the stored artifact
        """
        ...
    
    def load(self, ref: ArtifactRef) -> Any:
        """
        Load full content from an artifact.
        
        Args:
            ref: Reference to the artifact
            
        Returns:
            The deserialized content
        """
        ...
    
    def tail(self, ref: ArtifactRef, lines: int = 50) -> str:
        """
        Get the last N lines of an artifact.
        
        Args:
            ref: Reference to the artifact
            lines: Number of lines to return
            
        Returns:
            String containing the last N lines
        """
        ...
    
    def head(self, ref: ArtifactRef, lines: int = 50) -> str:
        """
        Get the first N lines of an artifact.
        
        Args:
            ref: Reference to the artifact
            lines: Number of lines to return
            
        Returns:
            String containing the first N lines
        """
        ...
    
    def grep(
        self,
        ref: ArtifactRef,
        pattern: str,
        context_lines: int = 2,
        max_matches: int = 50,
    ) -> List[GrepMatch]:
        """
        Search for pattern in artifact content.
        
        Args:
            ref: Reference to the artifact
            pattern: Regex pattern to search for
            context_lines: Number of context lines before/after match
            max_matches: Maximum number of matches to return
            
        Returns:
            List of GrepMatch objects
        """
        ...
    
    def chunk(
        self,
        ref: ArtifactRef,
        start_line: int = 1,
        end_line: Optional[int] = None,
    ) -> str:
        """
        Get a chunk of lines from an artifact.
        
        Args:
            ref: Reference to the artifact
            start_line: Starting line number (1-indexed)
            end_line: Ending line number (inclusive), None for end of file
            
        Returns:
            String containing the requested lines
        """
        ...
    
    def delete(self, ref: ArtifactRef) -> bool:
        """
        Delete an artifact.
        
        Args:
            ref: Reference to the artifact
            
        Returns:
            True if deleted successfully
        """
        ...
    
    def list_artifacts(
        self,
        run_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        tool_name: Optional[str] = None,
    ) -> List[ArtifactRef]:
        """
        List artifacts matching filters.
        
        Args:
            run_id: Filter by run ID
            agent_id: Filter by agent ID
            tool_name: Filter by tool name
            
        Returns:
            List of matching ArtifactRef objects
        """
        ...


@runtime_checkable
class HistoryStoreProtocol(Protocol):
    """
    Protocol for conversation history storage.
    
    Enables loss recovery during summarization by persisting
    full conversation history to artifacts.
    """
    
    def append(
        self,
        message: Dict[str, Any],
        agent_id: str,
        run_id: str,
    ) -> None:
        """
        Append a message to history.
        
        Args:
            message: The message dict (role, content, etc.)
            agent_id: ID of the agent
            run_id: ID of the run/session
        """
        ...
    
    def get_ref(self, agent_id: str, run_id: str) -> Optional[ArtifactRef]:
        """
        Get artifact reference for history file.
        
        Args:
            agent_id: ID of the agent
            run_id: ID of the run/session
            
        Returns:
            ArtifactRef if history exists, None otherwise
        """
        ...
    
    def search(
        self,
        query: str,
        agent_id: str,
        run_id: str,
        max_results: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Search history for matching messages.
        
        Args:
            query: Search query (supports regex)
            agent_id: ID of the agent
            run_id: ID of the run/session
            max_results: Maximum results to return
            
        Returns:
            List of matching message dicts
        """
        ...
    
    def get_messages(
        self,
        agent_id: str,
        run_id: str,
        start_turn: int = 0,
        end_turn: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get messages from history.
        
        Args:
            agent_id: ID of the agent
            run_id: ID of the run/session
            start_turn: Starting turn number
            end_turn: Ending turn number (None for all)
            
        Returns:
            List of message dicts
        """
        ...


@runtime_checkable
class TerminalLoggerProtocol(Protocol):
    """
    Protocol for terminal session logging.
    
    Captures shell command outputs to artifacts for later retrieval.
    """
    
    def log_command(
        self,
        command: str,
        output: str,
        exit_code: int,
        agent_id: str,
        run_id: str,
    ) -> ArtifactRef:
        """
        Log a command execution.
        
        Args:
            command: The command that was executed
            output: Combined stdout/stderr output
            exit_code: Command exit code
            agent_id: ID of the agent
            run_id: ID of the run/session
            
        Returns:
            ArtifactRef to the logged output
        """
        ...
    
    def get_session_ref(self, agent_id: str, run_id: str) -> Optional[ArtifactRef]:
        """
        Get artifact reference for terminal session log.
        
        Args:
            agent_id: ID of the agent
            run_id: ID of the run/session
            
        Returns:
            ArtifactRef if session exists, None otherwise
        """
        ...
    
    def tail_session(
        self,
        agent_id: str,
        run_id: str,
        lines: int = 100,
    ) -> str:
        """
        Get last N lines from terminal session.
        
        Args:
            agent_id: ID of the agent
            run_id: ID of the run/session
            lines: Number of lines to return
            
        Returns:
            String containing the last N lines
        """
        ...
    
    def grep_session(
        self,
        pattern: str,
        agent_id: str,
        run_id: str,
        max_matches: int = 50,
    ) -> List[GrepMatch]:
        """
        Search terminal session for pattern.
        
        Args:
            pattern: Regex pattern to search for
            agent_id: ID of the agent
            run_id: ID of the run/session
            max_matches: Maximum matches to return
            
        Returns:
            List of GrepMatch objects
        """
        ...


@dataclass
class QueueConfig:
    """
    Configuration for tool output queuing.
    
    Controls when and how large tool outputs are queued to artifacts
    instead of being included inline in the context.
    """
    enabled: bool = True
    inline_max_bytes: int = 32 * 1024  # 32KB default
    redact_secrets: bool = True
    summary_max_chars: int = 200
    checksum_algorithm: str = "sha256"
    
    # Secret patterns to redact (regex)
    secret_patterns: List[str] = field(default_factory=lambda: [
        r'(?i)(api[_-]?key|apikey)["\']?\s*[:=]\s*["\']?[\w\-]+',
        r'(?i)(secret|password|passwd|pwd)["\']?\s*[:=]\s*["\']?[\w\-]+',
        r'(?i)(token|bearer)["\']?\s*[:=]\s*["\']?[\w\-]+',
        r'(?i)(auth|authorization)["\']?\s*[:=]\s*["\']?[\w\-]+',
        r'sk-[a-zA-Z0-9]{20,}',  # OpenAI keys
        r'ghp_[a-zA-Z0-9]{36}',  # GitHub tokens
        r'gho_[a-zA-Z0-9]{36}',  # GitHub OAuth
        r'xox[baprs]-[a-zA-Z0-9\-]+',  # Slack tokens
    ])
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "inline_max_bytes": self.inline_max_bytes,
            "redact_secrets": self.redact_secrets,
            "summary_max_chars": self.summary_max_chars,
            "checksum_algorithm": self.checksum_algorithm,
            "secret_patterns": self.secret_patterns,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QueueConfig":
        return cls(
            enabled=data.get("enabled", True),
            inline_max_bytes=data.get("inline_max_bytes", 32 * 1024),
            redact_secrets=data.get("redact_secrets", True),
            summary_max_chars=data.get("summary_max_chars", 200),
            checksum_algorithm=data.get("checksum_algorithm", "sha256"),
            secret_patterns=data.get("secret_patterns", cls().secret_patterns),
        )





def compute_checksum(content: Union[str, bytes], algorithm: str = "sha256") -> str:
    """
    Compute checksum of content.
    
    Args:
        content: String or bytes to hash
        algorithm: Hash algorithm (sha256, md5, etc.)
        
    Returns:
        Hex digest of the hash
    """
    if isinstance(content, str):
        content = content.encode("utf-8")
    
    hasher = hashlib.new(algorithm)
    hasher.update(content)
    return hasher.hexdigest()


def generate_summary(content: Any, max_chars: int = 200) -> str:
    """
    Generate a brief summary of content.
    
    Args:
        content: Content to summarize
        max_chars: Maximum characters in summary
        
    Returns:
        Brief summary string
    """
    if isinstance(content, (dict, list)):
        # For structured data, describe the structure
        if isinstance(content, dict):
            keys = list(content.keys())[:5]
            key_str = ", ".join(str(k) for k in keys)
            if len(content) > 5:
                key_str += f", ... ({len(content)} total keys)"
            return f"Dict with keys: {key_str}"[:max_chars]
        else:
            if len(content) > 0:
                first_type = type(content[0]).__name__
                return f"List of {len(content)} {first_type} items"[:max_chars]
            return "Empty list"
    
    # For strings, take first N chars
    text = str(content)
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 3] + "..."
