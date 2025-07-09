"""Callback management for display and approval operations.

This module provides a centralized callback system for registering and executing
both synchronous and asynchronous callbacks for various events in the PraisonAI
agents system.
"""

import asyncio
from typing import Dict, Callable, Any, Optional

# Separate registries for sync and async callbacks
sync_display_callbacks: Dict[str, Callable] = {}
async_display_callbacks: Dict[str, Callable] = {}

# Global approval callback registry
approval_callback: Optional[Callable] = None


def register_display_callback(display_type: str, callback_fn: Callable, is_async: bool = False):
    """Register a synchronous or asynchronous callback function for a specific display type.
    
    Display types include:
    - 'interaction': User/task and agent response interactions
    - 'self_reflection': Agent self-reflection messages
    - 'instruction': Instructions with agent information
    - 'tool_call': Tool execution information
    - 'error': Error messages
    - 'generating': Content being generated
    
    Args:
        display_type: Type of display event to register for
        callback_fn: The callback function to register
        is_async: Whether the callback is asynchronous
    """
    if is_async:
        async_display_callbacks[display_type] = callback_fn
    else:
        sync_display_callbacks[display_type] = callback_fn


def register_approval_callback(callback_fn: Callable):
    """Register a global approval callback function for dangerous tool operations.
    
    The callback function should accept:
    - function_name: Name of the function/tool being called
    - arguments: Arguments to be passed to the function
    - risk_level: Risk level of the operation
    
    And return an ApprovalDecision object with:
    - approved: bool indicating if operation is approved
    - explanation: Optional explanation for the decision
    - modified_args: Optional modified arguments
    
    Args:
        callback_fn: Function that takes (function_name, arguments, risk_level) and returns ApprovalDecision
    """
    global approval_callback
    approval_callback = callback_fn


async def execute_callback(display_type: str, **kwargs):
    """Execute both sync and async callbacks for a given display type.
    
    This function handles the execution of registered callbacks, running
    synchronous callbacks in a thread pool executor to avoid blocking
    the event loop, and running async callbacks directly.
    
    Args:
        display_type: Type of display event
        **kwargs: Arguments to pass to the callback functions
    """
    # Execute synchronous callback if registered
    if display_type in sync_display_callbacks:
        callback = sync_display_callbacks[display_type]
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: callback(**kwargs))
    
    # Execute asynchronous callback if registered
    if display_type in async_display_callbacks:
        callback = async_display_callbacks[display_type]
        await callback(**kwargs)


def clear_callbacks(display_type: Optional[str] = None):
    """Clear registered callbacks.
    
    Args:
        display_type: Specific display type to clear, or None to clear all
    """
    if display_type:
        sync_display_callbacks.pop(display_type, None)
        async_display_callbacks.pop(display_type, None)
    else:
        sync_display_callbacks.clear()
        async_display_callbacks.clear()


def get_registered_callbacks() -> Dict[str, Dict[str, Any]]:
    """Get information about all registered callbacks.
    
    Returns:
        Dictionary with sync and async callback information
    """
    return {
        'sync': {k: v.__name__ if hasattr(v, '__name__') else str(v) 
                 for k, v in sync_display_callbacks.items()},
        'async': {k: v.__name__ if hasattr(v, '__name__') else str(v) 
                  for k, v in async_display_callbacks.items()},
        'approval': approval_callback.__name__ if approval_callback and hasattr(approval_callback, '__name__') 
                    else str(approval_callback) if approval_callback else None
    }


# Export all callback-related functions and registries
__all__ = [
    'register_display_callback',
    'register_approval_callback',
    'execute_callback',
    'clear_callbacks',
    'get_registered_callbacks',
    'sync_display_callbacks',
    'async_display_callbacks',
    'approval_callback',
]