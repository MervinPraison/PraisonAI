"""
Chat handler mixin for the Agent class.

Contains chat management, response processing, and message formatting.
Extracted from agent.py for better modularity and maintainability.
"""

import logging
import time
from typing import Optional, Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ChatHandlerMixin:
    """Mixin providing chat handling methods for the Agent class.
    
    This mixin focuses on high-level chat coordination and response processing,
    while the actual LLM interaction is handled by ChatMixin.
    """
    
    def _format_chat_response(self, response: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Format chat response with any necessary post-processing.
        
        Args:
            response: Raw response from the LLM
            metadata: Optional metadata about the response
            
        Returns:
            Formatted response string
        """
        if not response:
            return ""
            
        # Basic response formatting - can be extended with additional logic
        formatted = response.strip()
        
        # Add any metadata-based formatting if needed
        if metadata and metadata.get('add_timestamp'):
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            formatted = f"[{timestamp}] {formatted}"
            
        return formatted
    
    def _validate_chat_input(self, prompt: str) -> bool:
        """Validate chat input before processing.
        
        Args:
            prompt: Input prompt to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not prompt or not isinstance(prompt, str):
            logger.warning("Invalid chat input: prompt must be a non-empty string")
            return False
            
        if len(prompt.strip()) == 0:
            logger.warning("Invalid chat input: prompt cannot be empty or whitespace only")
            return False
            
        return True
    
    def _prepare_chat_context(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Prepare context for chat processing.
        
        Args:
            prompt: Input prompt
            **kwargs: Additional context parameters
            
        Returns:
            Context dictionary for chat processing
        """
        context = {
            'prompt': prompt,
            'timestamp': time.time(),
            'agent_name': getattr(self, 'name', None) or 'Agent',
        }
        
        # Add any additional context from kwargs
        context.update(kwargs)
        
        return context
    
    def _handle_chat_error(self, error: Exception, prompt: str) -> str:
        """Handle chat processing errors gracefully.
        
        Args:
            error: The exception that occurred
            prompt: The original prompt that caused the error
            
        Returns:
            Error response message
        """
        logger.error(f"Chat error occurred: {error}", exc_info=True)
        
        # Return a user-friendly error message without exposing internal details.
        # Include a timestamp reference so users can correlate with server logs.
        error_ref = time.strftime('%Y%m%d%H%M%S')
        return f"I encountered an error while processing your request (ref: {error_ref}). Please try again."
    
    def _log_chat_interaction(self, prompt: str, response: str, duration: Optional[float] = None):
        """Log chat interaction for debugging and analytics.
        
        Args:
            prompt: Input prompt
            response: Generated response  
            duration: Processing duration in seconds
        """
        agent_name = getattr(self, 'name', None) or 'Agent'
        duration_str = f" (took {duration:.2f}s)" if duration else ""
        
        logger.debug(f"[{agent_name}] Chat interaction{duration_str}")
        logger.debug(f"[{agent_name}] Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
        logger.debug(f"[{agent_name}] Response: {response[:100]}{'...' if len(response) > 100 else ''}")