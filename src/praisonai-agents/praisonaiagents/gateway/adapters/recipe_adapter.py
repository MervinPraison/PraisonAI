"""
RecipeBotAdapter - Bridge between Recipe Runtime and Agent/Bot protocols.

This adapter wraps a Recipe's execution environment behind the standard Agent
duck-typing interface, enabling recipes to be used with Gateway and BotOS.
"""

import asyncio
import logging
import uuid
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from praisonaiagents.streaming import StreamEventEmitter

logger = logging.getLogger(__name__)


class RecipeBotAdapter:
    """
    Adapter that implements the standard Agent interface by wrapping Recipe execution.
    
    This allows recipes to work seamlessly with:
    - WebSocket Gateway sessions
    - BotOS multi-platform bots
    - Any system expecting an Agent-like interface
    
    Key features:
    - Implements .chat(message: str) -> str
    - Provides .stream_emitter for Gateway streaming support
    - Maintains conversation context via Recipe variables
    - Supports Human-in-The-Loop via context injection
    
    Example:
        recipe_adapter = RecipeBotAdapter("support-team-recipe")
        response = recipe_adapter.chat("User has issue with login")
        
        # Use with Gateway
        gateway.register_agent(recipe_adapter, agent_id="support")
    """
    
    def __init__(
        self,
        recipe_name: str,
        recipe_config: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        **recipe_options
    ):
        """
        Initialize the Recipe Bot Adapter.
        
        Args:
            recipe_name: Name of the recipe to execute
            recipe_config: Optional recipe configuration overrides
            session_id: Session ID for state grouping
            **recipe_options: Additional options passed to recipe execution
        """
        self.recipe_name = recipe_name
        self.recipe_config = recipe_config or {}
        self.session_id = session_id or f"recipe-session-{uuid.uuid4().hex[:12]}"
        self.recipe_options = recipe_options
        
        # Agent-like properties
        self.name = recipe_name
        self.agent_id = f"recipe-{recipe_name}"
        
        # Context variables for human-in-the-loop (per-session)
        self._context_by_session: Dict[str, Dict[str, Any]] = {}
        self.context_variables: Dict[str, Any] = {}  # Default session context
        
        # Optional streaming support
        self._stream_emitter: Optional["StreamEventEmitter"] = None
        self._setup_streaming()
        
        logger.info(f"RecipeBotAdapter initialized for recipe '{recipe_name}'")
    
    def _setup_streaming(self) -> None:
        """Setup streaming emitter if available."""
        try:
            from praisonaiagents.streaming import StreamEventEmitter
            self._stream_emitter = StreamEventEmitter()
            logger.debug(f"Streaming enabled for recipe adapter '{self.recipe_name}'")
        except ImportError:
            logger.debug("Streaming not available, continuing without stream support")
            self._stream_emitter = None
    
    @property
    def stream_emitter(self) -> Optional["StreamEventEmitter"]:
        """Get the stream emitter for Gateway integration."""
        return self._stream_emitter
    
    def chat(self, prompt: str, **kwargs) -> str:
        """
        Process a message through the recipe execution.
        
        This is the main interface method that makes the adapter compatible
        with Agent expectations.
        
        Args:
            prompt: User input message
            **kwargs: Additional options (session_id, etc.)
            
        Returns:
            Recipe execution result as string
        """
        # Extract session ID from kwargs if provided
        session_id = kwargs.get('session_id', self.session_id)
        
        try:
            # Lazy import to prevent circular dependencies
            from praisonai.recipe.core import run
            
            # Get session-specific context
            session_context = self._context_by_session.get(session_id, {})
            combined_context = {**self.context_variables, **session_context}
            
            # Prepare input with message and context (separate from config)
            recipe_input = {
                "user_input": prompt,
                "message": prompt,  # Alternative key
                **combined_context,
            }
            
            # Keep config separate from input to prevent corruption
            config = dict(self.recipe_config) if self.recipe_config else {}
            
            # Execute recipe
            result = run(
                name=self.recipe_name,
                input=recipe_input,
                config=config,
                session_id=session_id,
                options=self.recipe_options,
            )
            
            # Extract output based on recipe result structure
            if hasattr(result, 'output') and result.output is not None:
                if isinstance(result.output, dict):
                    # Try common output keys
                    for key in ["response", "reply", "result", "output"]:
                        if key in result.output:
                            return str(result.output[key])
                    # Fallback to first string value
                    for value in result.output.values():
                        if isinstance(value, str) and value.strip():
                            return value
                    return str(result.output)
                else:
                    return str(result.output)
            elif hasattr(result, 'error') and result.error is not None:
                return f"Recipe error: {result.error}"
            else:
                return "Recipe executed successfully"
                
        except ImportError:
            logger.exception(
                "Recipe runtime import failed (recipe=%s, session_id=%s)",
                self.recipe_name, session_id
            )
            return (
                "Recipe execution is unavailable. Install extras with "
                "`pip install praisonaiagents[extras]`."
            )
        except Exception:
            logger.exception(
                "Recipe execution failed (recipe=%s, session_id=%s)",
                self.recipe_name, session_id
            )
            return (
                f"Recipe execution failed for '{self.recipe_name}' "
                f"(session_id={session_id})."
            )
    
    async def achat(self, prompt: str, **kwargs) -> str:
        """
        Asynchronous chat with the agent (AgentProtocol compliance).
        
        Args:
            prompt: The user prompt or message
            **kwargs: Additional optional parameters (session_id, etc.)
            
        Returns:
            The agent's response as a string
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.chat, prompt, **kwargs)
    
    async def chat_async(self, message: str) -> str:
        """
        Backward compatibility alias for achat.
        
        Runs the recipe in an executor to avoid blocking the event loop.
        """
        return await self.achat(message)
    
    def inject_context(self, key: str, value: Any, session_id: Optional[str] = None) -> None:
        """
        Inject context variables into the recipe execution.
        
        This enables Human-in-The-Loop capabilities by allowing external
        systems to modify the recipe's context during execution.
        
        Args:
            key: Context variable name
            value: Context variable value
            session_id: Optional session ID for session-specific context
        """
        if session_id:
            if session_id not in self._context_by_session:
                self._context_by_session[session_id] = {}
            # Use copy-on-write to prevent race conditions
            self._context_by_session[session_id] = {
                **self._context_by_session[session_id],
                key: value
            }
        else:
            # Use copy-on-write for default context
            self.context_variables = {**self.context_variables, key: value}
        logger.debug(f"Injected context variable '{key}' into recipe '{self.recipe_name}' (session={session_id or 'default'})")
    
    def clear_context(self, session_id: Optional[str] = None) -> None:
        """Clear context variables for a session or all sessions."""
        if session_id:
            self._context_by_session[session_id] = {}
            logger.debug(f"Cleared context variables for recipe '{self.recipe_name}' (session={session_id})")
        else:
            self.context_variables = {}
            self._context_by_session.clear()
            logger.debug(f"Cleared all context variables for recipe '{self.recipe_name}'")
    
    def get_context(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Get current context variables for a session or default."""
        if session_id:
            session_context = self._context_by_session.get(session_id, {})
            return {**self.context_variables, **session_context}
        return dict(self.context_variables)
    
    def set_recipe_config(self, config: Dict[str, Any]) -> None:
        """Update recipe configuration."""
        self.recipe_config.update(config)
        logger.debug(f"Updated recipe config for '{self.recipe_name}'")
    
    def get_recipe_info(self) -> Dict[str, Any]:
        """Get information about the wrapped recipe."""
        try:
            from praisonai.recipe.core import describe
            recipe_info = describe(self.recipe_name)
            if recipe_info:
                return {
                    "name": recipe_info.name,
                    "version": recipe_info.version,
                    "description": recipe_info.description,
                    "author": recipe_info.author,
                    "tags": recipe_info.tags,
                }
        except Exception:
            logger.debug(
                "Failed to describe recipe (recipe=%s, session_id=%s)",
                self.recipe_name, self.session_id, exc_info=True
            )
        
        return {
            "name": self.recipe_name,
            "version": "unknown",
            "description": f"Recipe adapter for {self.recipe_name}",
            "author": "PraisonAI",
            "tags": ["recipe", "adapter"],
        }
    
    def __str__(self) -> str:
        return f"RecipeBotAdapter(recipe='{self.recipe_name}', session='{self.session_id}')"
    
    def __repr__(self) -> str:
        return (
            f"RecipeBotAdapter("
            f"recipe_name='{self.recipe_name}', "
            f"session_id='{self.session_id}', "
            f"context_vars={len(self.context_variables)}"
            f")"
        )