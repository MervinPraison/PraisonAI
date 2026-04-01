"""
Execution functionality mixin for Agent class.

This module contains all execution-related methods extracted from the Agent class
for better organization and maintainability.
"""

import asyncio
from typing import Optional, Any, Generator, Union
from praisonaiagents._logging import get_logger

logger = get_logger(__name__)


class ExecutionMixin:
    """
    Mixin class containing all execution-related functionality.
    
    This mixin handles:
    - run() and arun() methods
    - start() and astart() methods  
    - run_until() and run_until_async() methods
    - run_autonomous() and run_autonomous_async() methods
    - Execution flow control
    """
    
    def run(self, prompt: str, **kwargs: Any) -> Optional[str]:
        """
        Run the agent with a prompt.
        
        Args:
            prompt: The input prompt for the agent
            **kwargs: Additional keyword arguments passed to chat()
        
        Returns:
            Agent response as string
        """
        # This method will be implemented by moving the actual implementation from agent.py
        # For now, this is a placeholder to maintain the mixin structure
        raise NotImplementedError("run() method needs to be moved from agent.py")
    
    async def arun(self, prompt: str, **kwargs):
        """
        Async version of run method.
        
        Args:
            prompt: The input prompt for the agent
            **kwargs: Additional keyword arguments
        
        Returns:
            Agent response
        """
        # This method will be implemented by moving the actual implementation from agent.py
        raise NotImplementedError("arun() method needs to be moved from agent.py")
    
    def start(self, prompt: Optional[str] = None, **kwargs: Any) -> Union[str, Generator[str, None, None], None]:
        """
        Start the agent execution.
        
        Args:
            prompt: Optional input prompt
            **kwargs: Additional keyword arguments
            
        Returns:
            Agent response or generator for streaming
        """
        # This method will be implemented by moving the actual implementation from agent.py
        raise NotImplementedError("start() method needs to be moved from agent.py")
    
    async def astart(self, prompt: str, **kwargs):
        """
        Async version of start method.
        
        Args:
            prompt: The input prompt for the agent
            **kwargs: Additional keyword arguments
            
        Returns:
            Agent response
        """
        # This method will be implemented by moving the actual implementation from agent.py
        raise NotImplementedError("astart() method needs to be moved from agent.py")
    
    def run_until(self, condition_func: callable, max_iterations: int = 10, **kwargs) -> Any:
        """
        Run agent until a condition is met.
        
        Args:
            condition_func: Function that returns True when condition is met
            max_iterations: Maximum number of iterations
            **kwargs: Additional arguments
            
        Returns:
            Result when condition is met
        """
        # This method will be implemented by moving the actual implementation from agent.py
        raise NotImplementedError("run_until() method needs to be moved from agent.py")
    
    async def run_until_async(self, condition_func: callable, max_iterations: int = 10, **kwargs) -> Any:
        """
        Async version of run_until.
        
        Args:
            condition_func: Function that returns True when condition is met
            max_iterations: Maximum number of iterations
            **kwargs: Additional arguments
            
        Returns:
            Result when condition is met
        """
        # This method will be implemented by moving the actual implementation from agent.py
        raise NotImplementedError("run_until_async() method needs to be moved from agent.py")
    
    def run_autonomous(self, initial_prompt: str = "", max_iterations: int = 5, **kwargs) -> str:
        """
        Run agent autonomously for multiple iterations.
        
        Args:
            initial_prompt: Starting prompt
            max_iterations: Maximum number of autonomous iterations
            **kwargs: Additional arguments
            
        Returns:
            Final agent response
        """
        # This method will be implemented by moving the actual implementation from agent.py
        raise NotImplementedError("run_autonomous() method needs to be moved from agent.py")
    
    async def run_autonomous_async(self, initial_prompt: str = "", max_iterations: int = 5, **kwargs) -> str:
        """
        Async version of run_autonomous.
        
        Args:
            initial_prompt: Starting prompt
            max_iterations: Maximum number of autonomous iterations
            **kwargs: Additional arguments
            
        Returns:
            Final agent response
        """
        # This method will be implemented by moving the actual implementation from agent.py
        raise NotImplementedError("run_autonomous_async() method needs to be moved from agent.py")