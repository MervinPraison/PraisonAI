"""
OpenAI-Compatible HTTP Provider

Provides OpenAI API compatibility layer for PraisonAI agents and completions.
Implements standard OpenAI endpoints like /v1/chat/completions, /v1/models, etc.
"""

import json
import time
import uuid
from typing import Any, Dict, List, Optional, Iterator

from .base import BaseProvider, InvokeResult, HealthResult
from ..discovery import EndpointInfo, ProviderInfo


class OpenAICompatProvider(BaseProvider):
    """
    OpenAI API-compatible provider for PraisonAI.
    
    Implements standard OpenAI endpoints:
    - POST /v1/chat/completions
    - POST /v1/completions  
    - GET /v1/models
    - POST /v1/embeddings (if available)
    - POST /v1/tools/invoke (custom)
    """
    
    provider_type = "openai-compat"
    
    def __init__(
        self,
        base_url: str = "http://localhost:8765",
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        agent_provider: Optional[BaseProvider] = None,
    ):
        """
        Initialize OpenAI-compatible provider.
        
        Args:
            base_url: Base URL of the server
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
            agent_provider: Optional AgentsAPIProvider for agent routing
        """
        super().__init__(base_url, api_key, timeout)
        self.agent_provider = agent_provider
    
    def get_provider_info(self) -> ProviderInfo:
        """Get provider information."""
        return ProviderInfo(
            type=self.provider_type,
            name="OpenAI API Compatibility Layer",
            description="OpenAI API-compatible endpoints for PraisonAI",
            capabilities=["chat", "completions", "models", "embeddings", "tools"],
        )
    
    def list_endpoints(self, tags: Optional[List[str]] = None) -> List[EndpointInfo]:
        """List available OpenAI-compatible endpoints."""
        endpoints = [
            EndpointInfo(
                name="chat_completions",
                description="OpenAI-compatible chat completions",
                provider_type=self.provider_type,
                tags=["chat", "openai"],
                version="1.0.0",
                streaming=["none", "sse"],
                auth_modes=["none", "api_key"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "messages": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "role": {"type": "string", "enum": ["user", "assistant", "system"]},
                                    "content": {"type": "string"}
                                }
                            }
                        },
                        "model": {"type": "string", "default": "gpt-4o-mini"},
                        "temperature": {"type": "number", "default": 1.0},
                        "max_tokens": {"type": "integer"},
                        "stream": {"type": "boolean", "default": False},
                        "tools": {"type": "array"},
                        "tool_choice": {"type": "string"}
                    },
                    "required": ["messages"]
                },
            ),
            EndpointInfo(
                name="completions",
                description="OpenAI-compatible text completions",
                provider_type=self.provider_type,
                tags=["completions", "openai"],
                version="1.0.0",
                streaming=["none"],
                auth_modes=["none", "api_key"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                        "model": {"type": "string", "default": "gpt-3.5-turbo-instruct"},
                        "temperature": {"type": "number", "default": 1.0},
                        "max_tokens": {"type": "integer"}
                    },
                    "required": ["prompt"]
                },
            ),
            EndpointInfo(
                name="models",
                description="List available models",
                provider_type=self.provider_type,
                tags=["models", "openai"],
                version="1.0.0",
                streaming=["none"],
                auth_modes=["none"],
            ),
            EndpointInfo(
                name="tools_invoke",
                description="Invoke agent tools (PraisonAI extension)",
                provider_type=self.provider_type,
                tags=["tools", "praisonai"],
                version="1.0.0",
                streaming=["none"],
                auth_modes=["none", "api_key"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "agent": {"type": "string"},
                        "tool_name": {"type": "string"},
                        "parameters": {"type": "object"}
                    },
                    "required": ["tool_name"]
                },
            ),
        ]
        
        if tags:
            endpoints = [ep for ep in endpoints if any(tag in ep.tags for tag in tags)]
        
        return endpoints
    
    def describe_endpoint(self, name: str) -> Optional[EndpointInfo]:
        """Get detailed information about an endpoint."""
        endpoints = self.list_endpoints()
        for ep in endpoints:
            if ep.name == name:
                return ep
        return None
    
    def invoke(
        self,
        name: str,
        input_data: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
        stream: bool = False,
    ) -> InvokeResult:
        """Invoke OpenAI-compatible endpoint."""
        try:
            if name == "chat_completions":
                return self._handle_chat_completions(input_data, stream)
            elif name == "completions":
                return self._handle_completions(input_data)
            elif name == "models":
                return self._handle_models()
            elif name == "tools_invoke":
                return self._handle_tools_invoke(input_data)
            else:
                return InvokeResult(
                    ok=False,
                    status="not_found",
                    error=f"Unknown endpoint: {name}",
                )
        except Exception as e:
            return InvokeResult(
                ok=False,
                status="error",
                error=f"Internal error: {str(e)}",
            )
    
    def invoke_stream(
        self,
        name: str,
        input_data: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Stream OpenAI-compatible responses."""
        if name == "chat_completions":
            yield from self._stream_chat_completions(input_data)
        else:
            # Fall back to non-streaming
            result = self.invoke(name, input_data, config, stream=False)
            if result.ok:
                yield {"event": "complete", "data": result.data}
            else:
                yield {"event": "error", "data": {"error": result.error}}
    
    def _handle_chat_completions(self, input_data: Dict[str, Any], stream: bool = False) -> InvokeResult:
        """Handle /v1/chat/completions endpoint."""
        from praisonai.capabilities.completions import chat_completion
        
        try:
            # Extract OpenAI-format request
            messages = input_data.get("messages", [])
            model = input_data.get("model", "gpt-4o-mini")
            temperature = input_data.get("temperature", 1.0)
            max_tokens = input_data.get("max_tokens")
            tools = input_data.get("tools")
            tool_choice = input_data.get("tool_choice")
            
            # Call PraisonAI completion capability
            result = chat_completion(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                tool_choice=tool_choice,
                stream=stream,
                api_key=self.api_key,
            )
            
            # Convert to OpenAI format
            response = self._format_chat_completion_response(result)
            
            return InvokeResult(
                ok=True,
                status="success",
                data=response,
            )
            
        except Exception as e:
            return InvokeResult(
                ok=False,
                status="error",
                error=f"Chat completion error: {str(e)}",
            )
    
    def _handle_completions(self, input_data: Dict[str, Any]) -> InvokeResult:
        """Handle /v1/completions endpoint."""
        from praisonai.capabilities.completions import text_completion
        
        try:
            prompt = input_data.get("prompt", "")
            model = input_data.get("model", "gpt-3.5-turbo-instruct")
            temperature = input_data.get("temperature", 1.0)
            max_tokens = input_data.get("max_tokens")
            
            result = text_completion(
                prompt=prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=self.api_key,
            )
            
            response = self._format_completion_response(result)
            
            return InvokeResult(
                ok=True,
                status="success",
                data=response,
            )
            
        except Exception as e:
            return InvokeResult(
                ok=False,
                status="error", 
                error=f"Text completion error: {str(e)}",
            )
    
    def _handle_models(self) -> InvokeResult:
        """Handle /v1/models endpoint."""
        # Return common models supported by LiteLLM
        models = [
            {
                "id": "gpt-4o-mini",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "openai",
            },
            {
                "id": "gpt-4o",
                "object": "model", 
                "created": int(time.time()),
                "owned_by": "openai",
            },
            {
                "id": "gpt-3.5-turbo",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "openai",
            },
            {
                "id": "claude-3-5-sonnet-20241022",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "anthropic",
            },
        ]
        
        response = {
            "object": "list",
            "data": models
        }
        
        return InvokeResult(
            ok=True,
            status="success",
            data=response,
        )
    
    def _handle_tools_invoke(self, input_data: Dict[str, Any]) -> InvokeResult:
        """Handle /v1/tools/invoke endpoint (PraisonAI extension)."""
        if not self.agent_provider:
            return InvokeResult(
                ok=False,
                status="not_available",
                error="Agent provider not configured for tool invocation",
            )
        
        try:
            agent_name = input_data.get("agent", "default")
            tool_name = input_data.get("tool_name")
            parameters = input_data.get("parameters", {})
            
            # Route to agent provider for tool execution
            agent_input = {
                "query": f"Use tool {tool_name} with parameters: {json.dumps(parameters)}",
                "tool_name": tool_name,
                "parameters": parameters,
            }
            
            result = self.agent_provider.invoke(agent_name, agent_input)
            
            return InvokeResult(
                ok=result.ok,
                status=result.status,
                data={
                    "tool_name": tool_name,
                    "result": result.data,
                    "success": result.ok,
                },
                error=result.error,
            )
            
        except Exception as e:
            return InvokeResult(
                ok=False,
                status="error",
                error=f"Tool invocation error: {str(e)}",
            )
    
    def _stream_chat_completions(self, input_data: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        """Stream chat completions in OpenAI SSE format."""
        try:
            # For now, use non-streaming and convert to SSE format
            result = self._handle_chat_completions(input_data, stream=False)
            
            if not result.ok:
                yield {
                    "event": "error",
                    "data": {"error": result.error}
                }
                return
            
            response = result.data
            choice = response["choices"][0] if response["choices"] else {}
            content = choice.get("message", {}).get("content", "")
            
            # Simulate streaming by chunking the response
            chunk_id = str(uuid.uuid4())
            
            # Send chunks
            for i, char in enumerate(content):
                chunk = {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": response.get("model", "gpt-4o-mini"),
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": char},
                            "finish_reason": None
                        }
                    ]
                }
                yield {"event": "data", "data": chunk}
            
            # Send final chunk
            final_chunk = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": response.get("model", "gpt-4o-mini"),
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop"
                    }
                ]
            }
            yield {"event": "data", "data": final_chunk}
            yield {"event": "done", "data": "[DONE]"}
            
        except Exception as e:
            yield {
                "event": "error", 
                "data": {"error": f"Streaming error: {str(e)}"}
            }
    
    def _format_chat_completion_response(self, result) -> Dict[str, Any]:
        """Convert PraisonAI CompletionResult to OpenAI chat completion format."""
        return {
            "id": result.id or f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": result.model or "gpt-4o-mini",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": result.role,
                        "content": result.content,
                        "tool_calls": result.tool_calls,
                    },
                    "finish_reason": result.finish_reason or "stop",
                }
            ],
            "usage": result.usage or {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        }
    
    def _format_completion_response(self, result) -> Dict[str, Any]:
        """Convert PraisonAI CompletionResult to OpenAI completion format."""
        return {
            "id": result.id or f"cmpl-{uuid.uuid4().hex[:8]}",
            "object": "text_completion",
            "created": int(time.time()),
            "model": result.model or "gpt-3.5-turbo-instruct",
            "choices": [
                {
                    "index": 0,
                    "text": result.content or "",
                    "finish_reason": result.finish_reason or "stop",
                }
            ],
            "usage": result.usage or {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        }
    
    def health(self) -> HealthResult:
        """Check OpenAI compatibility layer health."""
        try:
            # Test basic completion capability
            from praisonai.capabilities.completions import chat_completion
            
            test_result = chat_completion(
                messages=[{"role": "user", "content": "test"}],
                model="gpt-4o-mini",
                max_tokens=1,
            )
            
            return HealthResult(
                healthy=True,
                status="healthy",
                server_name="PraisonAI OpenAI Compatibility Layer",
                server_version="1.0.0",
                provider_type=self.provider_type,
                metadata={
                    "endpoints": ["chat/completions", "completions", "models", "tools/invoke"],
                    "test_completion_id": test_result.id,
                },
            )
            
        except Exception as e:
            return HealthResult(
                healthy=False,
                status="unhealthy",
                server_name="PraisonAI OpenAI Compatibility Layer",
                provider_type=self.provider_type,
                metadata={"error": str(e)},
            )