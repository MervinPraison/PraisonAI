"""
Context Builder for PreparedTurnContext.

This module provides the DefaultTurnContextBuilder that prepares
PreparedTurnContext instances from agent configuration and request
parameters. It consolidates the scattered context preparation logic
from chat_mixin.py, chat_handler.py, and other execution paths.
"""

from __future__ import annotations

import copy
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .turn_context import (
    PreparedTurnContext,
    ModelReference, 
    ToolSchema,
    TranscriptWindow,
    DeliveryChannels,
    SessionCorrelation,
    RuntimeMode,
)
from .protocols import TurnContextBuilderProtocol

if TYPE_CHECKING:
    from ..agent.protocols import AgentProtocol
    from ..streaming.events import StreamEventEmitter

logger = logging.getLogger(__name__)


class DefaultTurnContextBuilder:
    """
    Default implementation of turn context building.
    
    This builder extracts and normalizes configuration from Agent instances
    to create PreparedTurnContext objects. It consolidates the logic that
    was previously scattered across multiple mixins.
    """
    
    def __init__(self):
        self._cache: Dict[str, Any] = {}
    
    def build_context(
        self,
        agent: AgentProtocol,
        prompt: str,
        **kwargs: Any
    ) -> PreparedTurnContext:
        """
        Build a prepared turn context from agent and request.
        
        Args:
            agent: The agent instance
            prompt: The user prompt for this turn
            **kwargs: Additional request parameters including:
                - model: Override model ID
                - tools: Override tools list. Omit or pass None to use
                  agent.tools. Pass [] to explicitly disable tools for this turn.
                - stream: Enable streaming
                - temperature: Model temperature
                - max_tokens: Token limit
                - session_id: Session identifier
                - turn_id: Turn identifier
                
        Returns:
            A prepared turn context ready for execution
        """
        try:
            # Extract runtime mode from kwargs
            runtime_mode = self._determine_runtime_mode(kwargs)
            
            # Build model reference
            model_ref = self._build_model_reference(agent, kwargs)
            
            # Normalize tools
            tools = self._build_tool_schemas(agent, kwargs)
            
            # Build transcript window
            transcript = self._build_transcript_window(agent, prompt, kwargs)
            
            # Setup delivery channels
            delivery = self._build_delivery_channels(agent, kwargs)
            
            # Create correlation IDs
            correlation = self._build_session_correlation(agent, kwargs)
            
            # Create the context
            context = PreparedTurnContext(
                model_ref=model_ref,
                agent_runtime=agent,
                tools=tools,
                transcript=transcript,
                delivery=delivery,
                correlation=correlation,
                runtime_mode=runtime_mode,
                turn_metadata=self._extract_turn_metadata(agent, kwargs),
                created_at=time.time()
            )
            
            logger.debug(
                f"Built turn context: {context.get_message_count()} messages, "
                f"{len(context.tools)} tools, mode={context.runtime_mode.value}"
            )
            
            return context
            
        except Exception as e:
            logger.error(f"Failed to build turn context: {e}")
            raise
    
    def _determine_runtime_mode(self, kwargs: Dict[str, Any]) -> RuntimeMode:
        """Determine runtime mode from request parameters."""
        is_stream = kwargs.get('stream', False)
        is_async = kwargs.get('async_execution', False)
        
        if is_async and is_stream:
            return RuntimeMode.ASYNC_STREAM
        elif is_async:
            return RuntimeMode.ASYNC
        elif is_stream:
            return RuntimeMode.STREAM
        else:
            return RuntimeMode.SYNC
    
    def _build_model_reference(
        self, 
        agent: AgentProtocol, 
        kwargs: Dict[str, Any]
    ) -> ModelReference:
        """Build model reference from agent configuration and overrides."""
        # Get model ID (kwargs override, then agent default)
        model_id = kwargs.get('model') or getattr(agent, 'model', 'gpt-3.5-turbo')
        
        # Determine provider from model ID or agent config
        provider = self._determine_provider(model_id, agent)
        
        # Get model capabilities
        supports_streaming = kwargs.get('stream', False) or getattr(agent, '_supports_streaming', True)
        supports_tools = len(getattr(agent, 'tools', [])) > 0
        supports_system_prompts = getattr(agent, 'use_system_prompt', True)
        
        # Build model config - agent defaults first, kwargs override
        model_config = {}
        if hasattr(agent, 'model_config'):
            model_config.update(agent.model_config)
        if 'temperature' in kwargs:
            model_config['temperature'] = kwargs['temperature']
        if 'max_tokens' in kwargs:
            model_config['max_tokens'] = kwargs['max_tokens']
        
        return ModelReference(
            model_id=model_id,
            provider=provider,
            supports_streaming=supports_streaming,
            supports_tools=supports_tools,
            supports_system_prompts=supports_system_prompts,
            max_tokens=kwargs.get('max_tokens'),
            temperature=kwargs.get('temperature'),
            model_config=model_config
        )
    
    def _determine_provider(self, model_id: str, agent: AgentProtocol) -> str:
        """Determine provider from model ID or agent configuration."""
        # Check if agent has explicit provider
        if hasattr(agent, 'provider'):
            return agent.provider
        
        # Infer from model ID
        if model_id.startswith('gpt-'):
            return 'openai'
        elif model_id.startswith('claude-'):
            return 'anthropic'
        elif model_id.startswith('gemini-'):
            return 'google'
        elif 'llama' in model_id.lower():
            return 'meta'
        else:
            return 'openai'  # Default fallback
    
    def _build_tool_schemas(
        self,
        agent: AgentProtocol,
        kwargs: Dict[str, Any]
    ) -> List[ToolSchema]:
        """Build normalized tool schemas from agent tools.

        Tool resolution semantics:
            - ``tools`` omitted or ``tools=None`` -> use ``agent.tools``.
            - ``tools=[]`` -> explicitly disable tools for this turn.
            - ``tools=[...]`` -> override agent tools with the given list.
        """
        # Get tools from kwargs override or agent.
        # Treat a missing key and an explicit None identically (use agent tools),
        # while still respecting an explicit empty list as a deliberate override.
        if kwargs.get('tools') is not None:
            raw_tools = kwargs['tools']
        else:
            raw_tools = getattr(agent, 'tools', []) or []
        
        if not raw_tools:
            return []
        
        normalized_tools = []
        for tool in raw_tools:
            try:
                schema = self._normalize_tool_schema(tool)
                if schema:
                    normalized_tools.append(schema)
            except Exception as e:
                logger.warning(f"Failed to normalize tool {tool}: {e}")
                continue
        
        return normalized_tools
    
    def _normalize_tool_schema(self, tool: Any) -> Optional[ToolSchema]:
        """Normalize a single tool into ToolSchema format."""
        if tool is None:
            return None
        
        # Handle different tool formats
        if callable(tool):
            # Function tool
            return self._normalize_function_tool(tool)
        elif isinstance(tool, dict):
            # Dictionary tool (OpenAI format, custom format, etc.)
            return self._normalize_dict_tool(tool)
        elif hasattr(tool, 'name') and hasattr(tool, 'description'):
            # Object with name/description attributes
            return self._normalize_object_tool(tool)
        else:
            logger.warning(f"Unknown tool format: {type(tool)}")
            return None
    
    def _normalize_function_tool(self, func: callable) -> ToolSchema:
        """Normalize a callable function into ToolSchema."""
        import inspect
        
        name = getattr(func, '__name__', 'unknown_function')
        description = getattr(func, '__doc__', '') or f"Function: {name}"
        
        # Try to extract parameters from function signature
        try:
            sig = inspect.signature(func)
            parameters = {
                "type": "object",
                "properties": {},
                "required": []
            }
            
            for param_name, param in sig.parameters.items():
                if param_name == 'self':
                    continue
                    
                prop = {"type": "string"}  # Default type
                if param.annotation != inspect.Parameter.empty:
                    prop["type"] = self._python_type_to_json_type(param.annotation)
                    
                parameters["properties"][param_name] = prop
                
                if param.default == inspect.Parameter.empty:
                    parameters["required"].append(param_name)
            
        except Exception:
            # Fallback to empty parameters
            parameters = {"type": "object", "properties": {}}
        
        return ToolSchema(
            name=name,
            description=description.strip(),
            parameters=parameters,
            callable=func,
            source_type="function"
        )
    
    def _normalize_dict_tool(self, tool_dict: Dict[str, Any]) -> ToolSchema:
        """Normalize a dictionary tool into ToolSchema."""
        if 'function' in tool_dict:
            # OpenAI format: {"type": "function", "function": {...}}
            func_def = tool_dict['function']
            return ToolSchema(
                name=func_def.get('name', 'unknown'),
                description=func_def.get('description', ''),
                parameters=func_def.get('parameters', {}),
                source_type="openai"
            )
        else:
            # Direct format: {"name": ..., "description": ..., "parameters": ...}
            return ToolSchema(
                name=tool_dict.get('name', 'unknown'),
                description=tool_dict.get('description', ''),
                parameters=tool_dict.get('parameters', {}),
                source_type="custom"
            )
    
    def _normalize_object_tool(self, tool_obj: Any) -> ToolSchema:
        """Normalize a tool object into ToolSchema."""
        return ToolSchema(
            name=getattr(tool_obj, 'name', 'unknown'),
            description=getattr(tool_obj, 'description', ''),
            parameters=getattr(tool_obj, 'parameters', {}),
            callable=getattr(tool_obj, '__call__', None),
            source_type="object"
        )
    
    def _python_type_to_json_type(self, py_type: type) -> str:
        """Convert Python type annotation to JSON schema type."""
        if py_type == str:
            return "string"
        elif py_type == int:
            return "integer"
        elif py_type == float:
            return "number"
        elif py_type == bool:
            return "boolean"
        elif py_type == list:
            return "array"
        elif py_type == dict:
            return "object"
        else:
            return "string"  # Default fallback
    
    def _build_transcript_window(
        self,
        agent: AgentProtocol,
        prompt: str,
        kwargs: Dict[str, Any]
    ) -> TranscriptWindow:
        """Build transcript window from agent conversation history."""
        # Get system prompt
        system_prompt = None
        if hasattr(agent, '_build_system_prompt'):
            try:
                system_prompt = agent._build_system_prompt()
            except Exception as e:
                logger.warning(f"Failed to build system prompt: {e}")
        
        # Get conversation history - deep copy to prevent cross-agent mutations
        messages = []
        if hasattr(agent, 'chat_history') and agent.chat_history:
            messages = copy.deepcopy(agent.chat_history)
        
        # Add current prompt as user message
        if prompt:
            messages.append({"role": "user", "content": prompt})
        
        # Estimate token count (rough approximation)
        total_tokens = self._estimate_tokens(messages, system_prompt)
        
        return TranscriptWindow(
            messages=messages,
            total_tokens=total_tokens,
            system_prompt=system_prompt,
            context_metadata={
                "original_prompt": prompt,
                "history_length": len(messages) - (1 if prompt else 0)
            }
        )
    
    def _estimate_tokens(
        self, 
        messages: List[Dict[str, Any]], 
        system_prompt: Optional[str]
    ) -> int:
        """Rough token estimation for transcript."""
        total_chars = 0
        
        if system_prompt:
            total_chars += len(system_prompt)
        
        for msg in messages:
            content = msg.get('content', '')
            if isinstance(content, str):
                total_chars += len(content)
        
        # Rough approximation: 1 token ≈ 4 characters
        return total_chars // 4
    
    def _build_delivery_channels(
        self,
        agent: AgentProtocol,
        kwargs: Dict[str, Any]
    ) -> DeliveryChannels:
        """Build delivery channels configuration."""
        enable_streaming = kwargs.get('stream', False)
        enable_metrics = kwargs.get('enable_metrics', False)
        
        # Get stream emitter from agent if available
        stream_emitter = None
        if enable_streaming:
            if hasattr(agent, '_stream_emitter'):
                stream_emitter = agent._stream_emitter
            elif hasattr(agent, 'stream_emitter'):
                stream_emitter = agent.stream_emitter
        
        # Get callbacks
        callbacks = kwargs.get('callbacks', [])
        async_callbacks = kwargs.get('async_callbacks', [])
        
        return DeliveryChannels(
            stream_emitter=stream_emitter,
            callbacks=callbacks,
            async_callbacks=async_callbacks,
            enable_streaming=enable_streaming,
            enable_metrics=enable_metrics
        )
    
    def _build_session_correlation(
        self,
        agent: AgentProtocol,
        kwargs: Dict[str, Any]
    ) -> SessionCorrelation:
        """Build session correlation identifiers."""
        # Use provided IDs or generate new ones
        session_id = kwargs.get('session_id')
        if not session_id and hasattr(agent, 'session_id'):
            session_id = agent.session_id
        if not session_id:
            session_id = f"session-{uuid.uuid4().hex[:8]}"
        
        turn_id = kwargs.get('turn_id') or f"turn-{uuid.uuid4().hex[:8]}"
        agent_id = kwargs.get('agent_id') or getattr(agent, 'name', 'agent')
        run_id = kwargs.get('run_id') or f"run-{uuid.uuid4().hex[:8]}"
        parent_id = kwargs.get('parent_id')
        
        return SessionCorrelation(
            session_id=session_id,
            turn_id=turn_id,
            agent_id=agent_id,
            run_id=run_id,
            parent_id=parent_id,
            trace_metadata=kwargs.get('trace_metadata', {})
        )
    
    def _extract_turn_metadata(
        self,
        agent: AgentProtocol,
        kwargs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract additional turn metadata."""
        metadata = {}
        
        # Add agent metadata
        if hasattr(agent, 'role'):
            metadata['agent_role'] = agent.role
        if hasattr(agent, 'goal'):
            metadata['agent_goal'] = agent.goal
        
        # Add request metadata
        if 'metadata' in kwargs:
            metadata.update(kwargs['metadata'])
        
        return metadata


# Global instance for convenience
default_context_builder = DefaultTurnContextBuilder()