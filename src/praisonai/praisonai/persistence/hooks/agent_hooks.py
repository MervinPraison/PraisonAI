"""
Agent hooks for automatic persistence integration.

Provides wrapper functions to add persistence capabilities to PraisonAI agents
without modifying the core SDK.
"""

import time
import uuid
import logging
from typing import Any, Dict, List, Optional, Callable
from functools import wraps

from ..orchestrator import PersistenceOrchestrator
from ..conversation.base import ConversationMessage, ConversationSession

logger = logging.getLogger(__name__)


def wrap_agent_with_persistence(
    agent,
    orchestrator: PersistenceOrchestrator,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    auto_resume: bool = True,
):
    """
    Wrap an agent to add automatic persistence hooks.
    
    This function wraps the agent's chat method to automatically:
    1. Load/create session on first message
    2. Persist each user message
    3. Persist each assistant response
    4. Update session metadata after each interaction
    
    Args:
        agent: PraisonAI Agent instance
        orchestrator: PersistenceOrchestrator instance
        session_id: Session ID (auto-generated if None)
        user_id: User ID for the session
        auto_resume: Whether to auto-resume existing session
    
    Returns:
        The wrapped agent with persistence capabilities
    
    Example:
        from praisonai.persistence import PersistenceOrchestrator
        from praisonai.persistence.hooks import wrap_agent_with_persistence
        from praisonaiagents import Agent
        
        orchestrator = PersistenceOrchestrator(...)
        agent = Agent(name="Assistant", role="Helper")
        
        # Wrap agent with persistence
        agent = wrap_agent_with_persistence(agent, orchestrator, session_id="my-session")
        
        # Now all chats are automatically persisted
        response = agent.chat("Hello!")
    """
    session_id = session_id or f"session-{uuid.uuid4().hex[:8]}"
    user_id = user_id or getattr(agent, 'user_id', 'default')
    
    # Store original chat method
    original_chat = agent.chat
    _session_initialized = [False]  # Use list to allow mutation in closure
    
    @wraps(original_chat)
    def chat_with_persistence(prompt, *args, **kwargs):
        nonlocal _session_initialized
        
        # Initialize session on first call
        if not _session_initialized[0]:
            history = orchestrator.on_agent_start(
                agent, 
                session_id=session_id, 
                user_id=user_id,
                resume=auto_resume
            )
            
            # Inject history into agent's chat_history if resuming
            if auto_resume and history:
                agent.chat_history = [
                    {"role": msg.role, "content": msg.content}
                    for msg in history
                ]
                logger.info(f"Resumed session {session_id} with {len(history)} messages")
            
            _session_initialized[0] = True
        
        # Persist user message
        orchestrator.on_message(session_id, "user", prompt if isinstance(prompt, str) else str(prompt))
        
        # Call original chat
        response = original_chat(prompt, *args, **kwargs)
        
        # Persist assistant response
        if response:
            orchestrator.on_message(session_id, "assistant", response)
        
        return response
    
    # Replace chat method
    agent.chat = chat_with_persistence
    
    # Add persistence-related methods to agent
    agent._persistence_orchestrator = orchestrator
    agent._persistence_session_id = session_id
    
    def get_session():
        """Get the current session."""
        return orchestrator.get_session(session_id)
    
    def get_messages(limit: Optional[int] = None):
        """Get messages from the current session."""
        return orchestrator.get_messages(session_id, limit=limit)
    
    def end_session():
        """End the current session."""
        orchestrator.on_agent_end(agent, session_id)
    
    agent.get_session = get_session
    agent.get_messages = get_messages
    agent.end_session = end_session
    
    return agent


class PersistentAgent:
    """
    A wrapper class that provides persistence capabilities for any agent.
    
    This is an alternative to wrap_agent_with_persistence that uses composition
    instead of monkey-patching.
    
    Example:
        from praisonai.persistence import PersistenceOrchestrator
        from praisonai.persistence.hooks import PersistentAgent
        from praisonaiagents import Agent
        
        orchestrator = PersistenceOrchestrator(...)
        base_agent = Agent(name="Assistant", role="Helper")
        
        agent = PersistentAgent(base_agent, orchestrator, session_id="my-session")
        response = agent.chat("Hello!")
    """
    
    def __init__(
        self,
        agent,
        orchestrator: PersistenceOrchestrator,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        auto_resume: bool = True,
    ):
        self._agent = agent
        self._orchestrator = orchestrator
        self._session_id = session_id or f"session-{uuid.uuid4().hex[:8]}"
        self._user_id = user_id or getattr(agent, 'user_id', 'default')
        self._auto_resume = auto_resume
        self._session_initialized = False
    
    def __getattr__(self, name):
        """Delegate attribute access to wrapped agent."""
        return getattr(self._agent, name)
    
    def _ensure_session(self):
        """Ensure session is initialized."""
        if not self._session_initialized:
            history = self._orchestrator.on_agent_start(
                self._agent,
                session_id=self._session_id,
                user_id=self._user_id,
                resume=self._auto_resume
            )
            
            if self._auto_resume and history:
                self._agent.chat_history = [
                    {"role": msg.role, "content": msg.content}
                    for msg in history
                ]
                logger.info(f"Resumed session {self._session_id} with {len(history)} messages")
            
            self._session_initialized = True
    
    def chat(self, prompt, *args, **kwargs):
        """Chat with automatic persistence."""
        self._ensure_session()
        
        # Persist user message
        self._orchestrator.on_message(
            self._session_id, "user", 
            prompt if isinstance(prompt, str) else str(prompt)
        )
        
        # Call agent chat
        response = self._agent.chat(prompt, *args, **kwargs)
        
        # Persist assistant response
        if response:
            self._orchestrator.on_message(self._session_id, "assistant", response)
        
        return response
    
    def get_session(self) -> Optional[ConversationSession]:
        """Get the current session."""
        return self._orchestrator.get_session(self._session_id)
    
    def get_messages(self, limit: Optional[int] = None) -> List[ConversationMessage]:
        """Get messages from the current session."""
        return self._orchestrator.get_messages(self._session_id, limit=limit)
    
    def end_session(self):
        """End the current session."""
        self._orchestrator.on_agent_end(self._agent, self._session_id)
    
    @property
    def session_id(self) -> str:
        """Get the session ID."""
        return self._session_id


def create_persistent_session(
    orchestrator: PersistenceOrchestrator,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
):
    """
    Create a context manager for persistent sessions.
    
    Example:
        from praisonai.persistence import PersistenceOrchestrator
        from praisonai.persistence.hooks import create_persistent_session
        from praisonaiagents import Agent
        
        orchestrator = PersistenceOrchestrator(...)
        
        with create_persistent_session(orchestrator, session_id="my-session") as session:
            agent = Agent(name="Assistant", role="Helper")
            
            # Messages are persisted within the session context
            session.persist_message("user", "Hello!")
            response = agent.chat("Hello!")
            session.persist_message("assistant", response)
    """
    
    class PersistentSession:
        def __init__(self, orchestrator, session_id, user_id):
            self.orchestrator = orchestrator
            self.session_id = session_id or f"session-{uuid.uuid4().hex[:8]}"
            self.user_id = user_id or "default"
            self._started = False
        
        def __enter__(self):
            self.start()
            return self
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            self.end()
            return False
        
        def start(self, agent=None):
            """Start the session."""
            if not self._started:
                class MockAgent:
                    name = "session-agent"
                
                self.orchestrator.on_agent_start(
                    agent or MockAgent(),
                    session_id=self.session_id,
                    user_id=self.user_id
                )
                self._started = True
        
        def end(self, agent=None):
            """End the session."""
            if self._started:
                class MockAgent:
                    name = "session-agent"
                
                self.orchestrator.on_agent_end(
                    agent or MockAgent(),
                    self.session_id
                )
        
        def persist_message(self, role: str, content: str):
            """Persist a message to the session."""
            self.orchestrator.on_message(self.session_id, role, content)
        
        def get_messages(self, limit: Optional[int] = None):
            """Get messages from the session."""
            return self.orchestrator.get_messages(self.session_id, limit=limit)
        
        def get_session(self):
            """Get the session object."""
            return self.orchestrator.get_session(self.session_id)
    
    return PersistentSession(orchestrator, session_id, user_id)
