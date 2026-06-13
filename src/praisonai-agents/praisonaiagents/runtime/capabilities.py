"""
Runtime Capability System for PraisonAI Agents.

Defines capability flags and validation logic to detect runtime incompatibilities
at config/preflight time rather than during agent execution.

This addresses the issue where hooks, tools, streaming, and context compaction
behave differently across native and plugin harness runtimes, causing users
to discover incompatibilities mid-turn instead of at startup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Set, Optional, Dict, Any, Union


class RuntimeCapability(Enum):
    """
    Enumeration of runtime capabilities that agents may require.
    
    Used to declare what features a runtime supports and what features
    an agent/team configuration requires.
    """
    # Hook system capabilities
    NATIVE_HOOKS = auto()          # Supports in-process hook execution around tool/LLM events
    
    # Core execution capabilities  
    TOOL_LOOP = auto()             # Supports full agent tool execution loop
    STREAMING_DELTAS = auto()      # Supports real-time streaming of incremental responses
    CONTEXT_COMPACTION = auto()    # Supports automatic context size management
    
    # Tool and integration capabilities
    MCP_TOOLS = auto()             # Supports Model Context Protocol tools
    CODE_EXECUTION = auto()        # Supports safe code execution in sandboxes
    
    # Advanced capabilities
    MULTI_MODAL = auto()           # Supports images, audio, video processing
    ASYNC_EXECUTION = auto()       # Supports asynchronous operation
    SESSION_PERSISTENCE = auto()   # Supports persistent sessions across executions
    MEMORY_MANAGEMENT = auto()     # Supports advanced memory features
    
    # Plugin harness capabilities (typically reduced subset)
    BASIC_CHAT = auto()            # Basic text chat only
    SIMPLE_TOOLS = auto()          # Simple synchronous tool execution only


@dataclass
class RuntimeCapabilityMatrix:
    """
    Matrix of capabilities supported by a specific runtime implementation.
    
    Each runtime (native, plugin harness, managed service) declares its
    capability set using this matrix. Agent configurations can specify
    required capabilities, and validation occurs at runtime selection.
    
    Example:
        # Full native runtime
        native_matrix = RuntimeCapabilityMatrix(
            native_hooks=True,
            tool_loop=True, 
            streaming_deltas=True,
            context_compaction=True,
            mcp_tools=True,
            code_execution=True,
            multi_modal=True,
            async_execution=True,
            session_persistence=True,
            memory_management=True
        )
        
        # Limited plugin harness
        plugin_matrix = RuntimeCapabilityMatrix(
            basic_chat=True,
            simple_tools=True,
            # All other capabilities default to False
        )
    """
    
    # Hook system capabilities
    native_hooks: bool = False
    
    # Core execution capabilities
    tool_loop: bool = False
    streaming_deltas: bool = False
    context_compaction: bool = False
    
    # Tool and integration capabilities  
    mcp_tools: bool = False
    code_execution: bool = False
    
    # Advanced capabilities
    multi_modal: bool = False
    async_execution: bool = False
    session_persistence: bool = False
    memory_management: bool = False
    
    # Basic capabilities (typically for constrained environments)
    basic_chat: bool = False
    simple_tools: bool = False
    
    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_capability_set(self) -> Set[RuntimeCapability]:
        """Convert matrix to set of enabled capabilities."""
        capabilities = set()
        
        if self.native_hooks:
            capabilities.add(RuntimeCapability.NATIVE_HOOKS)
        if self.tool_loop:
            capabilities.add(RuntimeCapability.TOOL_LOOP)
        if self.streaming_deltas:
            capabilities.add(RuntimeCapability.STREAMING_DELTAS)
        if self.context_compaction:
            capabilities.add(RuntimeCapability.CONTEXT_COMPACTION)
        if self.mcp_tools:
            capabilities.add(RuntimeCapability.MCP_TOOLS)
        if self.code_execution:
            capabilities.add(RuntimeCapability.CODE_EXECUTION)
        if self.multi_modal:
            capabilities.add(RuntimeCapability.MULTI_MODAL)
        if self.async_execution:
            capabilities.add(RuntimeCapability.ASYNC_EXECUTION)
        if self.session_persistence:
            capabilities.add(RuntimeCapability.SESSION_PERSISTENCE)
        if self.memory_management:
            capabilities.add(RuntimeCapability.MEMORY_MANAGEMENT)
        if self.basic_chat:
            capabilities.add(RuntimeCapability.BASIC_CHAT)
        if self.simple_tools:
            capabilities.add(RuntimeCapability.SIMPLE_TOOLS)
            
        return capabilities
    
    def supports(self, capability: RuntimeCapability) -> bool:
        """Check if this runtime supports a specific capability."""
        return capability in self.to_capability_set()
    
    def supports_all(self, required_capabilities: Set[RuntimeCapability]) -> bool:
        """Check if this runtime supports all required capabilities."""
        supported = self.to_capability_set()
        return required_capabilities.issubset(supported)
    
    def missing_capabilities(self, required_capabilities: Set[RuntimeCapability]) -> Set[RuntimeCapability]:
        """Return set of required capabilities that this runtime doesn't support."""
        supported = self.to_capability_set()
        return required_capabilities - supported


class CapabilityValidationError(Exception):
    """
    Raised when runtime capability validation fails.
    
    Indicates that the selected runtime lacks capabilities required
    by the agent or team configuration.
    """
    
    def __init__(
        self, 
        runtime_name: str, 
        missing_capabilities: Set[RuntimeCapability],
        available_capabilities: Optional[Set[RuntimeCapability]] = None
    ):
        self.runtime_name = runtime_name
        self.missing_capabilities = missing_capabilities
        self.available_capabilities = available_capabilities or set()
        
        missing_names = [cap.name for cap in missing_capabilities]
        message = (
            f"Runtime '{runtime_name}' lacks required capabilities: {missing_names}. "
            f"Available capabilities: {[cap.name for cap in self.available_capabilities]}"
        )
        super().__init__(message)


def validate_capabilities(
    runtime_matrix: RuntimeCapabilityMatrix,
    required_capabilities: Union[Set[RuntimeCapability], RuntimeCapabilityMatrix],
    runtime_name: str = "unknown"
) -> bool:
    """
    Validate that a runtime supports all required capabilities.
    
    Args:
        runtime_matrix: Capability matrix of the runtime
        required_capabilities: Required capabilities (set or matrix)
        runtime_name: Name of runtime for error messages
        
    Returns:
        True if validation passes
        
    Raises:
        CapabilityValidationError: If validation fails
    """
    if isinstance(required_capabilities, RuntimeCapabilityMatrix):
        required_set = required_capabilities.to_capability_set()
    else:
        required_set = required_capabilities
    
    if runtime_matrix.supports_all(required_set):
        return True
    
    missing = runtime_matrix.missing_capabilities(required_set)
    available = runtime_matrix.to_capability_set()
    
    raise CapabilityValidationError(
        runtime_name=runtime_name,
        missing_capabilities=missing,
        available_capabilities=available
    )


def get_native_runtime_capabilities() -> RuntimeCapabilityMatrix:
    """
    Get the capability matrix for the built-in native runtime.
    
    The native runtime supports all capabilities since it runs
    in-process with full access to the agent system.
    
    Returns:
        Full capability matrix for native runtime
    """
    return RuntimeCapabilityMatrix(
        # Hook system - native runtime supports full hook system
        native_hooks=True,
        
        # Core execution - native runtime supports all core features
        tool_loop=True,
        streaming_deltas=True,
        context_compaction=True,
        
        # Tools and integrations - native runtime supports all
        mcp_tools=True,
        code_execution=True,
        
        # Advanced features - native runtime supports all
        multi_modal=True,
        async_execution=True,
        session_persistence=True,
        memory_management=True,
        
        # Basic features - native runtime also supports basic modes
        basic_chat=True,
        simple_tools=True,
        
        metadata={
            "runtime_type": "native",
            "description": "Built-in PraisonAI native runtime with full capabilities"
        }
    )


def get_reduced_harness_capabilities() -> RuntimeCapabilityMatrix:
    """
    Get an example capability matrix for a reduced plugin harness.
    
    This represents a typical external harness that only supports
    basic functionality without advanced native features.
    
    Returns:
        Reduced capability matrix for plugin harness example
    """
    return RuntimeCapabilityMatrix(
        # No native hooks - external harness can't hook into native events
        native_hooks=False,
        
        # Limited execution capabilities
        tool_loop=True,        # Can execute tools but without native hooks
        streaming_deltas=False, # May not support real-time streaming
        context_compaction=False, # May not have context management
        
        # Limited tool support
        mcp_tools=False,       # May not support MCP protocol
        code_execution=False,  # May not have safe execution environment
        
        # Basic features only
        multi_modal=False,
        async_execution=False,
        session_persistence=False,
        memory_management=False,
        
        # Supports basic operations
        basic_chat=True,
        simple_tools=True,
        
        metadata={
            "runtime_type": "plugin_harness",
            "description": "Example reduced plugin harness with limited capabilities"
        }
    )