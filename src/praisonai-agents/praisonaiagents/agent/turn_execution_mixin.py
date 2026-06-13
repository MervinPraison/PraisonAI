"""
Turn Execution Mixin - implements PreparedTurnContext runtime integration.

This module provides the TurnExecutionMixin that uses PreparedTurnContext
for standardized runtime preparation and execution. It demonstrates how
to refactor existing execution code to use the new turn context pattern.

This serves as an example integration and can be used alongside or to 
replace portions of unified_execution_mixin.py.
"""

import asyncio
import logging
from typing import List, Optional, Any, Dict, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from ..runtime.turn_context import PreparedTurnContext

from ..runtime import (
    PreparedTurnContext,
    default_context_builder,
    RuntimeMode,
    TurnRuntimeProtocol
)

logger = logging.getLogger(__name__)


class TurnExecutionMixin:
    """
    Mixin providing turn-based execution using PreparedTurnContext.
    
    This mixin demonstrates the new execution pattern where context
    is prepared in a single preflight step, then passed to runtimes
    for read-only execution.
    """

    async def _execute_with_prepared_context(
        self,
        prompt: str,
        **kwargs: Any
    ) -> Optional[str]:
        """
        Execute using PreparedTurnContext pattern.
        
        This method demonstrates how to refactor existing execution
        to use the new turn context approach:
        
        1. Build PreparedTurnContext in preflight step
        2. Pass immutable context to runtime for execution
        3. Mutations go through defined hooks only
        
        Args:
            prompt: User prompt for this turn
            **kwargs: Additional execution parameters
            
        Returns:
            Agent response or None if blocked
        """
        try:
            # Step 1: Prepare turn context (replaces scattered preparation)
            context = default_context_builder.build_context(
                agent=self,
                prompt=prompt,
                **kwargs
            )
            
            logger.debug(f"Prepared turn context: {context.to_dict()}")
            
            # Step 2: Apply pre-execution hooks if context allows
            if hasattr(self, '_apply_pre_execution_hooks'):
                context = await self._apply_pre_execution_hooks(context)
            
            # Step 3: Execute using the appropriate runtime
            runtime = self._get_runtime_for_context(context)
            if not runtime.supports_runtime_mode(context.runtime_mode):
                raise ValueError(
                    f"Runtime {type(runtime).__name__} does not support "
                    f"mode {context.runtime_mode.value}"
                )
            
            # Step 4: Run the turn with prepared context
            response = await runtime.run_turn(context)
            
            # Step 5: Apply post-execution hooks if needed
            if hasattr(self, '_apply_post_execution_hooks'):
                response = await self._apply_post_execution_hooks(context, response)
            
            return response
            
        except Exception as e:
            logger.error(f"Turn execution failed: {e}")
            raise

    def _get_runtime_for_context(self, context: PreparedTurnContext) -> TurnRuntimeProtocol:
        """
        Get the appropriate runtime for the prepared context.
        
        This method demonstrates runtime selection based on context
        properties. In practice, this could be more sophisticated
        (e.g., plugin registry, configuration-based selection).
        
        Args:
            context: The prepared turn context
            
        Returns:
            Runtime instance that can execute the context
        """
        # For now, return a default runtime that delegates to existing execution
        return DefaultAgentRuntime(self)

    def chat_with_context(
        self,
        prompt: str,
        **kwargs: Any
    ) -> Optional[str]:
        """
        Sync wrapper for context-based execution.
        
        This provides a sync interface while using the new
        PreparedTurnContext pattern internally.
        
        Args:
            prompt: User prompt
            **kwargs: Additional parameters
            
        Returns:
            Agent response
        """
        # Run the async implementation in sync context
        if hasattr(self, '_is_async_context') and self._is_async_context:
            # We're already in an async context, use existing event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create a task and run it
                task = loop.create_task(self._execute_with_prepared_context(prompt, **kwargs))
                return asyncio.run_coroutine_threadsafe(task, loop).result()
        
        # Run in new event loop
        return asyncio.run(self._execute_with_prepared_context(prompt, **kwargs))

    async def achat_with_context(
        self,
        prompt: str,
        **kwargs: Any
    ) -> Optional[str]:
        """
        Async interface for context-based execution.
        
        Args:
            prompt: User prompt
            **kwargs: Additional parameters
            
        Returns:
            Agent response
        """
        return await self._execute_with_prepared_context(prompt, **kwargs)


class DefaultAgentRuntime:
    """
    Default runtime implementation that delegates to existing Agent methods.
    
    This runtime bridges the new PreparedTurnContext pattern with the
    existing agent execution infrastructure. It demonstrates how to
    create a runtime that uses the prepared context while maintaining
    compatibility with existing code.
    """
    
    def __init__(self, agent):
        self.agent = agent
        self._supported_modes = [
            RuntimeMode.SYNC,
            RuntimeMode.ASYNC,
            RuntimeMode.STREAM,
            RuntimeMode.ASYNC_STREAM
        ]
    
    async def run_turn(self, context: PreparedTurnContext) -> str:
        """
        Execute a turn using the prepared context.
        
        This implementation demonstrates how to use the context
        to drive existing agent execution while eliminating
        scattered preparation logic.
        
        Args:
            context: The prepared turn context
            
        Returns:
            Agent response
        """
        try:
            # Extract prompt from transcript
            user_messages = [
                msg for msg in context.transcript.messages
                if msg.get('role') == 'user'
            ]
            if not user_messages:
                raise ValueError("No user message found in transcript")
            
            prompt = user_messages[-1]['content']
            
            # Use the prepared context to drive execution
            return await self._execute_with_context_data(prompt, context)
            
        except Exception as e:
            logger.error(f"Runtime execution failed: {e}")
            raise

    async def _execute_with_context_data(
        self, 
        prompt: str, 
        context: PreparedTurnContext
    ) -> str:
        """
        Execute using context data instead of scattered preparation.
        
        This method shows how to use the prepared context components
        instead of re-preparing them during execution.
        """
        # Get LLM client (existing pattern)
        llm_client = getattr(self.agent, 'llm_instance', None) or getattr(self.agent, 'llm', None)
        if llm_client is None:
            raise RuntimeError("No LLM client available")
        
        # Use prepared model reference and tools
        model_config = context.model_ref.model_config
        tools = [tool.callable for tool in context.tools if tool.callable is not None]
        
        # Use prepared transcript instead of rebuilding
        chat_history = context.transcript.messages[:-1]  # Exclude current prompt
        system_prompt = context.transcript.system_prompt
        
        # Execute based on runtime mode
        if context.runtime_mode == RuntimeMode.STREAM:
            return await self._execute_streaming(
                llm_client, prompt, system_prompt, chat_history, tools, model_config, context
            )
        else:
            return await self._execute_standard(
                llm_client, prompt, system_prompt, chat_history, tools, model_config, context
            )

    async def _execute_standard(
        self,
        llm_client,
        prompt: str,
        system_prompt: str,
        chat_history: List[Dict[str, Any]],
        tools: List[Any],
        model_config: Dict[str, Any],
        context: PreparedTurnContext
    ) -> str:
        """Execute standard (non-streaming) request."""
        if hasattr(llm_client, 'get_response_async'):
            return await llm_client.get_response_async(
                prompt=prompt,
                system_prompt=system_prompt,
                chat_history=chat_history,
                tools=tools,
                **model_config
            )
        else:
            # Fallback to sync method
            return llm_client.get_response(
                prompt=prompt,
                system_prompt=system_prompt,
                chat_history=chat_history,
                tools=tools,
                **model_config
            )

    async def _execute_streaming(
        self,
        llm_client,
        prompt: str,
        system_prompt: str,
        chat_history: List[Dict[str, Any]],
        tools: List[Any],
        model_config: Dict[str, Any],
        context: PreparedTurnContext
    ) -> str:
        """Execute streaming request using prepared delivery channels."""
        # Use prepared streaming configuration
        if not context.delivery.has_streaming():
            raise ValueError("Streaming requested but no streaming configuration in context")
        
        # Configure streaming with prepared emitter
        model_config['stream'] = True
        
        if hasattr(llm_client, 'get_response_async'):
            response = await llm_client.get_response_async(
                prompt=prompt,
                system_prompt=system_prompt,
                chat_history=chat_history,
                tools=tools,
                **model_config
            )
        else:
            response = llm_client.get_response(
                prompt=prompt,
                system_prompt=system_prompt,
                chat_history=chat_history,
                tools=tools,
                **model_config
            )
        
        return response

    def supports_runtime_mode(self, mode: RuntimeMode) -> bool:
        """Check if this runtime supports the given mode."""
        return mode in self._supported_modes

    def get_supported_modes(self) -> List[RuntimeMode]:
        """Get all supported runtime modes."""
        return self._supported_modes.copy()


class MinimalTurnRuntime:
    """
    Minimal runtime implementation for testing and examples.
    
    This runtime demonstrates the simplest possible implementation
    of the TurnRuntimeProtocol for testing the PreparedTurnContext
    pattern without complex execution logic.
    """
    
    def __init__(self, response_template: str = "Mock response to: {prompt}"):
        self.response_template = response_template
    
    async def run_turn(self, context: PreparedTurnContext) -> str:
        """Execute a minimal turn for testing."""
        # Extract prompt from context
        user_messages = [
            msg for msg in context.transcript.messages
            if msg.get('role') == 'user'
        ]
        prompt = user_messages[-1]['content'] if user_messages else "No prompt"
        
        # Return simple response
        return self.response_template.format(prompt=prompt)
    
    def supports_runtime_mode(self, mode: RuntimeMode) -> bool:
        """Support all modes for testing."""
        return True
    
    def get_supported_modes(self) -> List[RuntimeMode]:
        """Get all supported modes."""
        return list(RuntimeMode)