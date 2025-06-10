"""
Session Management for PraisonAI Agents

A simple wrapper around existing stateful capabilities to provide a unified
session API for developers building stateful agent applications.
"""

import os
import uuid
import requests
import json
import time
from typing import Any, Dict, List, Optional
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
    - Remote agent connectivity
    
    Examples:
        # Local session with agent
        session = Session(session_id="chat_123", user_id="user_456")
        agent = session.Agent(name="Assistant", role="Helpful AI")
        
        # Remote agent session (similar to Google ADK)
        session = Session(agent_url="192.168.1.10:8000/agent")
        response = session.chat("Hello from remote client!")
        
        # Save session state
        session.save_state({"conversation_topic": "AI research"})
    """

    def __init__(
        self, 
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        agent_url: Optional[str] = None,
        memory_config: Optional[Dict[str, Any]] = None,
        knowledge_config: Optional[Dict[str, Any]] = None,
        timeout: int = 30
    ):
        """
        Initialize a new session with optional persistence or remote agent connectivity.
        
        Args:
            session_id: Unique session identifier. Auto-generated if None.
            user_id: User identifier for user-specific memory operations.
            agent_url: URL of remote agent for direct connectivity (e.g., "192.168.1.10:8000/agent")
            memory_config: Configuration for memory system (defaults to RAG)
            knowledge_config: Configuration for knowledge base system  
            timeout: HTTP timeout for remote agent calls (default: 30 seconds)
        """
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.user_id = user_id or "default_user"
        self.agent_url = agent_url
        self.timeout = timeout
        self.is_remote = agent_url is not None

        # Validate agent_url format
        if self.is_remote:
            if not self.agent_url.startswith(('http://', 'https://')):
                # Assume http if no protocol specified
                self.agent_url = f"http://{self.agent_url}"
            # Test connectivity to remote agent
            self._test_remote_connection()

        # Initialize memory with sensible defaults (only for local sessions)
        if not self.is_remote:
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
        else:
            # For remote sessions, disable local memory/knowledge
            self.memory_config = {}
            self.knowledge_config = {}
            self._memory = None
            self._knowledge = None
            self._agents_instance = None

    @property
    def memory(self) -> Memory:
        """Lazy-loaded memory instance"""
        if self.is_remote:
            raise ValueError("Memory operations are not available for remote agent sessions")
        if self._memory is None:
            self._memory = Memory(config=self.memory_config)
        return self._memory

    @property
    def knowledge(self) -> Knowledge:
        """Lazy-loaded knowledge instance"""
        if self.is_remote:
            raise ValueError("Knowledge operations are not available for remote agent sessions")
        if self._knowledge is None:
            self._knowledge = Knowledge(config=self.knowledge_config)
        return self._knowledge

    def Agent(
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
            
        Raises:
            ValueError: If this is a remote session (use chat() instead)
        """
        if self.is_remote:
            raise ValueError("Cannot create local agents in remote sessions. Use chat() to communicate with the remote agent.")

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

    # Keep create_agent for backward compatibility
    def create_agent(self, *args, **kwargs) -> Agent:
        """Backward compatibility wrapper for Agent method"""
        return self.Agent(*args, **kwargs)

    def save_state(self, state_data: Dict[str, Any]) -> None:
        """
        Save session state data to memory.
        
        Args:
            state_data: Dictionary of state data to save
            
        Raises:
            ValueError: If this is a remote session
        """
        if self.is_remote:
            raise ValueError("State operations are not available for remote agent sessions")
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
            
        Raises:
            ValueError: If this is a remote session
        """
        if self.is_remote:
            raise ValueError("State operations are not available for remote agent sessions")
        # Use metadata-based search for better SQLite compatibility
        results = self.memory.search_short_term(
            query=f"type:session_state",
            limit=10  # Get more results to filter by session_id
        )

        # Filter results by session_id in metadata
        for result in results:
            metadata = result.get("metadata", {})
            if (metadata.get("type") == "session_state" and 
                metadata.get("session_id") == self.session_id):
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
        return self.knowledge.search(query, agent_id=self.session_id, limit=limit)

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

    def _test_remote_connection(self) -> None:
        """
        Test connectivity to the remote agent.
        
        Raises:
            ConnectionError: If unable to connect to the remote agent
        """
        try:
            # Try a simple GET request to check if the server is responding
            test_url = self.agent_url.rstrip('/') + '/health' if '/health' not in self.agent_url else self.agent_url
            response = requests.get(test_url, timeout=self.timeout)
            if response.status_code != 200:
                # If health endpoint fails, try the main endpoint
                response = requests.head(self.agent_url, timeout=self.timeout)
                if response.status_code not in [200, 405]:  # 405 = Method Not Allowed is OK
                    raise ConnectionError(f"Remote agent returned status code: {response.status_code}")
            print(f"✅ Successfully connected to remote agent at {self.agent_url}")
        except requests.exceptions.Timeout:
            raise ConnectionError(f"Timeout connecting to remote agent at {self.agent_url}")
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Failed to connect to remote agent at {self.agent_url}")
        except Exception as e:
            raise ConnectionError(f"Error connecting to remote agent: {str(e)}")

    def chat(self, message: str, **kwargs) -> str:
        """
        Send a message to the remote agent or handle local session.
        
        Args:
            message: The message to send to the agent
            **kwargs: Additional parameters for the request
            
        Returns:
            The agent's response
            
        Raises:
            ValueError: If this is not a remote session
            ConnectionError: If unable to communicate with remote agent
        """
        if not self.is_remote:
            raise ValueError("chat() method is only available for remote agent sessions. Use Agent.chat() for local agents.")
        
        try:
            # Prepare the request payload
            payload = {
                "query": message,
                "session_id": self.session_id,
                "user_id": self.user_id,
                **kwargs
            }
            
            # Send POST request to the remote agent
            response = requests.post(
                self.agent_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout
            )
            
            # Check if request was successful
            response.raise_for_status()
            
            # Parse the response
            result = response.json()
            
            # Extract the agent's response
            if isinstance(result, dict):
                return result.get("response", str(result))
            else:
                return str(result)
                
        except requests.exceptions.Timeout:
            raise ConnectionError(f"Timeout communicating with remote agent at {self.agent_url}")
        except requests.exceptions.ConnectionError:
            raise ConnectionError(f"Failed to communicate with remote agent at {self.agent_url}")
        except requests.exceptions.HTTPError as e:
            raise ConnectionError(f"HTTP error from remote agent: {e}")
        except json.JSONDecodeError:
            # If response is not JSON, return the raw text
            return response.text
        except Exception as e:
            raise ConnectionError(f"Error communicating with remote agent: {str(e)}")

    def send_message(self, message: str, **kwargs) -> str:
        """
        Alias for chat() method to match Google ADK pattern.
        
        Args:
            message: The message to send to the agent
            **kwargs: Additional parameters for the request
            
        Returns:
            The agent's response
        """
        return self.chat(message, **kwargs)

    def __str__(self) -> str:
        if self.is_remote:
            return f"Session(id='{self.session_id}', user='{self.user_id}', remote_agent='{self.agent_url}')"
        return f"Session(id='{self.session_id}', user='{self.user_id}')"

    def __repr__(self) -> str:
        return self.__str__()