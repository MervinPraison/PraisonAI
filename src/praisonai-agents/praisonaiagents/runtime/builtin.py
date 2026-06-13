"""
Built-in PraisonAI Runtime Implementation.

Default runtime implementation that provides baseline support for all
provider/model combinations with standard priority for auto-selection.
"""

from typing import Dict, Any
from .protocols import AgentRuntimeProtocol


class PraisonAIRuntime:
    """Default PraisonAI runtime with universal provider/model support.
    
    This is the baseline runtime that handles standard agent execution
    using the existing praisonaiagents framework. It serves as the fallback
    when no specialized runtimes are available.
    """

    def supports(self, provider: str, model: str) -> bool:
        """Universal support for all provider/model combinations."""
        return True

    def selection_priority(self) -> int:
        """Standard priority for built-in runtime."""
        return 50

    async def execute_agent(
        self, 
        config: Dict[str, Any],
        **kwargs
    ) -> Any:
        """Execute agent using standard praisonaiagents framework.
        
        Args:
            config: Agent configuration (model, tools, system, etc.)
            **kwargs: Additional execution parameters
            
        Returns:
            Agent execution result
        """
        # Import here to avoid circular dependency
        from ..agent import Agent
        
        # Extract agent parameters from config
        model = config.get('model')
        system = config.get('system', '')
        tools = config.get('tools', [])
        
        # Create and configure agent
        agent = Agent(
            model=model,
            system=system,
            tools=tools,
            **{k: v for k, v in config.items() 
               if k not in ('model', 'system', 'tools')}
        )
        
        # Execute based on provided parameters
        prompt = kwargs.get('prompt', kwargs.get('messages', ''))
        if prompt:
            return agent.execute(prompt, **kwargs)
        else:
            return agent

    async def cleanup(self) -> None:
        """No cleanup needed for standard runtime."""
        pass

    @property
    def runtime_id(self) -> str:
        """Built-in runtime identifier."""
        return "praisonai"

    @property
    def is_available(self) -> bool:
        """Always available since this is the built-in runtime."""
        return True