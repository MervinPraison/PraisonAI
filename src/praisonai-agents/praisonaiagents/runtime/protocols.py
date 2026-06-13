"""
Runtime Protocols for PraisonAI Agents.

Defines the AgentRuntimeProtocol that all runtime implementations must follow,
including the capability reporting requirement for runtime compatibility validation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from .capabilities import RuntimeCapabilityMatrix


@runtime_checkable
class AgentRuntimeProtocol(Protocol):
    """
    Protocol that all agent runtime implementations must follow.
    
    This protocol defines the interface for different runtime environments:
    - Native runtime (built-in praisonai runtime)
    - Plugin harness runtimes (external CLI tools, docker containers)
    - Managed service runtimes (Anthropic, E2B, Modal, etc.)
    
    Key requirement: All implementations must declare their capability matrix
    via the capabilities() method to enable compatibility validation.
    
    Example lifecycle:
        runtime = SomeRuntimeImplementation()
        caps = runtime.capabilities()
        
        # Validate against agent requirements
        if not caps.supports_all(required_capabilities):
            raise CapabilityValidationError(...)
            
        # Execute agent
        result = await runtime.execute_agent(config, prompt)
    """
    
    @property
    def runtime_name(self) -> str:
        """
        Human-readable name of this runtime implementation.
        
        Examples: "native", "claude-code", "e2b-managed", "docker-harness"
        """
        ...
    
    @property 
    def runtime_version(self) -> str:
        """
        Version string of this runtime implementation.
        
        Used for compatibility tracking and debugging.
        """
        ...
    
    def capabilities(self) -> RuntimeCapabilityMatrix:
        """
        Report the capability matrix for this runtime.
        
        This is the key method for the capability validation system.
        Each runtime must honestly declare what features it supports
        to enable fail-fast validation at config/selection time.
        
        Returns:
            RuntimeCapabilityMatrix with supported capabilities
        """
        ...
    
    async def execute_agent(
        self, 
        agent_config: Dict[str, Any], 
        prompt: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute agent with the given configuration and prompt.
        
        Args:
            agent_config: Agent configuration dict
            prompt: User prompt to process
            **kwargs: Additional execution parameters
            
        Returns:
            Execution result dict with response, metadata, etc.
        """
        ...
    
    async def stream_agent(
        self,
        agent_config: Dict[str, Any],
        prompt: str,
        **kwargs
    ) -> Any:  # AsyncIterator but avoid import
        """
        Execute agent with streaming responses.
        
        Only required if runtime declares streaming_deltas capability.
        
        Args:
            agent_config: Agent configuration dict 
            prompt: User prompt to process
            **kwargs: Additional execution parameters
            
        Yields:
            Streaming response chunks
        """
        ...
    
    async def validate_config(
        self, 
        agent_config: Dict[str, Any]
    ) -> List[str]:
        """
        Validate agent configuration against runtime capabilities.
        
        Args:
            agent_config: Agent configuration to validate
            
        Returns:
            List of validation error messages (empty if valid)
        """
        ...
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform runtime health check.
        
        Returns:
            Health status dict with status, latency, errors, etc.
        """
        ...


@runtime_checkable  
class CliBackendProtocol(Protocol):
    """
    Protocol for CLI backend implementations (subset of AgentRuntimeProtocol).
    
    This is the existing protocol that cli_backend parameter uses.
    We extend it to also require capability reporting for consistency.
    
    Note: This maintains backward compatibility with existing CLI backends
    while adding the capability requirement for the new validation system.
    """
    
    def capabilities(self) -> RuntimeCapabilityMatrix:
        """
        Report capabilities for this CLI backend.
        
        Required for integration with the runtime capability validation system.
        CLI backends should honestly declare their capabilities.
        
        Returns:
            RuntimeCapabilityMatrix with supported capabilities
        """
        ...
    
    async def execute(
        self,
        prompt: str,
        session: Any,  # CliSessionBinding
        images: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Any:
        """Execute prompt via CLI backend."""
        ...
    
    def stream(
        self,
        prompt: str,
        session: Any,  # CliSessionBinding  
        images: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> Any:  # AsyncIterator
        """Stream response via CLI backend."""
        ...