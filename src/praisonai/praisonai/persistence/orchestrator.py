"""
PersistenceOrchestrator - Central coordinator for all persistence operations.

Hooks into agent lifecycle to provide automatic conversation persistence,
knowledge retrieval, and state management.
"""

import logging
import time
import uuid
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .conversation.base import ConversationStore, ConversationSession, ConversationMessage
from .knowledge.base import KnowledgeStore, KnowledgeDocument
from .state.base import StateStore
from .config import PersistenceConfig
from .factory import create_stores_from_config

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PersistenceOrchestrator:
    """
    Central coordinator for all persistence operations.
    
    Lives in wrapper layer, hooks into agent lifecycle to provide:
    - Automatic session loading/creation at agent start
    - Message persistence during conversation
    - Session metadata updates at agent end
    - Knowledge retrieval for RAG
    - State caching
    
    Example:
        orchestrator = PersistenceOrchestrator(
            conversation_store=PostgresConversationStore(...),
            knowledge_store=QdrantKnowledgeStore(...),
            state_store=RedisStateStore(...),
        )
        
        # Hook into agent lifecycle
        history = orchestrator.on_agent_start(agent, session_id="sess-123")
        # ... agent runs ...
        orchestrator.on_message(session_id, user_message)
        orchestrator.on_message(session_id, assistant_message)
        orchestrator.on_agent_end(agent, session_id)
    """
    
    def __init__(
        self,
        conversation_store: Optional[ConversationStore] = None,
        knowledge_store: Optional[KnowledgeStore] = None,
        state_store: Optional[StateStore] = None,
        config: Optional[PersistenceConfig] = None,
    ):
        """
        Initialize the orchestrator.
        
        Args:
            conversation_store: Store for session/message persistence
            knowledge_store: Store for vector embeddings
            state_store: Store for key-value state
            config: Configuration (alternative to passing stores directly)
        """
        if config:
            stores = create_stores_from_config(config)
            self.conversation = stores["conversation"] or conversation_store
            self.knowledge = stores["knowledge"] or knowledge_store
            self.state = stores["state"] or state_store
            self._config = config
        else:
            self.conversation = conversation_store
            self.knowledge = knowledge_store
            self.state = state_store
            self._config = None
        
        self._current_session: Optional[ConversationSession] = None
        self._session_cache: Dict[str, ConversationSession] = {}
    
    @classmethod
    def from_config(cls, config: PersistenceConfig) -> "PersistenceOrchestrator":
        """Create orchestrator from configuration."""
        return cls(config=config)
    
    @classmethod
    def from_env(cls) -> "PersistenceOrchestrator":
        """Create orchestrator from environment variables."""
        config = PersistenceConfig.from_env()
        return cls(config=config)
    
    # =========================================================================
    # Agent Lifecycle Hooks
    # =========================================================================
    
    def on_agent_start(
        self,
        agent: Any,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        resume: bool = True,
    ) -> List[ConversationMessage]:
        """
        Called before agent run. Loads or creates session.
        
        Args:
            agent: The agent instance
            session_id: Session ID (generated if not provided)
            user_id: User ID for session
            resume: Whether to load existing session history
        
        Returns:
            List of previous messages if resuming, empty list otherwise
        """
        if not session_id:
            session_id = str(uuid.uuid4())
        
        if not self.conversation:
            logger.debug("No conversation store configured, skipping session load")
            return []
        
        # Try to load existing session
        session = None
        if resume:
            session = self.conversation.get_session(session_id)
        
        if session:
            logger.info(f"Resuming session: {session_id}")
            self._current_session = session
            self._session_cache[session_id] = session
            
            # Load previous messages
            messages = self.conversation.get_messages(session_id)
            return messages
        else:
            # Create new session
            agent_id = getattr(agent, "name", None) or getattr(agent, "agent_id", None)
            session = ConversationSession(
                session_id=session_id,
                user_id=user_id,
                agent_id=agent_id,
                name=f"Session {session_id[:8]}",
                metadata={"agent_type": type(agent).__name__},
            )
            self.conversation.create_session(session)
            logger.info(f"Created new session: {session_id}")
            self._current_session = session
            self._session_cache[session_id] = session
            return []
    
    def on_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_calls: Optional[List[Dict]] = None,
        tool_call_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[ConversationMessage]:
        """
        Called after each message (user or assistant).
        
        Args:
            session_id: Session ID
            role: Message role (user, assistant, system, tool)
            content: Message content
            tool_calls: Tool calls (for assistant messages)
            tool_call_id: Tool call ID (for tool response messages)
            metadata: Additional metadata
        
        Returns:
            The persisted message, or None if no store configured
        """
        if not self.conversation:
            return None
        
        message = ConversationMessage(
            id=str(uuid.uuid4()),
            session_id=session_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
            metadata=metadata,
        )
        
        self.conversation.add_message(session_id, message)
        logger.debug(f"Persisted {role} message to session {session_id}")
        return message
    
    def on_agent_end(
        self,
        agent: Any,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Called after agent run. Updates session metadata.
        
        Args:
            agent: The agent instance
            session_id: Session ID
            metadata: Additional metadata to store
        """
        if not self.conversation:
            return
        
        session = self._session_cache.get(session_id) or self.conversation.get_session(session_id)
        if session:
            session.updated_at = time.time()
            if metadata:
                session.metadata = {**(session.metadata or {}), **metadata}
            self.conversation.update_session(session)
            logger.debug(f"Updated session metadata: {session_id}")
    
    # =========================================================================
    # Knowledge Retrieval
    # =========================================================================
    
    def retrieve_knowledge(
        self,
        query_embedding: List[float],
        collection: str = "default",
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[KnowledgeDocument]:
        """
        Retrieve relevant documents for RAG.
        
        Args:
            query_embedding: Query vector embedding
            collection: Collection name
            limit: Max documents to return
            filters: Metadata filters
        
        Returns:
            List of relevant documents
        """
        if not self.knowledge:
            logger.debug("No knowledge store configured")
            return []
        
        return self.knowledge.search(
            collection=collection,
            query_embedding=query_embedding,
            limit=limit,
            filters=filters,
        )
    
    def add_knowledge(
        self,
        documents: List[KnowledgeDocument],
        collection: str = "default",
    ) -> List[str]:
        """
        Add documents to knowledge store.
        
        Args:
            documents: Documents with embeddings
            collection: Collection name
        
        Returns:
            List of document IDs
        """
        if not self.knowledge:
            raise ValueError("No knowledge store configured")
        
        return self.knowledge.upsert(collection, documents)
    
    # =========================================================================
    # State Management
    # =========================================================================
    
    def get_state(self, key: str) -> Optional[Any]:
        """Get state value."""
        if not self.state:
            return None
        return self.state.get(key)
    
    def set_state(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set state value with optional TTL."""
        if not self.state:
            return
        self.state.set(key, value, ttl)
    
    def delete_state(self, key: str) -> bool:
        """Delete state value."""
        if not self.state:
            return False
        return self.state.delete(key)
    
    # =========================================================================
    # Session Management
    # =========================================================================
    
    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get a session by ID."""
        if not self.conversation:
            return None
        return self.conversation.get_session(session_id)
    
    def list_sessions(
        self,
        user_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[ConversationSession]:
        """List sessions for a user."""
        if not self.conversation:
            return []
        return self.conversation.list_sessions(user_id=user_id, limit=limit)
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages."""
        if not self.conversation:
            return False
        
        if session_id in self._session_cache:
            del self._session_cache[session_id]
        
        return self.conversation.delete_session(session_id)
    
    def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
    ) -> List[ConversationMessage]:
        """Get messages from a session."""
        if not self.conversation:
            return []
        return self.conversation.get_messages(session_id, limit=limit)
    
    # =========================================================================
    # Context Building
    # =========================================================================
    
    def build_context(
        self,
        session_id: str,
        query_embedding: Optional[List[float]] = None,
        history_limit: int = 20,
        knowledge_limit: int = 5,
        knowledge_collection: str = "default",
    ) -> Dict[str, Any]:
        """
        Build context for agent including history and knowledge.
        
        Args:
            session_id: Session ID
            query_embedding: Query embedding for knowledge retrieval
            history_limit: Max history messages
            knowledge_limit: Max knowledge documents
            knowledge_collection: Knowledge collection name
        
        Returns:
            Dict with 'history' and 'knowledge' keys
        """
        context = {
            "history": [],
            "knowledge": [],
        }
        
        # Get conversation history
        if self.conversation:
            messages = self.conversation.get_messages(session_id, limit=history_limit)
            context["history"] = [
                {"role": m.role, "content": m.content}
                for m in messages
            ]
        
        # Get relevant knowledge
        if self.knowledge and query_embedding:
            docs = self.knowledge.search(
                collection=knowledge_collection,
                query_embedding=query_embedding,
                limit=knowledge_limit,
            )
            context["knowledge"] = [
                {"content": d.content, "metadata": d.metadata}
                for d in docs
            ]
        
        return context
    
    # =========================================================================
    # Cleanup
    # =========================================================================
    
    def close(self) -> None:
        """Close all stores and release resources."""
        if self.conversation:
            self.conversation.close()
        if self.knowledge:
            self.knowledge.close()
        if self.state:
            self.state.close()
        
        self._session_cache.clear()
        logger.info("Persistence orchestrator closed")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
