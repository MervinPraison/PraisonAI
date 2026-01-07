"""
Message Parts for PraisonAI Agents.

Provides structured message parts for better streaming and display,
similar to OpenCode's message-v2 parts system.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
from enum import Enum
import time
import uuid


class PartType(str, Enum):
    """Types of message parts."""
    
    TEXT = "text"
    TOOL = "tool"
    REASONING = "reasoning"
    FILE = "file"
    IMAGE = "image"
    COMPACTION = "compaction"
    ERROR = "error"


class ToolStatus(str, Enum):
    """Status of a tool execution."""
    
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class BasePart:
    """Base class for all message parts."""
    
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: PartType = PartType.TEXT
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert part to dictionary."""
        return {
            "id": self.id,
            "type": self.type.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    def update(self):
        """Update the updated_at timestamp."""
        self.updated_at = time.time()


@dataclass
class TextPart(BasePart):
    """A text content part."""
    
    type: PartType = field(default=PartType.TEXT)
    text: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["text"] = self.text
        return d
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TextPart":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            text=data.get("text", ""),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )


@dataclass
class ToolPart(BasePart):
    """A tool execution part."""
    
    type: PartType = field(default=PartType.TOOL)
    tool_name: str = ""
    tool_call_id: str = ""
    status: ToolStatus = ToolStatus.PENDING
    input: Dict[str, Any] = field(default_factory=dict)
    output: Optional[str] = None
    error: Optional[str] = None
    title: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "tool_name": self.tool_name,
            "tool_call_id": self.tool_call_id,
            "status": self.status.value,
            "input": self.input,
            "output": self.output,
            "error": self.error,
            "title": self.title,
            "metadata": self.metadata,
        })
        return d
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolPart":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            tool_name=data.get("tool_name", ""),
            tool_call_id=data.get("tool_call_id", ""),
            status=ToolStatus(data.get("status", "pending")),
            input=data.get("input", {}),
            output=data.get("output"),
            error=data.get("error"),
            title=data.get("title"),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )
    
    def start(self):
        """Mark tool as running."""
        self.status = ToolStatus.RUNNING
        self.update()
    
    def complete(self, output: str, title: Optional[str] = None, metadata: Optional[Dict] = None):
        """Mark tool as completed."""
        self.status = ToolStatus.COMPLETED
        self.output = output
        if title:
            self.title = title
        if metadata:
            self.metadata.update(metadata)
        self.update()
    
    def fail(self, error: str):
        """Mark tool as failed."""
        self.status = ToolStatus.ERROR
        self.error = error
        self.update()


@dataclass
class ReasoningPart(BasePart):
    """A reasoning/thinking content part."""
    
    type: PartType = field(default=PartType.REASONING)
    text: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["text"] = self.text
        return d
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReasoningPart":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            text=data.get("text", ""),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )


@dataclass
class FilePart(BasePart):
    """A file attachment part."""
    
    type: PartType = field(default=PartType.FILE)
    path: str = ""
    name: str = ""
    mime_type: Optional[str] = None
    size: Optional[int] = None
    content: Optional[str] = None  # Base64 encoded for binary
    
    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "path": self.path,
            "name": self.name,
            "mime_type": self.mime_type,
            "size": self.size,
            "content": self.content,
        })
        return d
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FilePart":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            path=data.get("path", ""),
            name=data.get("name", ""),
            mime_type=data.get("mime_type"),
            size=data.get("size"),
            content=data.get("content"),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )


@dataclass
class ImagePart(BasePart):
    """An image attachment part."""
    
    type: PartType = field(default=PartType.IMAGE)
    url: Optional[str] = None
    path: Optional[str] = None
    base64: Optional[str] = None
    mime_type: str = "image/png"
    alt_text: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "url": self.url,
            "path": self.path,
            "base64": self.base64,
            "mime_type": self.mime_type,
            "alt_text": self.alt_text,
        })
        return d
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ImagePart":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            url=data.get("url"),
            path=data.get("path"),
            base64=data.get("base64"),
            mime_type=data.get("mime_type", "image/png"),
            alt_text=data.get("alt_text"),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )


@dataclass
class CompactionPart(BasePart):
    """A compaction summary part."""
    
    type: PartType = field(default=PartType.COMPACTION)
    summary: str = ""
    original_tokens: int = 0
    compacted_tokens: int = 0
    messages_removed: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "summary": self.summary,
            "original_tokens": self.original_tokens,
            "compacted_tokens": self.compacted_tokens,
            "messages_removed": self.messages_removed,
        })
        return d
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompactionPart":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            summary=data.get("summary", ""),
            original_tokens=data.get("original_tokens", 0),
            compacted_tokens=data.get("compacted_tokens", 0),
            messages_removed=data.get("messages_removed", 0),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )


@dataclass
class ErrorPart(BasePart):
    """An error part."""
    
    type: PartType = field(default=PartType.ERROR)
    error_type: str = ""
    message: str = ""
    stack_trace: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d.update({
            "error_type": self.error_type,
            "message": self.message,
            "stack_trace": self.stack_trace,
        })
        return d
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ErrorPart":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            error_type=data.get("error_type", ""),
            message=data.get("message", ""),
            stack_trace=data.get("stack_trace"),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )


# Type alias for any part
MessagePart = Union[TextPart, ToolPart, ReasoningPart, FilePart, ImagePart, CompactionPart, ErrorPart]


def part_from_dict(data: Dict[str, Any]) -> MessagePart:
    """Create a part from a dictionary based on its type."""
    part_type = data.get("type", "text")
    
    if part_type == PartType.TEXT.value:
        return TextPart.from_dict(data)
    elif part_type == PartType.TOOL.value:
        return ToolPart.from_dict(data)
    elif part_type == PartType.REASONING.value:
        return ReasoningPart.from_dict(data)
    elif part_type == PartType.FILE.value:
        return FilePart.from_dict(data)
    elif part_type == PartType.IMAGE.value:
        return ImagePart.from_dict(data)
    elif part_type == PartType.COMPACTION.value:
        return CompactionPart.from_dict(data)
    elif part_type == PartType.ERROR.value:
        return ErrorPart.from_dict(data)
    else:
        # Default to text part
        return TextPart.from_dict(data)


@dataclass
class StructuredMessage:
    """
    A message with structured parts.
    
    This extends the basic message format with support for
    multiple parts of different types.
    """
    
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    role: str = "assistant"  # user, assistant, system
    parts: List[MessagePart] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    session_id: Optional[str] = None
    agent_name: Optional[str] = None
    model_id: Optional[str] = None
    provider_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_part(self, part: MessagePart) -> MessagePart:
        """Add a part to the message."""
        self.parts.append(part)
        self.updated_at = time.time()
        return part
    
    def add_text(self, text: str) -> TextPart:
        """Add a text part."""
        part = TextPart(text=text)
        return self.add_part(part)
    
    def add_tool(
        self,
        tool_name: str,
        tool_call_id: str,
        input: Optional[Dict] = None,
    ) -> ToolPart:
        """Add a tool part."""
        part = ToolPart(
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            input=input or {},
        )
        return self.add_part(part)
    
    def add_reasoning(self, text: str) -> ReasoningPart:
        """Add a reasoning part."""
        part = ReasoningPart(text=text)
        return self.add_part(part)
    
    def add_file(self, path: str, name: str, **kwargs) -> FilePart:
        """Add a file part."""
        part = FilePart(path=path, name=name, **kwargs)
        return self.add_part(part)
    
    def add_image(self, **kwargs) -> ImagePart:
        """Add an image part."""
        part = ImagePart(**kwargs)
        return self.add_part(part)
    
    def add_error(self, error_type: str, message: str, stack_trace: Optional[str] = None) -> ErrorPart:
        """Add an error part."""
        part = ErrorPart(error_type=error_type, message=message, stack_trace=stack_trace)
        return self.add_part(part)
    
    def get_part(self, part_id: str) -> Optional[MessagePart]:
        """Get a part by ID."""
        for part in self.parts:
            if part.id == part_id:
                return part
        return None
    
    def get_parts_by_type(self, part_type: PartType) -> List[MessagePart]:
        """Get all parts of a specific type."""
        return [p for p in self.parts if p.type == part_type]
    
    def get_text_content(self) -> str:
        """Get combined text content from all text parts."""
        text_parts = self.get_parts_by_type(PartType.TEXT)
        return "\n".join(p.text for p in text_parts if hasattr(p, 'text'))
    
    def get_tool_parts(self) -> List[ToolPart]:
        """Get all tool parts."""
        return [p for p in self.parts if isinstance(p, ToolPart)]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary."""
        return {
            "id": self.id,
            "role": self.role,
            "parts": [p.to_dict() for p in self.parts],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "model_id": self.model_id,
            "provider_id": self.provider_id,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StructuredMessage":
        """Create message from dictionary."""
        parts = [part_from_dict(p) for p in data.get("parts", [])]
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            role=data.get("role", "assistant"),
            parts=parts,
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            session_id=data.get("session_id"),
            agent_name=data.get("agent_name"),
            model_id=data.get("model_id"),
            provider_id=data.get("provider_id"),
            metadata=data.get("metadata", {}),
        )
    
    def to_llm_message(self) -> Dict[str, Any]:
        """Convert to LLM-compatible message format."""
        content = self.get_text_content()
        return {
            "role": self.role,
            "content": content,
        }
    
    def __repr__(self) -> str:
        return f"StructuredMessage(id={self.id[:8]}..., role={self.role}, parts={len(self.parts)})"
