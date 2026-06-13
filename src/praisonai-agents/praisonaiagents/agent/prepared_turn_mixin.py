"""
Prepared Turn Mixin for Agent class.

This mixin provides the integration between the existing Agent class
and the new PreparedTurnContext pattern. It demonstrates how to refactor
existing execution methods to use the new standardized runtime approach.

This mixin can be added to the Agent class to provide backward-compatible
methods that use PreparedTurnContext internally while maintaining the
existing API surface.
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
)

logger = logging.getLogger(__name__)


class PreparedTurnMixin:
    """
    Mixin that adds PreparedTurnContext support to Agent class.
    
    This mixin demonstrates the integration path for existing agents
    to use the new turn context pattern while maintaining backward
    compatibility with existing APIs.
    
    Usage:
        class Agent(PreparedTurnMixin, ChatMixin, ...):
            # existing implementation
            pass
            
        # New context-aware methods:
        agent = Agent(...)
        context = agent.prepare_turn_context("Hello", temperature=0.7)
        response = await agent.execute_prepared_turn(context)
        
        # Or use the integrated chat method:
        response = agent.chat_with_prepared_context("Hello", temperature=0.7)
    """

    def prepare_turn_context(
        self,
        prompt: str,
        **kwargs: Any
    ) -> PreparedTurnContext:
        """
        Prepare a turn context for execution.
        
        This method creates a PreparedTurnContext that captures all the
        configuration needed for a single agent turn. The context can
        then be passed to runtimes or used for inspection/debugging.
        
        Args:
            prompt: User prompt for this turn
            **kwargs: Additional execution parameters including:
                - model: Override model ID  
                - tools: Override tools list
                - stream: Enable streaming
                - temperature: Model temperature
                - max_tokens: Token limit
                - session_id: Session identifier
                
        Returns:
            PreparedTurnContext ready for execution
            
        Example:
            ```python
            agent = Agent(name="helper", model="gpt-4")
            context = agent.prepare_turn_context(
                "What's the weather?",
                temperature=0.7,
                stream=True
            )
            
            # Inspect the prepared context
            print(f"Model: {context.model_ref.model_id}")
            print(f"Tools: {len(context.tools)}")
            print(f"Mode: {context.runtime_mode}")
            ```
        """
        logger.debug(f"Preparing turn context for agent {getattr(self, 'name', 'Unknown')}")
        
        try:
            context = default_context_builder.build_context(
                agent=self,
                prompt=prompt,
                **kwargs
            )
            
            logger.debug(
                f"Prepared context: {context.get_message_count()} messages, "
                f"{len(context.tools)} tools, {context.runtime_mode.value} mode"
            )
            
            return context
            
        except Exception as e:
            logger.error(f"Failed to prepare turn context: {e}")
            raise

    async def execute_prepared_turn(
        self, 
        context: PreparedTurnContext
    ) -> str:
        """
        Execute a prepared turn context.
        
        This method takes a PreparedTurnContext and executes it using
        the appropriate runtime. It demonstrates how prepared contexts
        eliminate the need for scattered configuration gathering.
        
        Args:
            context: The prepared turn context to execute
            
        Returns:
            Agent response text
            
        Example:
            ```python
            # Prepare context
            context = agent.prepare_turn_context("Hello")
            
            # Execute later (possibly in different context)
            response = await agent.execute_prepared_turn(context)
            ```
        """
        logger.debug(f"Executing prepared turn {context.correlation.turn_id}")
        
        try:
            # Get the runtime for this context
            runtime = self._get_runtime_for_prepared_context(context)
            
            # Validate runtime supports the context mode
            if not runtime.supports_runtime_mode(context.runtime_mode):
                raise ValueError(
                    f"Runtime does not support mode {context.runtime_mode.value}"
                )
            
            # Execute the turn
            response = await runtime.run_turn(context)
            
            # Update agent state with response (maintain existing behavior)
            await self._post_turn_processing(context, response)
            
            return response
            
        except Exception as e:
            logger.error(f"Failed to execute prepared turn: {e}")
            raise

    def chat_with_prepared_context(
        self,
        prompt: str,
        **kwargs: Any
    ) -> str:
        """
        Sync chat using PreparedTurnContext pattern.
        
        This method provides a backward-compatible sync interface that
        uses the new PreparedTurnContext pattern internally. It can
        serve as a drop-in replacement for existing chat() methods.
        
        Args:
            prompt: User prompt
            **kwargs: Execution parameters
            
        Returns:
            Agent response
            
        Example:
            ```python
            # Drop-in replacement for agent.chat()
            response = agent.chat_with_prepared_context(
                "Hello", 
                temperature=0.7,
                stream=True
            )
            ```
        """
        # Prepare context in one step
        context = self.prepare_turn_context(prompt, **kwargs)
        
        # Execute synchronously
        if hasattr(self, '_execute_sync'):
            return self._execute_sync(context)
        else:
            # Fallback to asyncio.run
            return asyncio.run(self.execute_prepared_turn(context))

    async def achat_with_prepared_context(
        self,
        prompt: str, 
        **kwargs: Any
    ) -> str:
        """
        Async chat using PreparedTurnContext pattern.
        
        Args:
            prompt: User prompt
            **kwargs: Execution parameters
            
        Returns:
            Agent response
        """
        # Prepare context in one step  
        context = self.prepare_turn_context(prompt, **kwargs)
        
        # Execute asynchronously
        return await self.execute_prepared_turn(context)

    def _get_runtime_for_prepared_context(
        self, 
        context: PreparedTurnContext
    ) -> Any:
        """
        Get the appropriate runtime for the prepared context.
        
        This method demonstrates runtime selection based on context
        properties. In practice, this could integrate with the existing
        execution infrastructure or plugin systems.
        
        Args:
            context: The prepared turn context
            
        Returns:
            Runtime instance that can execute the context
        """
        # For now, use a bridge runtime that delegates to existing methods
        return PreparedTurnBridgeRuntime(self)

    async def _post_turn_processing(
        self,
        context: PreparedTurnContext,
        response: str
    ) -> None:
        """
        Process results after turn execution.
        
        This method maintains existing agent behavior like updating
        chat history, memory storage, etc. while working with the
        new context pattern.
        
        Args:
            context: The executed turn context
            response: The response that was generated
        """
        # Update chat history (maintain existing behavior)
        if hasattr(self, 'chat_history'):
            # Extract original prompt from context
            user_messages = [
                msg for msg in context.transcript.messages
                if msg.get('role') == 'user'
            ]
            if user_messages:
                prompt = user_messages[-1]['content']
                
                # Add to chat history if not already there
                if not self.chat_history or self.chat_history[-1].get('content') != prompt:
                    self.chat_history.append({'role': 'user', 'content': prompt})
                
                # Add response
                self.chat_history.append({'role': 'assistant', 'content': response})

        # Store in memory if enabled
        if hasattr(self, '_memory_instance') and self._memory_instance and response:
            try:
                user_messages = [
                    msg for msg in context.transcript.messages
                    if msg.get('role') == 'user'
                ]
                if user_messages:
                    prompt = user_messages[-1]['content']
                    self._memory_instance.store_short_term(
                        f"User: {prompt}\nAssistant: {response}",
                        metadata={
                            "agent_id": getattr(self, 'agent_id', self.name),
                            "turn_id": context.correlation.turn_id,
                            "session_id": context.correlation.session_id
                        }
                    )
            except Exception as e:
                logger.warning(f"Failed to store interaction in memory: {e}")


class PreparedTurnBridgeRuntime:
    """
    Bridge runtime that integrates PreparedTurnContext with existing Agent methods.
    
    This runtime demonstrates how to use prepared contexts while delegating
    to existing agent execution infrastructure. It serves as a compatibility
    layer during the transition to the new pattern.
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
        Execute a turn using existing agent infrastructure.
        
        This method bridges the new PreparedTurnContext pattern with
        existing agent execution methods, demonstrating backward
        compatibility during transition.
        
        Args:
            context: The prepared turn context
            
        Returns:
            Agent response
        """
        try:
            # Extract execution parameters from context
            execution_params = self._extract_execution_params(context)
            
            # Use existing agent execution method
            if hasattr(self.agent, '_unified_chat_impl'):
                # Use unified execution if available
                response = await self.agent._unified_chat_impl(**execution_params)
            elif hasattr(self.agent, 'get_response_async'):
                # Use LLM client directly
                llm_client = getattr(self.agent, 'llm_instance', None) or getattr(self.agent, 'llm', None)
                if llm_client:
                    response = await llm_client.get_response_async(**execution_params)
                else:
                    raise RuntimeError("No LLM client available")
            else:
                # Fallback to sync method
                if hasattr(self.agent, 'chat'):
                    prompt = execution_params.get('prompt', '')
                    response = self.agent.chat(prompt, **execution_params)
                else:
                    raise RuntimeError("No execution method available")
            
            return response or ""
            
        except Exception as e:
            logger.error(f"Bridge runtime execution failed: {e}")
            raise

    def _extract_execution_params(self, context: PreparedTurnContext) -> Dict[str, Any]:
        """
        Extract execution parameters from PreparedTurnContext.
        
        This method demonstrates how to convert the prepared context
        back to the parameters expected by existing execution methods.
        
        Args:
            context: The prepared turn context
            
        Returns:
            Dictionary of parameters for existing execution methods
        """
        # Extract prompt from transcript
        user_messages = [
            msg for msg in context.transcript.messages
            if msg.get('role') == 'user'
        ]
        prompt = user_messages[-1]['content'] if user_messages else ""
        
        # Extract tools
        tools = [tool.callable for tool in context.tools if tool.callable is not None]
        if not tools:
            tools = None  # Let existing method use default tools
        
        # Build parameters dictionary
        params = {
            'prompt': prompt,
            'tools': tools,
            'stream': context.delivery.enable_streaming,
            **context.model_ref.model_config  # Include temperature, max_tokens, etc.
        }
        
        # Add system prompt to chat history for existing methods
        if context.transcript.system_prompt and hasattr(self.agent, 'chat_history'):
            # Temporarily modify agent's system behavior
            original_system = getattr(self.agent, 'use_system_prompt', True)
            params['system_prompt'] = context.transcript.system_prompt
            
        # Add chat history
        chat_history = [msg for msg in context.transcript.messages if msg.get('role') != 'user']
        if chat_history:
            params['chat_history'] = chat_history
        
        return params

    def supports_runtime_mode(self, mode: RuntimeMode) -> bool:
        """Check if this runtime supports the given mode."""
        return mode in self._supported_modes

    def get_supported_modes(self) -> List[RuntimeMode]:
        """Get all supported runtime modes."""
        return self._supported_modes.copy()