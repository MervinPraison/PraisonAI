"""
PraisonDB adapter - implements the DbAdapter protocol from praisonaiagents.

This module provides the bridge between the core Agent's db interface
and the wrapper's persistence layer (PersistenceOrchestrator).
"""

import time
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PraisonDB:
    """
    Universal database adapter for PraisonAI agents.
    
    Automatically selects backends based on URL or explicit configuration.
    Implements the DbAdapter protocol expected by praisonaiagents.Agent.
    
    Example:
        from praisonaiagents import Agent
        from praisonai.db import PraisonDB
        
        # Simple usage with PostgreSQL
        db = PraisonDB(database_url="postgresql://localhost/mydb")
        agent = Agent(name="Assistant", db=db, session_id="my-session")
        agent.chat("Hello!")
        
        # With multiple backends
        db = PraisonDB(
            database_url="postgresql://localhost/mydb",
            state_url="redis://localhost:6379"
        )
    """
    
    def __init__(
        self,
        database_url: Optional[str] = None,
        state_url: Optional[str] = None,
        knowledge_url: Optional[str] = None,
        **options
    ):
        """
        Initialize PraisonDB adapter.
        
        Args:
            database_url: URL for conversation storage (postgres, mysql, sqlite)
            state_url: URL for state storage (redis, etc.)
            knowledge_url: URL for knowledge/vector storage (qdrant, etc.)
            **options: Additional backend-specific options
        """
        self._database_url = database_url
        self._state_url = state_url
        self._knowledge_url = knowledge_url
        self._options = options
        
        # Lazy-loaded stores
        self._conversation_store = None
        self._state_store = None
        self._knowledge_store = None
        self._initialized = False
    
    def _init_stores(self):
        """Lazily initialize stores on first use."""
        if self._initialized:
            return
        
        # Import persistence layer
        from ..persistence.factory import (
            create_conversation_store,
            create_state_store,
            create_knowledge_store,
        )
        
        # Initialize conversation store
        if self._database_url:
            backend = self._detect_backend(self._database_url)
            self._conversation_store = create_conversation_store(
                backend, url=self._database_url, **self._options
            )
        
        # Initialize state store
        if self._state_url:
            backend = self._detect_backend(self._state_url)
            self._state_store = create_state_store(
                backend, url=self._state_url, **self._options
            )
        
        # Initialize knowledge store
        if self._knowledge_url:
            backend = self._detect_backend(self._knowledge_url)
            self._knowledge_store = create_knowledge_store(
                backend, url=self._knowledge_url, **self._options
            )
        
        self._initialized = True
    
    def _detect_backend(self, url: str) -> str:
        """Detect backend type from URL."""
        url_lower = url.lower()
        
        if url_lower.startswith("postgresql://") or url_lower.startswith("postgres://"):
            return "postgres"
        elif url_lower.startswith("mysql://"):
            return "mysql"
        elif url_lower.startswith("sqlite://") or url_lower.endswith(".db"):
            return "sqlite"
        elif url_lower.startswith("redis://"):
            return "redis"
        elif url_lower.startswith("http://") or url_lower.startswith("https://"):
            # Could be Qdrant, Weaviate, etc.
            if "qdrant" in url_lower or ":6333" in url_lower:
                return "qdrant"
            elif "weaviate" in url_lower:
                return "weaviate"
        
        # Default fallback
        return "sqlite"
    
    def on_agent_start(
        self,
        agent_name: str,
        session_id: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List:
        """Called when agent starts - returns previous messages for resume."""
        self._init_stores()
        
        if not self._conversation_store:
            return []
        
        from ..persistence.conversation.base import ConversationSession
        
        # Check if session exists
        session = self._conversation_store.get_session(session_id)
        
        if session is None:
            # Create new session
            session = ConversationSession(
                session_id=session_id,
                user_id=user_id or "default",
                agent_id=agent_name,
                name=f"Session {session_id}",
                metadata=metadata or {}
            )
            self._conversation_store.create_session(session)
            return []
        
        # Resume existing session - get messages
        messages = self._conversation_store.get_messages(session_id)
        
        # Convert to DbMessage format
        from praisonaiagents.db.protocol import DbMessage
        return [
            DbMessage(
                role=msg.role,
                content=msg.content,
                metadata=msg.metadata or {},
                timestamp=msg.created_at or time.time(),
                id=msg.id
            )
            for msg in messages
        ]
    
    def on_user_message(
        self,
        session_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Called when user sends a message."""
        if not self._conversation_store:
            return
        
        from ..persistence.conversation.base import ConversationMessage
        import uuid
        
        msg = ConversationMessage(
            id=f"msg-{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            role="user",
            content=content,
            metadata=metadata or {},
            created_at=time.time()
        )
        self._conversation_store.add_message(session_id, msg)
    
    def on_agent_message(
        self,
        session_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Called when agent produces a response."""
        if not self._conversation_store:
            return
        
        from ..persistence.conversation.base import ConversationMessage
        import uuid
        
        msg = ConversationMessage(
            id=f"msg-{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            role="assistant",
            content=content,
            metadata=metadata or {},
            created_at=time.time()
        )
        self._conversation_store.add_message(session_id, msg)
    
    def on_tool_call(
        self,
        session_id: str,
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Called when a tool is executed."""
        if not self._conversation_store:
            return
        
        from ..persistence.conversation.base import ConversationMessage
        import uuid
        import json
        
        # Store tool call as a special message
        tool_content = json.dumps({
            "tool": tool_name,
            "args": args,
            "result": str(result)[:1000]  # Truncate large results
        })
        
        msg = ConversationMessage(
            id=f"tool-{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            role="tool",
            content=tool_content,
            metadata={"tool_name": tool_name, **(metadata or {})},
            created_at=time.time()
        )
        self._conversation_store.add_message(session_id, msg)
    
    def on_agent_end(
        self,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Called when agent session ends."""
        if not self._conversation_store:
            return
        
        # Update session metadata
        session = self._conversation_store.get_session(session_id)
        if session:
            session.metadata = {**(session.metadata or {}), "ended_at": time.time()}
            self._conversation_store.update_session(session)
    
    def on_run_start(
        self,
        session_id: str,
        run_id: str,
        input_content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Called when a new run (turn) starts."""
        if not self._conversation_store:
            return
        
        # Store run start in state if available
        if self._state_store:
            run_key = f"run:{session_id}:{run_id}"
            self._state_store.set(run_key, {
                "run_id": run_id,
                "session_id": session_id,
                "started_at": time.time(),
                "input_content": input_content,
                "status": "running",
                "metadata": metadata or {}
            })
    
    def on_run_end(
        self,
        session_id: str,
        run_id: str,
        output_content: Optional[str] = None,
        status: str = "completed",
        metrics: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Called when a run (turn) ends."""
        if self._state_store:
            run_key = f"run:{session_id}:{run_id}"
            run_data = self._state_store.get(run_key) or {}
            run_data.update({
                "ended_at": time.time(),
                "output_content": output_content,
                "status": status,
                "metrics": metrics or {},
                "metadata": {**run_data.get("metadata", {}), **(metadata or {})}
            })
            self._state_store.set(run_key, run_data)
    
    def get_runs(
        self,
        session_id: str,
        limit: Optional[int] = None,
    ) -> List:
        """Get runs for a session."""
        # For now, runs are stored in state store
        # Full implementation would query from conversation store
        return []
    
    def export_session(
        self,
        session_id: str,
    ) -> Dict[str, Any]:
        """Export a session as a dictionary."""
        self._init_stores()
        
        if not self._conversation_store:
            return {}
        
        session = self._conversation_store.get_session(session_id)
        if not session:
            return {}
        
        messages = self._conversation_store.get_messages(session_id)
        
        return {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "agent_id": session.agent_id,
            "name": session.name,
            "metadata": session.metadata,
            "created_at": session.created_at,
            "messages": [
                {
                    "id": msg.id,
                    "role": msg.role,
                    "content": msg.content,
                    "metadata": msg.metadata,
                    "created_at": msg.created_at
                }
                for msg in messages
            ]
        }
    
    def import_session(
        self,
        data: Dict[str, Any],
    ) -> str:
        """Import a session from a dictionary."""
        self._init_stores()
        
        if not self._conversation_store:
            raise ValueError("No conversation store configured")
        
        from ..persistence.conversation.base import ConversationSession, ConversationMessage
        import uuid
        
        session_id = data.get("session_id") or f"imported-{uuid.uuid4().hex[:8]}"
        
        # Create session
        session = ConversationSession(
            session_id=session_id,
            user_id=data.get("user_id", "default"),
            agent_id=data.get("agent_id", "imported"),
            name=data.get("name", f"Imported Session {session_id}"),
            metadata=data.get("metadata", {})
        )
        self._conversation_store.create_session(session)
        
        # Import messages with new IDs to avoid conflicts
        for msg_data in data.get("messages", []):
            msg = ConversationMessage(
                id=f"msg-{uuid.uuid4().hex[:12]}",  # Always generate new ID
                session_id=session_id,
                role=msg_data.get("role", "user"),
                content=msg_data.get("content", ""),
                metadata=msg_data.get("metadata", {}),
                created_at=msg_data.get("created_at", time.time())
            )
            self._conversation_store.add_message(session_id, msg)
        
        return session_id
    
    # --- Tracing/Observability ---
    
    def on_trace_start(
        self,
        trace_id: str,
        session_id: Optional[str] = None,
        run_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Called when a new trace starts."""
        if self._state_store:
            trace_key = f"trace:{trace_id}"
            self._state_store.set(trace_key, {
                "trace_id": trace_id,
                "session_id": session_id,
                "run_id": run_id,
                "agent_name": agent_name,
                "user_id": user_id,
                "started_at": time.time(),
                "status": "running",
                "spans": [],
                "metadata": metadata or {}
            })
    
    def on_trace_end(
        self,
        trace_id: str,
        status: str = "ok",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Called when a trace ends."""
        if self._state_store:
            trace_key = f"trace:{trace_id}"
            trace_data = self._state_store.get(trace_key) or {}
            trace_data.update({
                "ended_at": time.time(),
                "status": status,
                "metadata": {**trace_data.get("metadata", {}), **(metadata or {})}
            })
            self._state_store.set(trace_key, trace_data)
    
    def on_span_start(
        self,
        span_id: str,
        trace_id: str,
        name: str,
        parent_span_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Called when a new span starts."""
        if self._state_store:
            span_key = f"span:{span_id}"
            self._state_store.set(span_key, {
                "span_id": span_id,
                "trace_id": trace_id,
                "name": name,
                "parent_span_id": parent_span_id,
                "started_at": time.time(),
                "status": "running",
                "attributes": attributes or {},
                "events": []
            })
    
    def on_span_end(
        self,
        span_id: str,
        status: str = "ok",
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Called when a span ends."""
        if self._state_store:
            span_key = f"span:{span_id}"
            span_data = self._state_store.get(span_key) or {}
            span_data.update({
                "ended_at": time.time(),
                "status": status,
                "attributes": {**span_data.get("attributes", {}), **(attributes or {})}
            })
            self._state_store.set(span_key, span_data)
    
    def get_traces(
        self,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List:
        """Get traces with optional filters."""
        # For now, return empty list - full implementation would scan state store
        return []
    
    def close(self) -> None:
        """Close all database connections."""
        if self._conversation_store:
            self._conversation_store.close()
        if self._state_store:
            self._state_store.close()
        if self._knowledge_store:
            self._knowledge_store.close()


class PostgresDB(PraisonDB):
    """PostgreSQL-specific database adapter."""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "praisonai",
        user: str = "postgres",
        password: str = "",
        **options
    ):
        url = f"postgresql://{user}:{password}@{host}:{port}/{database}"
        super().__init__(database_url=url, **options)


class SQLiteDB(PraisonDB):
    """SQLite-specific database adapter."""
    
    def __init__(self, path: str = "praisonai.db", database_url: str = None, **options):
        # Allow either path or database_url
        url = database_url or path
        super().__init__(database_url=url, **options)
    
    def _detect_backend(self, url: str) -> str:
        return "sqlite"


class RedisDB(PraisonDB):
    """Redis-specific database adapter (for state only)."""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        **options
    ):
        url = f"redis://{host}:{port}"
        super().__init__(state_url=url, **options)
