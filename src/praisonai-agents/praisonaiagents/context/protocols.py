"""
Context Protocols for PraisonAI Agents.

Protocol-driven abstractions for context management:
- ContextView: Read-only view of context for an agent
- ContextMutator: Mutation interface for context changes
- ContextStore: Global context store interface

These protocols enable:
- Scoped context views per agent
- Delta/commit/rollback model
- Non-destructive truncation (tagging vs deletion)
- Observation masking (lightweight alternative to summarization)

Zero Performance Impact:
- Protocols are typing-only at runtime (no overhead)
- Implementations are lazy-loaded
"""

from typing import (
    Protocol, List, Dict, Any, Optional,
    runtime_checkable, Tuple
)
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import time


class MessageRole(str, Enum):
    """Valid message roles."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class MessageMetadata:
    """
    Metadata for context messages.
    
    Supports non-destructive truncation/condensation via parent IDs.
    """
    # Core identifiers
    agent_id: str = ""
    turn_id: int = 0
    timestamp: float = field(default_factory=time.time)
    
    # Token tracking (cached)
    token_count: int = 0
    token_count_valid: bool = False
    
    # Non-destructive truncation (inspired by kilocode)
    condense_parent: Optional[str] = None  # ID of summary that replaced this
    truncation_parent: Optional[str] = None  # ID of truncation marker
    is_summary: bool = False
    summary_id: Optional[str] = None  # Unique ID if this is a summary
    is_truncation_marker: bool = False
    truncation_id: Optional[str] = None  # Unique ID if this is a truncation marker
    
    # Observation masking
    is_masked: bool = False
    masked_preview: str = ""  # Short preview when masked
    original_token_count: int = 0  # Original size before masking
    
    # Tool-specific
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    is_tool_output: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "turn_id": self.turn_id,
            "timestamp": self.timestamp,
            "token_count": self.token_count,
            "condense_parent": self.condense_parent,
            "truncation_parent": self.truncation_parent,
            "is_summary": self.is_summary,
            "is_masked": self.is_masked,
        }


@dataclass
class ContextMessage:
    """
    Enhanced message with metadata for context management.
    
    Wraps standard message dict with tracking metadata.
    """
    role: MessageRole
    content: Any  # str or List[Dict] for multimodal
    metadata: MessageMetadata = field(default_factory=MessageMetadata)
    
    # Original message dict (for compatibility)
    _raw: Dict[str, Any] = field(default_factory=dict, repr=False)
    
    @classmethod
    def from_dict(cls, msg: Dict[str, Any], agent_id: str = "", turn_id: int = 0) -> "ContextMessage":
        """Create from standard message dict."""
        role_str = msg.get("role", "user")
        try:
            role = MessageRole(role_str)
        except ValueError:
            role = MessageRole.USER
        
        metadata = MessageMetadata(
            agent_id=agent_id,
            turn_id=turn_id,
            tool_call_id=msg.get("tool_call_id"),
            tool_name=msg.get("name"),
            is_tool_output=role == MessageRole.TOOL,
        )
        
        # Restore metadata if present
        if "_metadata" in msg:
            meta_dict = msg["_metadata"]
            metadata.condense_parent = meta_dict.get("condense_parent")
            metadata.truncation_parent = meta_dict.get("truncation_parent")
            metadata.is_summary = meta_dict.get("is_summary", False)
            metadata.summary_id = meta_dict.get("summary_id")
            metadata.is_truncation_marker = meta_dict.get("is_truncation_marker", False)
            metadata.truncation_id = meta_dict.get("truncation_id")
            metadata.is_masked = meta_dict.get("is_masked", False)
            metadata.masked_preview = meta_dict.get("masked_preview", "")
            metadata.original_token_count = meta_dict.get("original_token_count", 0)
        
        return cls(
            role=role,
            content=msg.get("content", ""),
            metadata=metadata,
            _raw=msg,
        )
    
    def to_dict(self, include_metadata: bool = False) -> Dict[str, Any]:
        """Convert to standard message dict."""
        result = {
            "role": self.role.value,
            "content": self.content,
        }
        
        if self.metadata.tool_call_id:
            result["tool_call_id"] = self.metadata.tool_call_id
        if self.metadata.tool_name:
            result["name"] = self.metadata.tool_name
        
        if include_metadata:
            result["_metadata"] = self.metadata.to_dict()
        
        return result
    
    def content_hash(self) -> str:
        """Get hash of content for caching."""
        content_str = str(self.content) if not isinstance(self.content, str) else self.content
        return hashlib.md5(content_str.encode()).hexdigest()[:16]


@runtime_checkable
class ContextView(Protocol):
    """
    Read-only view of context for an agent.
    
    Provides filtered, budget-aware access to messages.
    """
    
    def get_messages(self, max_tokens: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get messages within optional token limit."""
        ...
    
    def get_effective_messages(self) -> List[Dict[str, Any]]:
        """Get messages filtered by condense/truncation parents."""
        ...
    
    def get_token_count(self) -> int:
        """Get total token count of visible messages."""
        ...
    
    def get_budget_remaining(self) -> int:
        """Get remaining token budget."""
        ...
    
    def get_utilization(self) -> float:
        """Get current utilization (0.0 to 1.0+)."""
        ...


@runtime_checkable
class ContextMutator(Protocol):
    """
    Mutation interface for context changes.
    
    Supports delta buffering with commit/rollback.
    """
    
    def append(self, message: Dict[str, Any]) -> None:
        """Append message to delta buffer."""
        ...
    
    def commit(self) -> None:
        """Commit delta buffer to store."""
        ...
    
    def rollback(self) -> None:
        """Discard delta buffer."""
        ...
    
    def tag_for_condensation(self, message_indices: List[int], summary_id: str) -> None:
        """Tag messages as condensed (non-destructive)."""
        ...
    
    def tag_for_truncation(self, message_indices: List[int], truncation_id: str) -> None:
        """Tag messages as truncated (non-destructive)."""
        ...
    
    def mask_observation(self, message_index: int, preview: str = "") -> None:
        """Mask a message's content with a preview."""
        ...


@runtime_checkable
class ContextStore(Protocol):
    """
    Global context store interface.
    
    Manages per-agent views and shared context.
    """
    
    def get_view(self, agent_id: str) -> ContextView:
        """Get read-only view for agent."""
        ...
    
    def get_mutator(self, agent_id: str) -> ContextMutator:
        """Get mutator for agent."""
        ...
    
    def get_shared_context(self) -> List[Dict[str, Any]]:
        """Get shared context across agents."""
        ...
    
    def snapshot(self) -> bytes:
        """Serialize store state."""
        ...
    
    def restore(self, data: bytes) -> None:
        """Restore store from serialized state."""
        ...


# Message schema validation
REQUIRED_MESSAGE_FIELDS = {"role", "content"}
VALID_ROLES = {"system", "user", "assistant", "tool"}
TOOL_MESSAGE_FIELDS = {"tool_call_id"}  # Required for tool messages


def validate_message_schema(
    message: Dict[str, Any],
    strict: bool = False,
) -> Tuple[bool, Optional[str]]:
    """
    Validate message against schema invariants.
    
    Args:
        message: Message dict to validate
        strict: If True, fail on any issue; if False, warn only
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check required fields
    missing = REQUIRED_MESSAGE_FIELDS - set(message.keys())
    if missing:
        return False, f"Missing required fields: {missing}"
    
    # Check role validity
    role = message.get("role")
    if role not in VALID_ROLES:
        return False, f"Invalid role: {role}. Must be one of {VALID_ROLES}"
    
    # Tool messages need tool_call_id
    if role == "tool":
        if "tool_call_id" not in message:
            if strict:
                return False, "Tool message missing tool_call_id"
            # Non-strict: allow but note
    
    # Content type check
    content = message.get("content")
    if content is not None and not isinstance(content, (str, list)):
        return False, f"Content must be str or list, got {type(content)}"
    
    return True, None


def get_effective_history(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filter messages to get effective API history.
    
    Excludes messages that have been condensed or truncated
    (their parent summary/marker still exists).
    
    Inspired by kilocode's getEffectiveApiHistory.
    
    Args:
        messages: Full message history with metadata
        
    Returns:
        Filtered messages for API call
    """
    # Collect existing summary and truncation IDs
    existing_summary_ids = set()
    existing_truncation_ids = set()
    
    for msg in messages:
        meta = msg.get("_metadata", {})
        if meta.get("is_summary") and meta.get("summary_id"):
            existing_summary_ids.add(meta["summary_id"])
        if meta.get("is_truncation_marker") and meta.get("truncation_id"):
            existing_truncation_ids.add(meta["truncation_id"])
    
    # Filter out messages whose parent exists
    result = []
    for msg in messages:
        meta = msg.get("_metadata", {})
        
        # Skip if condensed and summary exists
        condense_parent = meta.get("condense_parent")
        if condense_parent and condense_parent in existing_summary_ids:
            continue
        
        # Skip if truncated and marker exists
        truncation_parent = meta.get("truncation_parent")
        if truncation_parent and truncation_parent in existing_truncation_ids:
            continue
        
        result.append(msg)
    
    return result


def cleanup_orphaned_parents(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Clean up orphaned parent references after rewind/delete.
    
    When a summary or truncation marker is deleted, messages that
    were tagged with its ID should have their parent reference cleared.
    
    Inspired by kilocode's cleanupAfterTruncation.
    
    Args:
        messages: Messages after truncation
        
    Returns:
        Messages with orphaned parents cleared
    """
    # Collect existing IDs
    existing_summary_ids = set()
    existing_truncation_ids = set()
    
    for msg in messages:
        meta = msg.get("_metadata", {})
        if meta.get("is_summary") and meta.get("summary_id"):
            existing_summary_ids.add(meta["summary_id"])
        if meta.get("is_truncation_marker") and meta.get("truncation_id"):
            existing_truncation_ids.add(meta["truncation_id"])
    
    # Clear orphaned references
    result = []
    for msg in messages:
        meta = msg.get("_metadata", {})
        needs_update = False
        
        condense_parent = meta.get("condense_parent")
        if condense_parent and condense_parent not in existing_summary_ids:
            needs_update = True
        
        truncation_parent = meta.get("truncation_parent")
        if truncation_parent and truncation_parent not in existing_truncation_ids:
            needs_update = True
        
        if needs_update:
            # Create new message without orphaned parents
            new_msg = msg.copy()
            new_meta = meta.copy()
            
            if condense_parent and condense_parent not in existing_summary_ids:
                new_meta.pop("condense_parent", None)
            if truncation_parent and truncation_parent not in existing_truncation_ids:
                new_meta.pop("truncation_parent", None)
            
            new_msg["_metadata"] = new_meta
            result.append(new_msg)
        else:
            result.append(msg)
    
    return result
