"""
Clarify Tool for PraisonAI Agents.

Allows agents to ask clarifying questions when they need more information
to proceed with a task. The tool pauses execution and waits for user input.

This is a first-class tool that integrates with different contexts:
- CLI: Uses stdin prompt
- Bot: Sends message and waits for reply
- UI: Uses interactive components
"""

import logging
from typing import Optional, List, Any, Dict, Callable

from .base import BaseTool

logger = logging.getLogger(__name__)


class ClarifyHandler:
    """Handler for clarify requests in different contexts."""
    
    def __init__(self, ask_callback: Optional[Callable[[str, Optional[List[str]]], str]] = None):
        self.ask_callback = ask_callback
    
    async def ask(self, question: str, choices: Optional[List[str]] = None) -> str:
        """Ask a clarifying question and wait for response.
        
        Args:
            question: The question to ask the user
            choices: Optional list of predefined choices
            
        Returns:
            User's response
        """
        if self.ask_callback:
            try:
                result = self.ask_callback(question, choices)
                # Handle both sync and async callbacks
                if hasattr(result, '__await__'):
                    return await result
                return result
            except Exception as e:
                logger.warning(f"Clarify handler callback failed: {e}")
                
        # Fallback: return instruction to proceed with best guess
        return f"No interactive channel available. Please proceed with your best judgment for: {question}"


class ClarifyTool(BaseTool):
    """Tool that allows agents to ask clarifying questions.
    
    This tool pauses the agent's execution and requests input from the user
    through the appropriate channel (CLI, bot, UI, etc.).
    """
    
    name = "clarify"
    description = (
        "Ask the user a focused clarifying question when genuinely ambiguous. "
        "Use sparingly - only when you cannot proceed without their input."
    )
    
    def __init__(self, handler: Optional[ClarifyHandler] = None):
        super().__init__()
        self.handler = handler or ClarifyHandler()
    
    async def run(
        self, 
        question: str,
        choices: Optional[List[str]] = None,
        **kwargs
    ) -> str:
        """Ask a clarifying question and return the user's response.
        
        Args:
            question: The question to ask
            choices: Optional list of predefined choices
            **kwargs: Additional context (may contain 'ctx' with agent context)
            
        Returns:
            User's response or fallback instruction
        """
        logger.debug(f"Clarify tool asking: {question}")
        
        # Check if there's a clarify handler in the context
        ctx = kwargs.get('ctx')
        if ctx and hasattr(ctx, 'get'):
            context_handler = ctx.get('clarify_handler')
            if context_handler:
                if hasattr(context_handler, 'ask'):
                    return await context_handler.ask(question, choices)
                elif callable(context_handler):
                    result = context_handler(question, choices)
                    if hasattr(result, '__await__'):
                        return await result
                    return result
        
        # Use the tool's handler
        return await self.handler.ask(question, choices)
    
    def get_schema(self) -> Dict[str, Any]:
        """Get OpenAI-compatible schema for this tool."""
        schema = super().get_schema()
        
        # Customize the schema to include choices parameter
        schema["function"]["parameters"]["properties"]["choices"] = {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional list of predefined answer choices"
        }
        
        return schema


# Create a default instance for easy import
clarify = ClarifyTool()


def create_cli_clarify_handler() -> ClarifyHandler:
    """Create a clarify handler for CLI usage."""
    
    def cli_ask(question: str, choices: Optional[List[str]] = None) -> str:
        """CLI implementation of clarify asking."""
        print(f"\n🤔 {question}")
        
        if choices:
            print("\nChoices:")
            for i, choice in enumerate(choices, 1):
                print(f"  {i}. {choice}")
            print()
            
            while True:
                try:
                    response = input("Your choice (number or text): ").strip()
                    
                    # Check if it's a number choice
                    if response.isdigit():
                        idx = int(response) - 1
                        if 0 <= idx < len(choices):
                            return choices[idx]
                        else:
                            print(f"Please enter a number between 1 and {len(choices)}")
                            continue
                    
                    # Return the raw response
                    return response
                    
                except KeyboardInterrupt:
                    return "skip"
                except EOFError:
                    return "skip"
        else:
            try:
                response = input("Your answer: ").strip()
                return response or "no answer provided"
            except (KeyboardInterrupt, EOFError):
                return "skip"
    
    return ClarifyHandler(ask_callback=cli_ask)


def create_bot_clarify_handler(send_message_fn: Callable, wait_for_reply_fn: Callable) -> ClarifyHandler:
    """Create a clarify handler for bot usage.
    
    Args:
        send_message_fn: Function to send a message to the user
        wait_for_reply_fn: Function to wait for user reply
    """
    
    async def bot_ask(question: str, choices: Optional[List[str]] = None) -> str:
        """Bot implementation of clarify asking."""
        formatted_question = f"🤔 {question}"
        
        if choices:
            formatted_question += "\n\nChoices:\n"
            for i, choice in enumerate(choices, 1):
                formatted_question += f"  {i}. {choice}\n"
        
        await send_message_fn(formatted_question)
        response = await wait_for_reply_fn()
        
        # Handle choice selection for bots
        if choices and response.isdigit():
            try:
                idx = int(response) - 1
                if 0 <= idx < len(choices):
                    return choices[idx]
            except ValueError:
                pass
        
        return response or "no answer provided"
    
    return ClarifyHandler(ask_callback=bot_ask)


# Export the tool for registration
__all__ = ['clarify', 'ClarifyTool', 'ClarifyHandler', 'create_cli_clarify_handler', 'create_bot_clarify_handler']