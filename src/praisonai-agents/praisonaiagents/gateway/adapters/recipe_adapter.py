"""
Adapter to wrap a RecipeRuntime behind the standard Agent duck-typing for Gateway and BotOS.
"""

import logging
from typing import Optional, Any
from praisonaiagents.streaming import StreamEventEmitter

logger = logging.getLogger(__name__)

class RecipeBotAdapter:
    """Wraps RecipeRuntime to act like an Agent for gateway/bot compatibility."""
    
    def __init__(self, recipe_name: str, **kwargs):
        self.recipe_name = recipe_name
        self.config = kwargs
        self._runtime = None
        self.stream_emitter = StreamEventEmitter()
    
    @property
    def name(self) -> str:
        return f"recipe-{self.recipe_name}"
        
    def _get_runtime(self):
        """Lazy load and instantiate RecipeRuntime."""
        if self._runtime is None:
            try:
                from praisonai.recipe.core import RecipeRuntime
                self._runtime = RecipeRuntime(recipe_name=self.recipe_name, **self.config)
            except ImportError as e:
                raise ImportError(
                    f"Failed to load PraisonAI recipe components: {e}. "
                    "Make sure you have praisonai installed."
                ) from e
        return self._runtime
        
    def chat(self, message: str) -> str:
        """Process the message via the recipe runtime."""
        try:
            runtime = self._get_runtime()
            
            # Forward the user_input to the recipe's variables
            variables = runtime.context.variables if hasattr(runtime, 'context') else {}
            variables["user_input"] = message
            
            # Currently we rely on string return matching standard Agent
            # Note: We don't have direct streaming from recipe to emitter yet; this binds them generically.
            result = runtime.run()
            
            if hasattr(result, "final_output"):
                return str(result.final_output)
            return str(result)
            
        except Exception as e:
            logger.error(f"Recipe execution failed: {e}")
            return f"Error executing recipe: {e}"
