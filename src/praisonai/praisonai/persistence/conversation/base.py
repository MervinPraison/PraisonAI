"""
Base interfaces for ConversationStore.

ConversationStore handles session and message persistence for conversation history.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import time
import uuid


@dataclass
class ConversationMessage:
    """A single message in a conversation."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    role: str = ""  # user, assistant, system, tool
    content: str = ""
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "tool_calls": self.tool_calls,
            "tool_call_id": self.tool_call_id,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationMessage":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ConversationSession:
    """A conversation session containing messages."""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    name: Optional[str] = None
    state: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "name": self.name,
            "state": self.state,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationSession":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class ConversationStore(ABC):
    """
    Abstract base class for conversation persistence.
    
    Implementations handle session and message storage for different backends:
    - PostgreSQL, MySQL, SQLite (relational)
    - SingleStore, Supabase, SurrealDB (hybrid)
    """
    
    @abstractmethod
    def create_session(self, session: ConversationSession) -> ConversationSession:
        """Create a new session."""
        raise NotImplementedError
    
    @abstractmethod
    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get a session by ID."""
        raise NotImplementedError
    
    @abstractmethod
    def update_session(self, session: ConversationSession) -> ConversationSession:
        """Update an existing session."""
        raise NotImplementedError
    
    @abstractmethod
    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages."""
        raise NotImplementedError
    
    @abstractmethod
    def list_sessions(
        self, 
        user_id: Optional[str] = None, 
        agent_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[ConversationSession]:
        """List sessions, optionally filtered by user or agent."""
        raise NotImplementedError
    
    @abstractmethod
    def add_message(self, session_id: str, message: ConversationMessage) -> ConversationMessage:
        """Add a message to a session."""
        raise NotImplementedError
    
    @abstractmethod
    def get_messages(
        self, 
        session_id: str, 
        limit: Optional[int] = None,
        before: Optional[float] = None,
        after: Optional[float] = None
    ) -> List[ConversationMessage]:
        """Get messages from a session."""
        raise NotImplementedError
    
    @abstractmethod
    def delete_messages(self, session_id: str, message_ids: Optional[List[str]] = None) -> int:
        """Delete messages. If message_ids is None, delete all messages in session."""
        raise NotImplementedError
    
    def upsert_session(self, session: ConversationSession) -> ConversationSession:
        """Create or update a session."""
        existing = self.get_session(session.session_id)
        if existing:
            session.updated_at = time.time()
            return self.update_session(session)
        return self.create_session(session)
    
    @abstractmethod
    def close(self) -> None:
        """Close the store and release resources."""
        raise NotImplementedError
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
