"""
MCP Sampling Implementation

Implements the Sampling API per MCP 2025-11-25 specification.
Sampling allows servers to request LLM completions from clients.

Features:
- Sampling requests with tool calling support
- Tool choice configuration
- Model preferences
- System prompt support
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class ToolChoiceMode(str, Enum):
    """Tool choice modes per MCP 2025-11-25 specification."""
    AUTO = "auto"  # Model decides whether to use tools
    NONE = "none"  # Model should not use tools
    ANY = "any"  # Model must use at least one tool (any tool)
    TOOL = "tool"  # Model must use a specific tool


# Backwards compatibility alias
ToolChoiceType = ToolChoiceMode


@dataclass
class ToolDefinition:
    """Tool definition for sampling requests."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


@dataclass
class ToolChoice:
    """Tool choice configuration per MCP 2025-11-25."""
    mode: ToolChoiceMode
    name: Optional[str] = None  # Required when mode is TOOL
    
    # Backwards compatibility alias
    @property
    def type(self) -> ToolChoiceMode:
        return self.mode
    
    @property
    def tool_name(self) -> Optional[str]:
        return self.name
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to MCP toolChoice format."""
        result = {"mode": self.mode.value}
        if self.mode == ToolChoiceMode.TOOL and self.name:
            result["name"] = self.name
        return result
    
    @classmethod
    def auto(cls) -> "ToolChoice":
        return cls(mode=ToolChoiceMode.AUTO)
    
    @classmethod
    def none(cls) -> "ToolChoice":
        return cls(mode=ToolChoiceMode.NONE)
    
    @classmethod
    def any(cls) -> "ToolChoice":
        return cls(mode=ToolChoiceMode.ANY)
    
    @classmethod
    def tool(cls, name: str) -> "ToolChoice":
        return cls(mode=ToolChoiceMode.TOOL, name=name)


@dataclass
class SamplingMessage:
    """Message for sampling request."""
    role: str  # "user", "assistant", "system"
    content: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": {"type": "text", "text": self.content},
        }


@dataclass
class ModelPreferences:
    """Model preferences for sampling."""
    hints: List[Dict[str, str]] = field(default_factory=list)
    cost_priority: Optional[float] = None  # 0-1, lower = prefer cheaper
    speed_priority: Optional[float] = None  # 0-1, lower = prefer faster
    intelligence_priority: Optional[float] = None  # 0-1, lower = prefer smarter
    
    def to_dict(self) -> Dict[str, Any]:
        result = {}
        if self.hints:
            result["hints"] = self.hints
        if self.cost_priority is not None:
            result["costPriority"] = self.cost_priority
        if self.speed_priority is not None:
            result["speedPriority"] = self.speed_priority
        if self.intelligence_priority is not None:
            result["intelligencePriority"] = self.intelligence_priority
        return result


@dataclass
class SamplingRequest:
    """
    MCP Sampling request.
    
    Allows servers to request LLM completions from clients.
    """
    messages: List[SamplingMessage]
    system_prompt: Optional[str] = None
    model_preferences: Optional[ModelPreferences] = None
    max_tokens: int = 1024
    temperature: Optional[float] = None
    stop_sequences: List[str] = field(default_factory=list)
    
    # Tool calling (MCP 2025-11-25)
    tools: List[ToolDefinition] = field(default_factory=list)
    tool_choice: Optional[ToolChoice] = None
    
    # Metadata
    include_context: Optional[str] = None  # "none", "thisServer", "allServers"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "messages": [m.to_dict() for m in self.messages],
            "maxTokens": self.max_tokens,
        }
        
        if self.system_prompt:
            result["systemPrompt"] = self.system_prompt
        
        if self.model_preferences:
            result["modelPreferences"] = self.model_preferences.to_dict()
        
        if self.temperature is not None:
            result["temperature"] = self.temperature
        
        if self.stop_sequences:
            result["stopSequences"] = self.stop_sequences
        
        # Tool calling
        if self.tools:
            result["tools"] = [t.to_dict() for t in self.tools]
        
        if self.tool_choice:
            result["toolChoice"] = self.tool_choice.to_dict()
        
        if self.include_context:
            result["includeContext"] = self.include_context
        
        if self.metadata:
            result["_meta"] = self.metadata
        
        return result


@dataclass
class ToolCall:
    """Tool call from sampling response."""
    id: str
    name: str
    arguments: Dict[str, Any]
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolCall":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            arguments=data.get("arguments", {}),
        )


@dataclass
class SamplingResponse:
    """
    MCP Sampling response.
    
    Contains the LLM completion result.
    """
    role: str
    content: str
    model: Optional[str] = None
    stop_reason: Optional[str] = None
    
    # Tool calls (MCP 2025-11-25)
    tool_calls: List[ToolCall] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "role": self.role,
            "content": {"type": "text", "text": self.content},
        }
        
        if self.model:
            result["model"] = self.model
        
        if self.stop_reason:
            result["stopReason"] = self.stop_reason
        
        if self.tool_calls:
            result["toolCalls"] = [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                for tc in self.tool_calls
            ]
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SamplingResponse":
        content = data.get("content", {})
        if isinstance(content, dict):
            text = content.get("text", "")
        else:
            text = str(content)
        
        tool_calls = []
        if "toolCalls" in data:
            tool_calls = [ToolCall.from_dict(tc) for tc in data["toolCalls"]]
        
        return cls(
            role=data.get("role", "assistant"),
            content=text,
            model=data.get("model"),
            stop_reason=data.get("stopReason"),
            tool_calls=tool_calls,
        )


class SamplingHandler:
    """
    Handles sampling requests.
    
    Can be configured with different backends:
    - Client callback (for MCP client-side sampling)
    - Direct LLM integration (for server-side sampling)
    """
    
    def __init__(
        self,
        callback: Optional[Callable] = None,
        default_model: Optional[str] = None,
    ):
        """
        Initialize sampling handler.
        
        Args:
            callback: Async callback for sampling requests
            default_model: Default model to use
        """
        self._callback = callback
        self._default_model = default_model
    
    def set_callback(self, callback: Callable) -> None:
        """Set the sampling callback."""
        self._callback = callback
    
    async def create_message(
        self,
        request: SamplingRequest,
    ) -> SamplingResponse:
        """
        Create a sampling message.
        
        Args:
            request: Sampling request
            
        Returns:
            Sampling response
        """
        if self._callback:
            return await self._callback(request)
        
        # Fall back to direct LLM integration
        return await self._direct_sampling(request)
    
    async def _direct_sampling(
        self,
        request: SamplingRequest,
    ) -> SamplingResponse:
        """
        Direct LLM sampling using praisonaiagents.
        
        Falls back to this when no callback is configured.
        """
        try:
            from praisonaiagents import Agent
            
            # Build messages
            messages = []
            if request.system_prompt:
                messages.append({"role": "system", "content": request.system_prompt})
            
            for msg in request.messages:
                messages.append({"role": msg.role, "content": msg.content})
            
            # Create agent for sampling
            agent = Agent(
                instructions=request.system_prompt or "You are a helpful assistant.",
                llm=self._default_model,
            )
            
            # Get last user message
            last_message = ""
            for msg in reversed(request.messages):
                if msg.role == "user":
                    last_message = msg.content
                    break
            
            # Execute
            result = agent.chat(last_message)
            
            return SamplingResponse(
                role="assistant",
                content=result,
                model=self._default_model,
                stop_reason="end_turn",
            )
            
        except ImportError:
            return SamplingResponse(
                role="assistant",
                content="Sampling not available - praisonaiagents not installed",
                stop_reason="error",
            )
        except Exception as e:
            logger.exception("Sampling failed")
            return SamplingResponse(
                role="assistant",
                content=f"Sampling error: {str(e)}",
                stop_reason="error",
            )


# Global sampling handler
_sampling_handler: Optional[SamplingHandler] = None


def get_sampling_handler() -> SamplingHandler:
    """Get the global sampling handler."""
    global _sampling_handler
    if _sampling_handler is None:
        _sampling_handler = SamplingHandler()
    return _sampling_handler


def set_sampling_handler(handler: SamplingHandler) -> None:
    """Set the global sampling handler."""
    global _sampling_handler
    _sampling_handler = handler


def create_sampling_request(
    prompt: str,
    system_prompt: Optional[str] = None,
    max_tokens: int = 1024,
    tools: Optional[List[Dict[str, Any]]] = None,
    tool_choice: Optional[str] = None,
) -> SamplingRequest:
    """
    Create a sampling request.
    
    Args:
        prompt: User prompt
        system_prompt: System prompt
        max_tokens: Maximum tokens
        tools: Tool definitions
        tool_choice: Tool choice type
        
    Returns:
        SamplingRequest
    """
    messages = [SamplingMessage(role="user", content=prompt)]
    
    tool_defs = []
    if tools:
        for tool in tools:
            tool_defs.append(ToolDefinition(
                name=tool.get("name", ""),
                description=tool.get("description", ""),
                input_schema=tool.get("inputSchema", tool.get("input_schema", {})),
            ))
    
    tc = None
    if tool_choice:
        if tool_choice == "auto":
            tc = ToolChoice.auto()
        elif tool_choice == "none":
            tc = ToolChoice.none()
        elif tool_choice == "any":
            tc = ToolChoice.any()
        else:
            # Specific tool name
            tc = ToolChoice.tool(tool_choice)
    
    return SamplingRequest(
        messages=messages,
        system_prompt=system_prompt,
        max_tokens=max_tokens,
        tools=tool_defs,
        tool_choice=tc,
    )
