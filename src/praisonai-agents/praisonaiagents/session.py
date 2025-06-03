"""
Session Management for PraisonAI Agents

A simple wrapper around existing stateful capabilities to provide a unified
session API for developers building stateful agent applications.
"""

import os
import uuid
from typing import Any, Dict, List, Optional, Union
from .agents import PraisonAIAgents
from .agent import Agent
from .memory import Memory
from .knowledge import Knowledge


class Session:
    """
    A simple wrapper around PraisonAI's existing stateful capabilities.
    
    Provides a unified API for:
    - Session management with persistent state
    - Memory operations (short-term, long-term, user-specific)
    - Knowledge base operations
    - Agent state management
    
    Example:
        session = Session(session_id="chat_123", user_id="user_456")
        
        # Create stateful agent
        agent = session.create_agent(
            name="Assistant", 
            role="Helpful AI",
            memory=True
        )
        
        # Save session state
        session.save_state({"conversation_topic": "AI research"})
        
        # Restore state later
        session.restore_state()
    """
    
    def __init__(
        self, 
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        memory_config: Optional[Dict[str, Any]] = None,
        knowledge_config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize a new session with optional persistence.
        
        Args:
            session_id: Unique session identifier. Auto-generated if None.
            user_id: User identifier for user-specific memory operations.
            memory_config: Configuration for memory system (defaults to RAG)
            knowledge_config: Configuration for knowledge base system
        """
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.user_id = user_id or "default_user"
        
        # Initialize memory with sensible defaults
        default_memory_config = {
            "provider": "rag",
            "use_embedding": True,
            "rag_db_path": f".praison/sessions/{self.session_id}/chroma_db"
        }
        if memory_config:
            default_memory_config.update(memory_config)
        self.memory_config = default_memory_config
        
        # Initialize knowledge with session-specific config
        default_knowledge_config = knowledge_config or {}
        self.knowledge_config = default_knowledge_config
        
        # Create session directory
        os.makedirs(f".praison/sessions/{self.session_id}", exist_ok=True)
        
        # Initialize components lazily
        self._memory = None
        self._knowledge = None
        self._agents_instance = None
        
    @property
    def memory(self) -> Memory:
        """Lazy-loaded memory instance"""
        if self._memory is None:
            self._memory = Memory(config=self.memory_config)
        return self._memory
    
    @property
    def knowledge(self) -> Knowledge:
        """Lazy-loaded knowledge instance"""
        if self._knowledge is None:
            self._knowledge = Knowledge(config=self.knowledge_config)
        return self._knowledge
    
    def create_agent(
        self,
        name: str,
        role: str = "Assistant", 
        instructions: Optional[str] = None,
        tools: Optional[List[Any]] = None,
        memory: bool = True,
        knowledge: Optional[List[str]] = None,
        **kwargs
    ) -> Agent:
        """
        Create an agent with session context.
        
        Args:
            name: Agent name
            role: Agent role
            instructions: Agent instructions
            tools: List of tools for the agent
            memory: Enable memory for the agent
            knowledge: Knowledge sources for the agent
            **kwargs: Additional agent parameters
        
        Returns:
            Configured Agent instance
        """
        agent_kwargs = {
            "name": name,
            "role": role,
            "user_id": self.user_id,
            **kwargs
        }
        
        if instructions:
            agent_kwargs["instructions"] = instructions
        if tools:
            agent_kwargs["tools"] = tools
        if memory:
            agent_kwargs["memory"] = self.memory
        if knowledge:
            agent_kwargs["knowledge"] = knowledge
            agent_kwargs["knowledge_config"] = self.knowledge_config
            
        return Agent(**agent_kwargs)
    
    def save_state(self, state_data: Dict[str, Any]) -> None:
        """
        Save session state data to memory.
        
        Args:
            state_data: Dictionary of state data to save
        """
        state_text = f"Session state: {state_data}"
        self.memory.store_short_term(
            text=state_text,
            metadata={
                "type": "session_state",
                "session_id": self.session_id,
                "user_id": self.user_id,
                **state_data
            }
        )
    
    def restore_state(self) -> Dict[str, Any]:
        """
        Restore session state from memory.
        
        Returns:
            Dictionary of restored state data
        """
        results = self.memory.search_short_term(
            query=f"Session state session_id:{self.session_id}",
            limit=1
        )
        
        if results:
            metadata = results[0].get("metadata", {})
            # Extract state data from metadata (excluding system fields)
            state_data = {k: v for k, v in metadata.items() 
                         if k not in ["type", "session_id", "user_id"]}
            return state_data
        
        return {}
    
    def get_state(self, key: str, default: Any = None) -> Any:
        """Get a specific state value"""
        state = self.restore_state()
        return state.get(key, default)
    
    def set_state(self, key: str, value: Any) -> None:
        """Set a specific state value"""
        current_state = self.restore_state()
        current_state[key] = value
        self.save_state(current_state)
    
    def add_memory(self, text: str, memory_type: str = "long", **metadata) -> None:
        """
        Add information to session memory.
        
        Args:
            text: Text to store
            memory_type: "short" or "long" term memory
            **metadata: Additional metadata
        """
        metadata.update({
            "session_id": self.session_id,
            "user_id": self.user_id
        })
        
        if memory_type == "short":
            self.memory.store_short_term(text, metadata=metadata)
        else:
            self.memory.store_long_term(text, metadata=metadata)
    
    def search_memory(self, query: str, memory_type: str = "long", limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search session memory.
        
        Args:
            query: Search query
            memory_type: "short" or "long" term memory
            limit: Maximum results to return
            
        Returns:
            List of memory results
        """
        if memory_type == "short":
            return self.memory.search_short_term(query, limit=limit)
        else:
            return self.memory.search_long_term(query, limit=limit)
    
    def add_knowledge(self, source: str) -> None:
        """
        Add knowledge source to session.
        
        Args:
            source: File path, URL, or text content
        """
        self.knowledge.add(source, user_id=self.user_id, agent_id=self.session_id)
    
    def search_knowledge(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search session knowledge base.
        
        Args:
            query: Search query
            limit: Maximum results to return
            
        Returns:
            List of knowledge results
        """
        return self.knowledge.search(query, agent_id=self.session_id)
    
    def clear_memory(self, memory_type: str = "all") -> None:
        """
        Clear session memory.
        
        Args:
            memory_type: "short", "long", or "all"
        """
        if memory_type in ["short", "all"]:
            self.memory.reset_short_term()
        if memory_type in ["long", "all"]:
            self.memory.reset_long_term()
    
    def get_context(self, query: str, max_items: int = 3) -> str:
        """
        Build context from session memory and knowledge.
        
        Args:
            query: Query to build context for
            max_items: Maximum items per section
            
        Returns:
            Formatted context string
        """
        return self.memory.build_context_for_task(
            task_descr=query,
            user_id=self.user_id,
            max_items=max_items
        )
    
    def __str__(self) -> str:
        return f"Session(id='{self.session_id}', user='{self.user_id}')"
    
    def __repr__(self) -> str:
        return self.__str__()