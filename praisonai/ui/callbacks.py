import logging
from typing import Dict, Any, Callable, Optional, Union
import asyncio

logger = logging.getLogger(__name__)

class CallbackManager:
    """Manages callbacks for the PraisonAI UI"""
    
    def __init__(self):
        self._callbacks: Dict[str, Dict[str, Union[Callable, bool]]] = {}
    
    def register(self, name: str, callback: Callable, is_async: bool = False) -> None:
        """Register a callback function"""
        self._callbacks[name] = {
            'func': callback,
            'is_async': is_async
        }
    
    async def call(self, name: str, **kwargs) -> None:
        """Call a registered callback"""
        if name not in self._callbacks:
            logger.warning(f"No callback registered for {name}")
            return
            
        callback_info = self._callbacks[name]
        func = callback_info['func']
        is_async = callback_info['is_async']
        
        try:
            if is_async:
                await func(**kwargs)
            else:
                if asyncio.iscoroutinefunction(func):
                    await func(**kwargs)
                else:
                    await asyncio.get_event_loop().run_in_executor(None, lambda: func(**kwargs))
        except Exception as e:
            logger.error(f"Error in callback {name}: {str(e)}")

# Global callback manager instance
callback_manager = CallbackManager()

def register_callback(name: str, callback: Callable, is_async: bool = False) -> None:
    """Register a callback with the global callback manager"""
    callback_manager.register(name, callback, is_async)

async def trigger_callback(name: str, **kwargs) -> None:
    """Trigger a callback from the global callback manager"""
    await callback_manager.call(name, **kwargs)

# Decorator for registering callbacks
def callback(name: str, is_async: bool = False):
    def decorator(func):
        register_callback(name, func, is_async)
        return func
    return decorator 