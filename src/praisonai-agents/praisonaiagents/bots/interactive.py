"""
Interactive action dispatch system for messaging bots.

Provides a registry and dispatch protocol for handling callbacks from
interactive UI elements (buttons, select menus) across all messaging platforms.
This complements the presentation.py render side with symmetric inbound handling.

This is a core protocol with no heavy implementations - channel-specific
callback decoding belongs in the wrapper (praisonai).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .presentation import PresentationAction
    from .protocols import BotAdapter, BotMessage

logger = logging.getLogger(__name__)


@dataclass
class InteractiveContext:
    """Context for interactive callback handling.
    
    Attributes:
        callback_data: Raw callback data from the platform
        user_id: ID of the user who triggered the action
        message_id: ID of the message containing the interactive element
        chat_id: ID of the chat where the action was triggered
        bot_adapter: The bot adapter handling this interaction
        platform_data: Platform-specific additional data
    """
    
    callback_data: str
    user_id: str
    message_id: Optional[str] = None
    chat_id: Optional[str] = None
    bot_adapter: Optional["BotAdapter"] = None
    platform_data: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.platform_data is None:
            self.platform_data = {}


InteractiveHandler = Callable[[InteractiveContext], Awaitable[Optional[str]]]


def encode_action(namespace: str, action: "PresentationAction") -> str:
    """Encode an action with namespace for callback data.
    
    Args:
        namespace: The namespace for this action handler
        action: The presentation action to encode
        
    Returns:
        Encoded callback data string
    """
    from .presentation import ActionType
    
    if action.type == ActionType.CALLBACK:
        # For callback type, encode namespace with the value
        if action.value:
            return f"{namespace}:{action.value}"
        return namespace
    elif action.type == ActionType.COMMAND:
        # For command type, use cmd: prefix
        if action.command:
            return f"cmd:{action.command}"
        return namespace
    else:
        # URL and web_app types don't need encoding
        return namespace


def decode_callback(data: str) -> Tuple[str, Dict[str, Any]]:
    """Decode callback data into namespace and payload.
    
    Args:
        data: Raw callback data string
        
    Returns:
        Tuple of (namespace, payload_dict)
    """
    if not data:
        return ("unknown", {})
    
    # Handle command callbacks (cmd:)
    if data.startswith("cmd:"):
        command = data[4:]
        return ("command", {"command": command})
    
    # Handle namespaced callbacks (namespace:payload)
    if ":" in data:
        parts = data.split(":", 1)
        namespace = parts[0]
        payload = parts[1] if len(parts) > 1 else ""
        return (namespace, {"value": payload})
    
    # Plain data without namespace
    return (data, {})


class InteractiveRegistry:
    """Registry for interactive callback handlers.
    
    Manages registration and dispatch of handlers for different
    callback namespaces. Each namespace can have one handler.
    """
    
    def __init__(self):
        """Initialize the registry."""
        self._handlers: Dict[str, InteractiveHandler] = {}
        self._fallback_handler: Optional[InteractiveHandler] = None
    
    def register(
        self,
        namespace: str,
        handler: InteractiveHandler
    ) -> None:
        """Register a handler for a namespace.
        
        Args:
            namespace: The namespace to handle (e.g., "approval", "menu")
            handler: Async function to handle callbacks in this namespace
        """
        if namespace in self._handlers:
            logger.warning(f"Overwriting existing handler for namespace: {namespace}")
        self._handlers[namespace] = handler
        logger.debug(f"Registered handler for namespace: {namespace}")
    
    def unregister(self, namespace: str) -> None:
        """Unregister a handler.
        
        Args:
            namespace: The namespace to unregister
        """
        if namespace in self._handlers:
            del self._handlers[namespace]
            logger.debug(f"Unregistered handler for namespace: {namespace}")
    
    def set_fallback(self, handler: InteractiveHandler) -> None:
        """Set a fallback handler for unmatched callbacks.
        
        Args:
            handler: Async function to handle unmatched callbacks
        """
        self._fallback_handler = handler
    
    async def dispatch(self, context: InteractiveContext) -> bool:
        """Dispatch a callback to the appropriate handler.
        
        Args:
            context: The interactive context
            
        Returns:
            True if handled, False otherwise
        """
        namespace, payload = decode_callback(context.callback_data)
        
        # Try to find a handler for this namespace
        handler = self._handlers.get(namespace)
        
        if handler:
            try:
                # Add decoded payload to context
                context.platform_data["decoded_namespace"] = namespace
                context.platform_data["decoded_payload"] = payload
                
                result = await handler(context)
                if result:
                    logger.debug(f"Handler for namespace '{namespace}' returned: {result}")
                return True
            except Exception as e:
                logger.error(f"Error in handler for namespace '{namespace}': {e}")
                return False
        
        # Try fallback handler
        if self._fallback_handler:
            try:
                context.platform_data["decoded_namespace"] = namespace
                context.platform_data["decoded_payload"] = payload
                
                result = await self._fallback_handler(context)
                if result:
                    logger.debug(f"Fallback handler returned: {result}")
                return True
            except Exception as e:
                logger.error(f"Error in fallback handler: {e}")
                return False
        
        logger.debug(f"No handler found for namespace: {namespace}")
        return False
    
    def has_handler(self, namespace: str) -> bool:
        """Check if a namespace has a registered handler.
        
        Args:
            namespace: The namespace to check
            
        Returns:
            True if handler exists
        """
        return namespace in self._handlers
    
    def list_namespaces(self) -> list[str]:
        """List all registered namespaces.
        
        Returns:
            List of namespace names
        """
        return list(self._handlers.keys())


# Global registry instance
_global_registry = InteractiveRegistry()


def get_registry() -> InteractiveRegistry:
    """Get the global interactive registry.
    
    Returns:
        The global InteractiveRegistry instance
    """
    return _global_registry


def register_handler(namespace: str, handler: InteractiveHandler) -> None:
    """Register a handler in the global registry.
    
    Args:
        namespace: The namespace to handle
        handler: Async function to handle callbacks
    """
    _global_registry.register(namespace, handler)


def unregister_handler(namespace: str) -> None:
    """Unregister a handler from the global registry.
    
    Args:
        namespace: The namespace to unregister
    """
    _global_registry.unregister(namespace)